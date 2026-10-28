#!/usr/bin/env python3
"""Hosted native file-read adapter calibration; deterministic provider, no real model calls."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from resource_collector import ResourceCollector


def schemas(body):
    return {t.get('function',t)['name']:t.get('function',t).get('parameters',t.get('input_schema',{})) for t in body.get('tools',[]) if 'name' in t.get('function',t)}


def choose_response(body, file_path, receipt, target_tool='read'):
    messages=body.get('messages',[])
    results=[m for m in messages if m.get('role')=='tool' or (isinstance(m.get('content'),list) and any(v.get('type')=='tool_result' for v in m['content'] if isinstance(v,dict)))]
    visible=receipt in json.dumps(results)
    if visible:return dict(text='VERIFIED:'+receipt)
    available=schemas(body)
    if target_tool not in available:return dict(text='CALIBRATION_MISSING_NATIVE_READ')
    if target_tool!='read':
        if results:return dict(text='CALIBRATION_EXTENSION_WITHOUT_RECEIPT')
        return dict(tool=target_tool,arguments={})
    props=available['read'].get('properties',{})
    key=next((k for k in ('file_path','path') if k in props),None)
    if key is None:return dict(text='CALIBRATION_UNSUPPORTED_READ_SCHEMA')
    if results:return dict(text='CALIBRATION_TOOL_RESULT_WITHOUT_RECEIPT')
    return dict(tool=target_tool,arguments={key:str(file_path)})


class Provider:
    def __init__(self, file_path, receipt, target_tool='read', decision_fn=None,max_requests=10):
        self.file_path=file_path;self.receipt=receipt;self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                data=json.dumps(dict(object='list',data=[dict(id='fixture-model',object='model')])).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_POST(self):
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4*1024**2:self.send_error(413);return
                body=json.loads(self.rfile.read(size));decision=(decision_fn or choose_response)(body,owner.file_path,owner.receipt,target_tool)
                owner.requests.append(dict(monotonic_ns=time.monotonic_ns(),endpoint=self.path,
                    schemas=schemas(body),request=body,decision=decision))
                if len(owner.requests)>max_requests:self.send_error(429);return
                anthropic=self.path.endswith('/messages');call=decision.get('tool')
                text=decision.get('text','');callid='read_calibration_'+str(len(owner.requests))
                if anthropic:
                    content=[dict(type='tool_use',id=callid,name=call,input=decision['arguments'])] if call else [dict(type='text',text=text)]
                    message=dict(id=callid,type='message',role='assistant',model='fixture-model',content=content,
                        stop_reason='tool_use' if call else 'end_turn',stop_sequence=None,usage=dict(input_tokens=1,output_tokens=1))
                    if not body.get('stream'):
                        raw=json.dumps(message).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw);return
                    start_block=dict(type='tool_use',id=callid,name=call,input={}) if call else dict(type='text',text='')
                    delta=dict(type='input_json_delta',partial_json=json.dumps(decision['arguments'])) if call else dict(type='text_delta',text=text)
                    events=[('message_start',dict(type='message_start',message={**message,'content':[],'stop_reason':None,'usage':dict(input_tokens=1,output_tokens=0)})),
                            ('content_block_start',dict(type='content_block_start',index=0,content_block=start_block)),
                            ('content_block_delta',dict(type='content_block_delta',index=0,delta=delta)),
                            ('content_block_stop',dict(type='content_block_stop',index=0)),
                            ('message_delta',dict(type='message_delta',delta=dict(stop_reason=message['stop_reason'],stop_sequence=None),usage=dict(output_tokens=1))),
                            ('message_stop',dict(type='message_stop'))]
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for event,data in events:self.wfile.write(('event: '+event+'\ndata: '+json.dumps(data)+'\n\n').encode())
                else:
                    msg=dict(role='assistant',content=None if call else text)
                    if call:msg['tool_calls']=[dict(id=callid,type='function',function=dict(name=call,arguments=json.dumps(decision['arguments'])))]
                    finish='tool_calls' if call else 'stop'
                    if not body.get('stream'):
                        data=dict(id=callid,object='chat.completion',created=int(time.time()),model='fixture-model',choices=[dict(index=0,message=msg,finish_reason=finish)],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
                        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(data).encode());return
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    delta=dict(msg)
                    if call:delta['tool_calls']=[dict(index=0,**msg['tool_calls'][0])]
                    for part,reason in [(delta,None),({},finish)]:
                        data=dict(id=callid,object='chat.completion.chunk',created=int(time.time()),model='fixture-model',choices=[dict(index=0,delta=part,finish_reason=reason)])
                        self.wfile.write(('data: '+json.dumps(data)+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    @property
    def base(self):return f'http://127.0.0.1:{self.server.server_port}/v1'
    def close(self):self.server.shutdown();self.server.server_close()


def final_receipt_matches(product,stdout,receipt):
    """Read the actual terminal field; diagnostic/tool text cannot satisfy completion."""
    try:
        if product=='DSH':
            finals=[json.loads(line).get('text','') for line in stdout.splitlines() if line.startswith('{') and json.loads(line).get('type')=='final']
            if len(finals)!=1:return False
            text=finals[0]
        else:
            payload=json.loads(stdout).get('payloads',[])
            text='\n'.join(v.get('text','') for v in payload)
    except (ValueError,TypeError,AttributeError):return False
    prefix='VERIFIED:'
    return text.startswith(prefix) and text[len(prefix):].strip()==receipt


def run_product(product,runtime,root,route='native',live=False):
    workspace=root/'workspace';workspace.mkdir();input_file=workspace/'receipt.txt'
    receipt='OWNED_NATIVE_READ_'+uuid.uuid4().hex;input_file.write_text(receipt+'\n')
    original=hashlib.sha256(input_file.read_bytes()).hexdigest()
    target_tool='read' if route=='native' else ('mcp__probe__eval_read' if product=='DSH' else 'probe__eval_read')
    if live:
        from live_read_provider import LiveProvider
        provider=LiveProvider(input_file,receipt,target_tool)
    else:provider=Provider(input_file,receipt,target_tool)
    env=dict(os.environ);env.pop('DEEPSEEK_API_KEY',None)
    ledger=root/'mcp-ledger.jsonl'
    fixture=Path(__file__).with_name('read_mcp_fixture.py').resolve()
    # Synthetic launch-time credentials and task-owned product roots.
    prompt=f'Read {input_file} with {target_tool}. Reply exactly VERIFIED: followed by the file content, without extra text.'
    if product=='DSH':
        home=root/'dsh-home';home.mkdir();env.update(DSH_HOME=str(home),DEEPSEEK_BASE_URL=provider.base,DEEPSEEK_API_KEY='synthetic-only',DSH_PERMISSION_MODE='read-only')
        command=[str(runtime/'node_modules/.bin/dsh'),'--profile','headless']
        if route=='mcp':
            patch=root/'mcp.patch.yml'
            patch.write_text('- insert:\n    - id: probe-mcp\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: probe\n        transport: stdio\n        command: /usr/bin/python3\n        args: '+json.dumps([str(fixture),'--file',str(input_file),'--ledger',str(ledger)])+'\n        failOnStartupError: true\n')
            command+=['--patch',str(patch)]
        command+=['--json',prompt]
    else:
        state=root/'openclaw-state';state.mkdir();config=root/'openclaw.json'
        config.write_text(json.dumps(dict(gateway=dict(mode='local',auth=dict(mode='token',token='synthetic-only')),
            models=dict(providers=dict(fixture=dict(baseUrl=provider.base,apiKey='synthetic-only',api='openai-completions',models=[dict(id='deepseek-flash' if live else 'fixture-model',name='Native read fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=1024)]))),
            agents=dict(defaults=dict(workspace=str(workspace),model=dict(primary='fixture/'+('deepseek-flash' if live else 'fixture-model')),skipBootstrap=True,thinkingDefault='off')),
            tools=dict(allow=['read'],toolSearch=False),cron=dict(enabled=False))))
        if route=='mcp':
            current=json.loads(config.read_text())
            current['mcp']=dict(servers=dict(probe=dict(transport='stdio',command='/usr/bin/python3',args=[str(fixture),'--file',str(input_file),'--ledger',str(ledger)],supportsParallelToolCalls=True,requestTimeoutMs=10000)))
            current['tools']['allow']=[target_tool]
            config.write_text(json.dumps(current))
        env.update(OPENCLAW_STATE_DIR=str(state),OPENCLAW_CONFIG_PATH=str(config))
        command=[str(runtime/'node_modules/.bin/openclaw'),'agent','--local','--session-id',str(uuid.uuid4()),'--json','--message',prompt]
    collector=ResourceCollector(dict(workspace=workspace,product_state=home if product=='DSH' else state,extension_ledger=ledger))
    start=time.monotonic_ns();before=resource.getrusage(resource.RUSAGE_CHILDREN)
    result={};child=None
    try:
        child=subprocess.Popen(collector.command(command),env=env,cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        stdout,stderr=child.communicate(timeout=None if live else 120)
        result.update(exit_code=child.returncode,stdout=stdout[-20000:],stderr=stderr[-8000:])
    except subprocess.TimeoutExpired:
        result.update(exit_code=None,adapter_error='native read calibration did not settle within the declared 120-second handshake safeguard')
    finally:
        if child is not None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
        end=time.monotonic_ns();after=resource.getrusage(resource.RUSAGE_CHILDREN)
        measured_resources=collector.finish();provider.close()
    if live:
        from live_read_provider import tool_names,real_usage
        visible=any(choose_response(v['request'],input_file,receipt,target_tool).get('text')=='VERIFIED:'+receipt for v in provider.requests)
        native_attempt=any(target_tool in tool_names(v['request']) or target_tool in v['tool_names'] for v in provider.requests)
    else:
        visible=any(v['decision'].get('text')=='VERIFIED:'+receipt for v in provider.requests)
        native_attempt=any(v['decision'].get('tool')==target_tool for v in provider.requests)
    final_receipt=final_receipt_matches(product,result.get('stdout',''),receipt)
    unchanged=hashlib.sha256(input_file.read_bytes()).hexdigest()==original
    mcp_events=[json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    result.update(product=product,route=route,target_tool=target_tool,mcp_events=mcp_events,phase='live-read-pilot' if live else 'adapter-calibration-only',paid_model_calls=len(provider.requests) if live else 0,
        receipt_was_absent_from_initial_prompt=receipt not in prompt,native_read_requested=native_attempt,
        receipt_observed_in_tool_result=visible,receipt_observed_in_final_output=final_receipt,input_unchanged=unchanged,
        valid=result.get('exit_code')==0 and visible and native_attempt and final_receipt and unchanged and (route=='native' or len(mcp_events)==1),
        invocation_wall_ms=(end-start)/1e6,child_cpu_user_seconds=after.ru_utime-before.ru_utime,
        child_cpu_system_seconds=after.ru_stime-before.ru_stime,
        provider_request_count=len(provider.requests),provider_requests=provider.requests,
        resources=measured_resources,resource_collection_valid=measured_resources['complete'],
        token_usage=dict(synthetic=True,real_provider_tokens=None,actual_charge=None,
            request_json_bytes=[len(json.dumps(v['request']).encode()) for v in provider.requests],
            method='Synthetic provider reports protocol fixture counters only; request bytes are payload size, not tokens'),
        resource_limitations='Cgroup includes product and inherited MCP/tool processes. Observer and synthetic model server are outside. Shared installation is excluded. Synthetic usage is not real token cost; calibration timings are not a product ranking.',
        file_sha256=original,configuration='DSH shipped headless read-only; OpenClaw local native read-only tool allowlist with public direct-schema setting')
    if live:
        result['token_usage']=real_usage(provider.requests)
        result['provider_errors']=provider.errors
        result['configuration']+='; native default protocol/settings retained; DSH thinking enabled/high, OpenClaw thinking off; not a matched performance contrast'
        result['resource_limitations']='Single live pilot per arm, fixed order, product-specific contexts/protocols/thinking; no statistical or cross-product performance claim. Component token attribution and invoice cost remain unavailable.'
    result['acceptance_and_resource_valid']=result['valid'] and result['resource_collection_valid']
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--live-model',action='store_true');args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native execution requires a disposable hosted worker')
    args.output.mkdir(parents=True,exist_ok=True);results=[]
    versions={}
    for package,expected in [('@deepseek-ai/dsh','0.2.2-alpha.2'),('openclaw','2026.10.8')]:
        installed=json.loads((args.runtime/'node_modules'/package/'package.json').read_text())
        if installed['version']!=expected:raise ValueError('Installed product version mismatch: '+package)
        versions[package]=installed['version']
    lock_sha256=hashlib.sha256((args.runtime/'package-lock.json').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='native-read-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for product in ('DSH','OpenClaw'):
            for route in ('native','mcp'):
                root=Path(tmp)/(product+'-'+route);root.mkdir();results.append(run_product(product,args.runtime,root,route,live=args.live_model))
    report=dict(kind='two-product-native-read-calibration',run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),formal_new_experiments=False,live_model_pilot=args.live_model,installed_versions=versions,package_lock_sha256=lock_sha256,results=results)
    report['cleanup_observation']=dict(task_owned_roots_removed=True,retained_task_root_allocated_bytes=0,
        observer_output_excluded=True,method='TemporaryDirectory exited before report serialization; installation and exported evidence are separate paths')
    raw=json.dumps(report,indent=2).encode()
    if len(raw)>16*1024**2:raise ValueError('Compact calibration report bound exceeded')
    (args.output/'native-read-calibration.json').write_bytes(raw)
    print(json.dumps([dict(product=r['product'],route=r['route'],valid=r['valid'],exit_code=r['exit_code'],requests=r['provider_request_count']) for r in results]))
    if not all(r['acceptance_and_resource_valid'] for r in results):raise SystemExit('Native adapter calibration incomplete; inspect retained report')

if __name__=='__main__':main()
