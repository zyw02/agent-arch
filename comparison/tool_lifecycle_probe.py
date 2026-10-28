#!/usr/bin/env python3
"""Hosted native read/MCP scheduling, reached failure and explicit cancellation."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import tempfile
import threading
import time
import uuid
from context_skill_probe import request_text
from native_read_probe import schemas
from platform_api_probe import NativeServer,redact
from tool_lifecycle_provider import ToolProvider

PROTOCOL=Path(__file__).with_name('tool-lifecycle-protocol.json')
CONDITIONS=('native_single','mcp_single','mcp_four_serial','mcp_four_batch','mcp_batch_failure','mcp_batch_cancel')
TASK_MARKER=re.compile(r'TOOL_INPUT_[a-f0-9]{32}')


def tool_results(body):
    rows=[]
    for message in body.get('messages',[]):
        if message.get('role')=='tool':rows.append(dict(call_id=message.get('tool_call_id'),content=message.get('content')))
        if isinstance(message.get('content'),list):
            rows.extend(dict(call_id=b.get('tool_use_id'),content=b.get('content'),is_error=b.get('is_error')) for b in message['content'] if isinstance(b,dict) and b.get('type')=='tool_result')
    return rows


def terminal_text(product,result):
    if product=='OpenClaw':return '\n'.join(c.get('message',{}).get('content') or '' for c in result.get('choices',[]) if c.get('message',{}).get('role')=='assistant')
    records=result.get('output',{}).get('records',[])
    return '\n'.join(b.get('text','') for r in records if r.get('event',{}).get('type')=='assistant/message' for b in r['event'].get('data',{}).get('message',{}).get('content',[]) if b.get('type')=='text')


def read_ledger(path):
    if not path.exists():return []
    lines=path.read_text().splitlines();result=[]
    for index,line in enumerate(lines):
        try:result.append(json.loads(line))
        except ValueError:
            if index!=len(lines)-1:raise
    return result


def native_cancelled(product,history):
    if product=='DSH':
        return any(r.get('event',{}).get('type')=='turn/end' and r['event'].get('data',{}).get('reason',{}).get('kind')=='aborted' and r['event']['data']['reason'].get('reason',{}).get('kind')=='user' for r in history.get('events',{}).get('records',[]))
    # Native transcript status is separate from chat.abort's acceptance receipt.
    return any(m.get('stopReason')=='aborted' for m in history.get('history',{}).get('messages',[]))


def fixture_receipts_complete(row):
    if row['condition']=='native_single':return True
    events=row['fixture_events'];health_start=row.get('health_started_ns',float('inf'));primary=[e for e in events if e['monotonic_ns']<health_start]
    reads=[e for e in primary if e['kind']=='file_read'];sent=[e for e in primary if e['kind']=='result_sent'];condition=row['condition']
    if any(e['sha256']!=row['file_hashes'].get(str(e['index'])) for e in reads):return False
    if condition=='mcp_batch_cancel':
        health=[e for e in events if e['monotonic_ns']>=health_start and e['kind']=='file_read']
        return not any(e['index']==2 for e in reads) and len(health)==1 and health[0]['index']==0 and health[0]['sha256']==row['file_hashes']['0']
    wanted=[0] if condition=='mcp_single' else [0,1,3] if condition=='mcp_batch_failure' else list(range(4))
    if Counter(e['index'] for e in reads)!=Counter(wanted):return False
    if Counter(e['index'] for e in sent if not e['is_error'])!=Counter(wanted):return False
    if not all(any(s['mcp_call_id']==r['mcp_call_id'] and not s['is_error'] and s['content_sha256']==r['sha256'] for s in sent) for r in reads):return False
    errors=[s for s in sent if s['is_error']]
    if condition=='mcp_batch_failure':return len(errors)==1 and errors[0]['index']==2 and errors[0]['content_sha256']==hashlib.sha256(row['fixture_config']['failure_marker'].encode()).hexdigest()
    return not errors


class ToolPlan:
    def __init__(self,product,condition,files,values,failure_marker,health=False):
        self.marker='TOOL_INPUT_'+uuid.uuid4().hex;self.session_id=str(uuid.uuid4());self.product=product;self.condition=condition;self.files=files;self.values=values;self.failure_marker=failure_marker
        self.indexes=[0] if health or condition in ('native_single','mcp_single') else list(range(4));self.native=condition=='native_single' and not health
        self.target='read' if self.native else ('mcp__probe__eval_read' if product=='DSH' else 'probe__eval_read')
        self.serial=condition=='mcp_four_serial';self.failed_index=2 if condition=='mcp_batch_failure' and not health else None
        self.call_ids={i:'hd_'+self.marker[len('TOOL_INPUT_'):]+'_'+str(i) for i in self.indexes}
        self.expected_values={str(i):'error:'+failure_marker if i==self.failed_index else values[i] for i in self.indexes}
        self.expected_text=self.format(self.expected_values)
        self.prompt=f'{self.marker}\nRead the fixed synthetic files at indexes {self.indexes} using {self.target}. File paths: '+json.dumps({str(i):str(files[i]) for i in self.indexes})+'. Return only the task receipt and observed values. Never read any other file or run shell commands.'

    def format(self,values):return 'TOOL_DONE:'+self.marker+':'+json.dumps(values,sort_keys=True,separators=(',',':'))

    def decide(self,body):
        results={}
        for row in tool_results(body):
            if row['call_id'] not in self.call_ids.values():continue
            if row['call_id'] in results:return dict(text='FIXTURE_DUPLICATE_CORRELATED_RESULT')
            results[row['call_id']]=row
        values={}
        for i,identifier in self.call_ids.items():
            if identifier not in results:continue
            content=json.dumps(results[identifier]['content'])
            if self.values[i] in content:values[str(i)]=self.values[i]
            elif self.failure_marker in content:values[str(i)]='error:'+self.failure_marker
            else:return dict(text='FIXTURE_RESULT_WITHOUT_MATCHING_VALUE:'+str(i))
        if len(values)==len(self.indexes):return dict(text=self.format(values))
        if values and not self.serial:return dict(text='FIXTURE_INCOMPLETE_BATCH_RESULTS')
        available=schemas(body)
        if self.target not in available:return dict(text='FIXTURE_MISSING_TARGET_TOOL:'+self.target)
        wanted=[i for i in self.indexes if str(i) not in values]
        if self.serial:wanted=wanted[:1]
        calls=[]
        for i in wanted:
            if self.native:
                props=available[self.target].get('properties',{});key=next((k for k in ('file_path','path') if k in props),None)
                if key is None:return dict(text='FIXTURE_UNSUPPORTED_NATIVE_READ_SCHEMA')
                arguments={key:str(self.files[i])}
            else:arguments=dict(index=i)
            calls.append(dict(id=self.call_ids[i],name=self.target,arguments=arguments))
        return dict(calls=calls)


class ToolServer(NativeServer):
    def task_plan(self,plan):
        started=time.monotonic_ns();row=dict(session_id=plan.session_id,marker=plan.marker,target_tool=plan.target,started_ns=started)
        try:
            if self.product=='DSH':
                created=self.rpc('session/create',dict(request=dict(sessionId=plan.session_id,cwd=str(self.workspace))));row['session_id']=created['sessionId'];plan.session_id=created['sessionId'];row['create_receipt']=created
                row['prompt_receipt']=self.rpc('session/prompt',dict(request=dict(sessionId=plan.session_id,requestId=str(uuid.uuid4()),mode='queue',content=[dict(type='text',text=plan.prompt)])))
                result=self.rpc('session/wait',dict(request=dict(sessionId=plan.session_id,timeoutMs=60000)))
            else:
                row['session_key']='agent:main:platform:'+plan.session_id
                status,_,raw=self.http('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',messages=[dict(role='user',content=plan.prompt)],user=plan.session_id,stream=False)),{'Content-Type':'application/json','Authorization':'Bearer synthetic-platform-only','x-openclaw-session-key':row['session_key']},timeout=120)
                row['http_status']=status;result=json.loads(raw)
            row['native_result']=result;row['terminal_text']=terminal_text(self.product,result);row['exact_final']=row['terminal_text']==plan.expected_text
        except Exception as error:row['operation_error']=dict(type=type(error).__name__,message=redact(str(error))[:1000])
        row['finished_ns']=time.monotonic_ns();return row

    def cancel_task(self,session_id):
        started=time.monotonic_ns()
        if self.product=='DSH':return dict(requested_ns=started,receipt=self.rpc('session/cancel',dict(request=dict(sessionId=session_id))),received_ns=time.monotonic_ns(),observer_cli=None)
        command=[str(self.runtime/'node_modules/.bin/openclaw'),'gateway','call','chat.abort','--port',str(self.port),'--json','--params',json.dumps(dict(sessionKey='agent:main:platform:'+session_id)),'--timeout','10000']
        before=resource.getrusage(resource.RUSAGE_CHILDREN);result=subprocess.run(command,env=self.env,cwd=self.workspace,capture_output=True,text=True,timeout=90);after=resource.getrusage(resource.RUSAGE_CHILDREN)
        return dict(requested_ns=started,received_ns=time.monotonic_ns(),receipt=json.loads(result.stdout) if result.returncode==0 else None,exit_code=result.returncode,stderr=redact(result.stderr),stdout=redact(result.stdout) if result.returncode else None,
            observer_cli=dict(cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,elapsed_ms=(time.monotonic_ns()-started)/1e6))


def extension_configure(product,root,config_path,route):
    def configure(server,env,command):
        if route=='native':return
        fixture=Path(__file__).with_name('tool_lifecycle_mcp.py').resolve()
        args=[str(fixture),'--config',str(config_path)]
        if product=='DSH':
            patch=root/'server.patch.yml';patch.write_text(patch.read_text()+'- insert:\n    - id: tool-lifecycle-mcp\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: probe\n        transport: stdio\n        command: /usr/bin/python3\n        args: '+json.dumps(args)+'\n        toolCallTimeoutMs: 60000\n        failOnStartupError: true\n')
        else:
            path=root/'openclaw.json';value=json.loads(path.read_bytes());value['mcp']=dict(servers=dict(probe=dict(transport='stdio',command='/usr/bin/python3',args=args,supportsParallelToolCalls=True,requestTimeoutMs=60000)))
            value['tools']['allow']=['probe__eval_read'];path.write_text(json.dumps(value))
    return configure


def run_arm(product,condition,block,runtime,root,values):
    started=time.monotonic_ns();cpu_started=resource.getrusage(resource.RUSAGE_SELF);root.mkdir();workspace=root/'workspace';workspace.mkdir();files=[]
    for index,value in enumerate(values):
        file=workspace/('receipt-'+str(index)+'.txt');file.write_text(value);files.append(file)
    file_hashes={str(i):hashlib.sha256(file.read_bytes()).hexdigest() for i,file in enumerate(files)}
    ledger=root/'mcp-ledger.jsonl';cleanup_release=root/'cleanup-release';failure_marker='TOOL_FAILURE_'+uuid.uuid4().hex
    config=dict(files=[str(p) for p in files],ledger=str(ledger),cleanup_release=str(cleanup_release),delay_seconds=.25 if 'four_' in condition or 'batch_' in condition else 0,
        fail_index=2 if condition=='mcp_batch_failure' else None,hold_index=2 if condition=='mcp_batch_cancel' else None,failure_marker=failure_marker)
    config_path=root/'fixture-config.json';config_path.write_text(json.dumps(config));plan=ToolPlan(product,condition,files,values,failure_marker);plans=[plan]
    def decide(body):
        text=request_text(body)
        if 'Generate the session title from this JSON array' in text:return dict(text='Tool lifecycle')
        markers=set(TASK_MARKER.findall(text));matching=[p for p in plans if p.marker in markers]
        if len(matching)!=1:return dict(text='FIXTURE_MISSING_OR_AMBIGUOUS_TASK_MARKER')
        return matching[0].decide(body)
    provider=ToolProvider(decide);server=None;row=dict(product=product,condition=condition,block=block,task_marker=plan.marker,validity='adapter_error',handling_acceptance_met=False,paid_model_calls=0,started_ns=started,fixture_config=config,file_hashes=file_hashes,input_values=values)
    try:
        server=ToolServer(product,runtime,root,provider,sample_interval=.05,configure=extension_configure(product,root,config_path,'native' if plan.native else 'mcp'),resource_paths=dict(extension_ledger=ledger))
        server.ready();row.update(carrier_ready_ns=server.ready_ns,command=server.command,processes_at_ready=server.process_map());server.collector.sample();row['task_phase_started_ns']=time.monotonic_ns()
        if condition=='mcp_batch_cancel':
            holder={}
            thread=threading.Thread(target=lambda:holder.update(result=server.task_plan(plan)),daemon=True);thread.start()
            deadline=time.monotonic()+90
            while time.monotonic()<deadline and thread.is_alive() and not any(e['kind']=='hold_entered' for e in read_ledger(ledger)):time.sleep(.01)
            row['boundary_reached']=any(e['kind']=='hold_entered' for e in read_ledger(ledger))
            if not row['boundary_reached']:
                row['validity']='trigger_not_reached';raise RuntimeError('Declared held MCP boundary not reached')
            row['cancel']=server.cancel_task(plan.session_id);receipt=row['cancel'].get('receipt') or {};row['cancel_acknowledged']=receipt.get('accepted') is True if product=='DSH' else receipt.get('aborted') is True
            epoch=row['cancel']['received_ns'];row['cancel_observations']=[]
            for offset in (.5,2,10):
                remaining=epoch+int(offset*1e9)-time.monotonic_ns()
                if remaining>0:time.sleep(remaining/1e9)
                events=read_ledger(ledger);processes=server.process_map();pids={p['pid'] for p in processes};active={e['mcp_call_id']:e for e in events if e['kind']=='call_received'}
                for e in events:
                    if e['kind']=='call_stopped':active.pop(e['mcp_call_id'],None)
                row['cancel_observations'].append(dict(offset_seconds=offset,observed_ns=time.monotonic_ns(),native_task_consumer_alive=thread.is_alive(),processes=processes,active_live_fixture_calls=[v for v in active.values() if v['pid'] in pids],provider_requests=len(provider.requests),ledger_events=len(events)))
            row['cancel_history']=server.history(plan.session_id);row['native_cancelled_terminal']=native_cancelled(product,row['cancel_history'])
            row['quiescent_at_10s']=not row['cancel_observations'][-1]['active_live_fixture_calls'] and not row['cancel_observations'][-1]['native_task_consumer_alive'] and not any(r['arrived_ns']>epoch and plan.marker in request_text(r['request']) and 'Generate the session title' not in request_text(r['request']) for r in provider.requests)
            cleanup_release.write_text('cleanup only, no file read permitted');thread.join(timeout=15)
            row['task']=holder.get('result',{});row['native_task_consumer_still_alive_after_cleanup_release']=thread.is_alive()
            health=ToolPlan(product,'mcp_single',files,values,failure_marker,health=True);plans.append(health);row['health_started_ns']=time.monotonic_ns();row['health_task']=server.task_plan(health)
            row['handling_acceptance_met']=row['cancel_acknowledged'] and row['native_cancelled_terminal'] and row['quiescent_at_10s'] and not thread.is_alive() and row['health_task'].get('exact_final',False)
            row['product_outcome']='safe_indeterminate' if row['handling_acceptance_met'] else 'failure'
        else:
            row['task']=server.task_plan(plan);row['handling_acceptance_met']=row['task'].get('exact_final',False);row['product_outcome']='failure' if condition=='mcp_batch_failure' else ('success' if row['handling_acceptance_met'] else 'failure')
        row['task_phase_finished_ns']=time.monotonic_ns();server.collector.sample();row['processes_at_task_end']=server.process_map();row['native_history']=server.history(plan.session_id)
        row['validity']='valid'
    except Exception as error:row['adapter_error']=dict(type=type(error).__name__,message=redact(str(error))[:2000])
    finally:
        cleanup_release.touch(exist_ok=True)
        if server is not None:row['resources']=server.stop();row['sanitized_native_log']=list(server.logs)
        provider.close();row['provider_requests']=provider.requests;row['fixture_ledger_raw']=ledger.read_text() if ledger.exists() else '';row['fixture_events']=read_ledger(ledger);row['input_files_unchanged']=all(hashlib.sha256(p.read_bytes()).hexdigest()==file_hashes[str(i)] for i,p in enumerate(files))
        row['finished_ns']=time.monotonic_ns();cpu_ended=resource.getrusage(resource.RUSAGE_SELF);row['observer_parent_cpu_seconds']=cpu_ended.ru_utime+cpu_ended.ru_stime-cpu_started.ru_utime-cpu_started.ru_stime
        row['fixture_errors']=[r.get('fixture_error') for r in provider.requests if r.get('fixture_error')];row['resources_complete']=row.get('resources',{}).get('complete',False)
    if condition=='mcp_batch_cancel' and 'cancel' in row:
        epoch=row['cancel']['received_ns'];row['old_task_requests_after_cancel']=[i for i,r in enumerate(provider.requests) if r['arrived_ns']>epoch and plan.marker in request_text(r['request']) and 'Generate the session title' not in request_text(r['request'])]
        row['handling_acceptance_met']=row['handling_acceptance_met'] and not row['old_task_requests_after_cancel']
        if not row['handling_acceptance_met']:row['product_outcome']='failure'
    if condition=='mcp_batch_failure':
        row['boundary_reached']=any(e['kind']=='failure_injected' and e.get('index')==2 for e in row['fixture_events'])
        if row['validity']=='valid' and not row['boundary_reached']:row['validity']='trigger_not_reached'
    task_requests=[r for r in provider.requests if plan.marker in request_text(r['request']) and 'Generate the session title' not in request_text(r['request'])]
    row['initial_input_values_absent']=not any(value in json.dumps(task_requests[0]['request']) for value in values) if task_requests else None
    row['independent_fixture_receipts_complete']=fixture_receipts_complete(row);row['handling_acceptance_met']=row['handling_acceptance_met'] and row['independent_fixture_receipts_complete']
    row['complete_record']=row['validity']=='valid' and row['resources_complete'] and row['input_files_unchanged'] and row['initial_input_values_absent'] is not False and not row['fixture_errors']
    return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=['pilot','formal'],default='pilot');p.add_argument('--admission',type=Path);args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native execution only on disposable hosted worker')
    versions={name:json.loads((args.runtime/'node_modules'/name/'package.json').read_bytes())['version'] for name in ('@deepseek-ai/dsh','openclaw')}
    if versions!={'@deepseek-ai/dsh':'0.2.2-alpha.2','openclaw':'2026.10.8'}:raise ValueError('Pinned native versions required')
    blocks=1 if args.phase=='pilot' else 2
    if args.phase=='formal':
        admission=json.loads(args.admission.read_bytes()) if args.admission else {}
        if admission.get('protocol_sha256')!=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest() or admission.get('complete_pilot') is not True:raise ValueError('Verified complete pilot admission required')
    args.output.mkdir(parents=True,exist_ok=True);report=dict(study='HD-MCP-01',phase=args.phase,protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],installed_versions=versions,started_ns=time.monotonic_ns(),results=[])
    path=args.output/'tool-lifecycle-report.json'
    with tempfile.TemporaryDirectory(prefix='tool-lifecycle-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for block in range(1,blocks+1):
            values=['TOOL_VALUE_'+uuid.uuid4().hex for _ in range(4)];controls={}
            for condition in CONDITIONS:
                for product in ('DSH','OpenClaw') if block%2 else ('OpenClaw','DSH'):
                    if condition in ('mcp_batch_failure','mcp_batch_cancel') and not all(controls.get((product,c)) for c in CONDITIONS[:4]):
                        report['results'].append(dict(product=product,condition=condition,block=block,validity='control_failed',handling_acceptance_met=False,complete_record=False));continue
                    root=Path(tmp)/(str(block)+'-'+product+'-'+condition);row=run_arm(product,condition,block,args.runtime,root,values);report['results'].append(row);controls[product,condition]=row['complete_record'] and row['handling_acceptance_met']
                    path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:row.get(k) for k in ('product','condition','block','validity','handling_acceptance_met','complete_record','adapter_error')}),flush=True)
        report['finished_ns']=time.monotonic_ns()
    report['cleanup']=dict(task_owned_roots_removed=True);report['complete_records']=len(report['results'])==12*blocks and all(r['complete_record'] for r in report['results']);path.write_text(json.dumps(report,indent=2)+'\n')
    if not report['complete_records']:raise SystemExit('Incomplete native tool-lifecycle comparison; retained original records')


if __name__=='__main__':main()
