#!/usr/bin/env python3
"""CTX-02 native bootstrap-budget/skill controls with independent task/resource evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import resource
import signal
import subprocess
import tempfile
import time
import uuid

from native_read_probe import Provider,schemas
from live_read_provider import LiveProvider,real_usage
from resource_collector import ResourceCollector

PROTOCOL=Path(__file__).with_name('context-skill-protocol.json')
SKILL='probe-codec'
RULE_PATTERN=re.compile(r'PROBE_CODEC_RULE\s+(\{[^\n]+\})')


def text_content(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return '\n'.join(text_content(v) for v in value)
    if isinstance(value,dict):return '\n'.join(text_content(value[k]) for k in ('text','content') if k in value)
    return ''


def request_text(body):
    return text_content(body.get('system',''))+'\n'+'\n'.join(text_content(m.get('content','')) for m in body.get('messages',[]))


def rule_from_text(text):
    for match in RULE_PATTERN.finditer(text):
        try:
            rule=json.loads(match[1])
            if set(rule)=={'prefix','factor','offset'} and isinstance(rule['factor'],int) and isinstance(rule['offset'],int) and isinstance(rule['prefix'],str):return rule
        except (ValueError,TypeError):continue
    return None


def skill_catalog(body):
    for block in re.findall(r'<available_skills>(.*?)</available_skills>',request_text(body),re.S):
        for entry in re.findall(r'<skill>(.*?)</skill>',block,re.S):
            if '<name>'+SKILL+'</name>' in entry:return entry
        if '`'+SKILL+'`' in block:return block
    return ''


def tool_results(body):
    values=[]
    for message in body.get('messages',[]):
        if message.get('role')=='tool':values.append(text_content(message.get('content','')))
        elif isinstance(message.get('content'),list):
            values.extend(text_content(b.get('content','')) for b in message['content'] if isinstance(b,dict) and b.get('type')=='tool_result')
    return values


def calls_from_requests(requests):
    calls={}
    for row in requests:
        for message in row['request'].get('messages',[]):
            for call in message.get('tool_calls',[]):
                try:args=json.loads(call.get('function',{}).get('arguments','{}'))
                except ValueError:args={}
                calls[call.get('id',str(len(calls)))]=dict(name=call.get('function',{}).get('name'),arguments=args)
            if isinstance(message.get('content'),list):
                for block in message['content']:
                    if isinstance(block,dict) and block.get('type')=='tool_use':calls[block.get('id',str(len(calls)))]=dict(name=block.get('name'),arguments=block.get('input',{}))
    return list(calls.values())


def native_skill_call(product,call,skill_file):
    if not isinstance(call.get('arguments'),dict):return False
    if product=='DSH':return call['name']=='skill' and call['arguments']=={'name':SKILL}
    if call['name']=='skills_read':return call['arguments']=={'name':SKILL}
    if call['name']!='read':return False
    path=call['arguments'].get('file_path',call['arguments'].get('path',''))
    return bool(path) and str(Path(path).expanduser().resolve())==str(skill_file.resolve())


def task_prompt(values):
    return ('Use the probe-codec workflow to encode the supplied values. If probe-codec is advertised in the native skill catalog, load it before reporting. '
        'The algorithm is checksum=(sum(values)*factor+offset)%997, with encoded equal to prefix + ":" + decimal checksum. '
        'Obtain prefix, factor and offset only from already supplied project instructions or the advertised skill. '
        'Do not read AGENTS.md directly, search files, run a shell, or invent missing parameters. '
        'If parameters remain unavailable, return null. Output only one JSON object with exactly the key encoded.\nVALUES_JSON='+json.dumps(values))


def encoded(rule,values):
    return rule['prefix']+':'+str((sum(values)*rule['factor']+rule['offset'])%997) if rule else None


def fixture_response(body,file_path,receipt,target_tool):
    text=request_text(body)
    if 'Generate the session title from this JSON array' in text:return dict(text='Codec report')
    values_match=re.search(r'VALUES_JSON=(\[[^\n]+\])',text)
    if not values_match:return dict(text='CALIBRATION_MISSING_INPUT_VALUES')
    values=json.loads(values_match[1]);catalog=skill_catalog(body);results=tool_results(body);available=schemas(body)
    if catalog and not results:
        if 'skill' in available:return dict(tool='skill',arguments=dict(name=SKILL))
        if 'skills_read' in available:return dict(tool='skills_read',arguments=dict(name=SKILL))
        location=re.search(r'<location>\s*(.*?)\s*</location>',catalog,re.S)
        if location and 'read' in available:
            props=available['read'].get('properties',{});key=next((k for k in ('file_path','path') if k in props),None)
            if key:return dict(tool='read',arguments={key:location[1]})
        return dict(text='CALIBRATION_CATALOG_WITHOUT_NATIVE_LOAD_ENTRY')
    return dict(text=json.dumps(dict(encoded=encoded(rule_from_text(text),values))))


def terminal_text(product,stdout):
    if product=='DSH':
        finals=[json.loads(line) for line in stdout.splitlines() if line.startswith('{') and json.loads(line).get('type')=='final']
        if len(finals)!=1:raise ValueError('Missing unambiguous native final event')
        return finals[0].get('text','')
    return '\n'.join(v.get('text','') for v in json.loads(stdout).get('payloads',[]))


def parse_delivery(product,stdout):
    try:
        text=terminal_text(product,stdout).strip()
        if text.startswith('```') and text.endswith('```'):
            text=re.sub(r'^```(?:json)?\s*','',text)[:-3].strip()
        value=json.loads(text)
        if isinstance(value,dict) and set(value)=={'encoded'} and (value['encoded'] is None or isinstance(value['encoded'],str)):return value
    except (ValueError,TypeError,KeyError):pass
    return None


def fixture_material(rule,priority=False):
    line='PROBE_CODEC_RULE '+json.dumps(rule,sort_keys=True)
    if priority:line='Required: '+line
    padding=''.join('Background detail '+str(i).zfill(4)+': synthetic reference material without report parameters.\n' for i in range(64))
    agents='# Project reference\nThis workspace supports the probe-codec reporting workflow.\n\n'+padding+'\n'+line+'\n\n'+padding+'\nEnd of background reference.\n'
    skill='---\nname: probe-codec\ndescription: Encode supplied integer values into the project codec report.\n---\n# Project codec\n'+line+'\nCompute checksum=(sum(values)*factor+offset)%997 and output {"encoded":"prefix:checksum"}.\n\n'+padding
    return agents,skill


def manifest(paths):return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_arm(product,runtime,root,condition,block,values,rule,live,sequence,limits):
    workspace=root/'workspace';workspace.mkdir();(workspace/'.git').mkdir()
    skill_root=workspace/'.agents/skills';skill_dir=skill_root/SKILL;skill_dir.mkdir(parents=True)
    agents,skill=fixture_material(rule,condition['rule_line']=='required_keyword')
    agents_file=workspace/'AGENTS.md';agents_file.write_text(agents);skill_file=skill_dir/'SKILL.md';skill_file.write_text(skill)
    before_files=manifest([agents_file,skill_file]);limit=limits[condition['budget']]
    provider=LiveProvider(skill_file,rule['prefix']) if live else Provider(skill_file,rule['prefix'],decision_fn=fixture_response)
    env=dict(os.environ);env.pop('DEEPSEEK_API_KEY',None)
    prompt=task_prompt(values)
    config_paths=[]
    if product=='DSH':
        state=root/'dsh-home';state.mkdir();patch=root/'context.patch.yml'
        patch.write_text('- id: agent-instructions\n  config:\n    maxBytes: '+str(limit)+'\n'
            '- id: skill-filesystem\n  config:\n    includeDefaultRoots: false\n    watch: false\n    customSkillDirs: '+json.dumps([str(skill_root)] if condition['skill'] else [])+'\n'
            '- id: llm-deepseek\n  config:\n    thinking: disabled\n    reasoningEffort: off\n    maxTokens: 2048\n'
            '- id: session-title-llm\n  config:\n    maxOutputTokens: 2048\n')
        config_paths=[patch]
        env.update(DSH_HOME=str(state),DSH_PERMISSION_MODE='read-only',DEEPSEEK_BASE_URL=provider.base,DEEPSEEK_API_KEY='synthetic-only')
        command=[str(runtime/'node_modules/.bin/dsh'),'--profile','headless','--patch',str(patch),'--json',prompt]
    else:
        state=root/'openclaw-state';state.mkdir();config=root/'openclaw.json'
        for name in ('SOUL.md','TOOLS.md','IDENTITY.md','USER.md','HEARTBEAT.md','BOOTSTRAP.md'):(workspace/name).write_text('')
        config.write_text(json.dumps(dict(gateway=dict(mode='local',auth=dict(mode='token',token='synthetic-only')),
            models=dict(providers=dict(fixture=dict(baseUrl=provider.base,apiKey='synthetic-only',api='openai-completions',models=[dict(id='deepseek-flash' if live else 'fixture-model',name='Context fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=2048)]))),
            agents=dict(defaults=dict(workspace=str(workspace),model=dict(primary='fixture/'+('deepseek-flash' if live else 'fixture-model')),skipBootstrap=True,thinkingDefault='off',bootstrapMaxChars=limit,bootstrapTotalMaxChars=65536)),
            skills=dict(allowBundled=[SKILL],entries={SKILL:dict(enabled=condition['skill'])}),tools=dict(allow=['read'],toolSearch=False),cron=dict(enabled=False))))
        config_paths=[config];env.update(OPENCLAW_STATE_DIR=str(state),OPENCLAW_CONFIG_PATH=str(config))
        command=[str(runtime/'node_modules/.bin/openclaw'),'agent','--local','--session-id',str(uuid.uuid4()),'--json','--message',prompt]
    before_self=resource.getrusage(resource.RUSAGE_SELF);collector=ResourceCollector(dict(workspace=workspace,product_state=state))
    start=time.monotonic_ns();child=None;stdout=stderr='';exit_code=None;adapter_error=None
    try:
        child=subprocess.Popen(collector.command(command),env=env,cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        stdout,stderr=child.communicate(timeout=None if live else 120);exit_code=child.returncode
    except subprocess.TimeoutExpired as error:
        adapter_error='Synthetic protocol settlement safeguard exceeded; adapter failure, not product quality'
        stdout=error.output.decode(errors='replace') if isinstance(error.output,bytes) else error.output or ''
        stderr=error.stderr.decode(errors='replace') if isinstance(error.stderr,bytes) else error.stderr or ''
    finally:
        process_exit_ns=time.monotonic_ns()
        if child is not None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
        delivery=parse_delivery(product,stdout);unchanged=manifest([agents_file,skill_file])==before_files
        checked_ns=time.monotonic_ns();resources=collector.finish();provider.close();after_self=resource.getrusage(resource.RUSAGE_SELF)
    requests=provider.requests;task_requests=[r for r in requests if 'Generate the session title from this JSON array' not in request_text(r['request'])]
    first=task_requests[0]['request'] if task_requests else {};actual_calls=calls_from_requests(requests)
    permitted=lambda c:native_skill_call(product,c,skill_file)
    returned_names=[name for r in requests for name in (r.get('tool_names',[]) if live else [r['decision']['tool']] if r.get('decision',{}).get('tool') else [])]
    arguments_complete=len(actual_calls)==len(returned_names)
    constraints=all(permitted(c) and condition['skill'] for c in actual_calls) if arguments_complete else None
    load_attempt=any(permitted(c) for c in actual_calls)
    adopted=any(rule['prefix'] in result for r in task_requests for result in tool_results(r['request']))
    initial_rule=rule['prefix'] in request_text(first);catalog_visible=bool(skill_catalog(first));expected_initial=condition['budget']=='ample' or (product=='OpenClaw' and condition['rule_line']=='required_keyword')
    correct=delivery is not None and delivery['encoded']==encoded(rule,values)
    delivered=exit_code==0 and delivery is not None and unchanged
    expected_delivery=encoded(rule,values) if expected_initial or condition['skill'] else None
    calibration_valid=delivered and constraints and initial_rule==expected_initial and catalog_visible==condition['skill'] and (not condition['skill'] or load_attempt and adopted) and delivery['encoded']==expected_delivery and resources['complete']
    result=dict(study_id='CTX-02',product=product,block=block,condition=condition,sequence=sequence,live_model=live,
        config_sha256=manifest(config_paths),input_sha256=before_files,task_values=values,rule=rule,rule_absent_from_user_prompt=rule['prefix'] not in prompt,
        instruction_limit=limit,source_agents_bytes=len(agents.encode()),source_skill_bytes=len(skill.encode()),
        exit_code=exit_code,adapter_error=adapter_error,stdout=stdout[-30000:],stderr=stderr[-8000:],
        observed=dict(rule_visible_initial=initial_rule,skill_catalog_visible=catalog_visible,native_skill_load_attempt=load_attempt,rule_adopted_from_tool=adopted,actual_tool_calls=actual_calls,issued_tool_names=returned_names,tool_arguments_observed=arguments_complete),
        context_payload_bytes=dict(initial_text_utf8=len(request_text(first).encode()),request_text_utf8=[len(request_text(r['request']).encode()) for r in task_requests],meaning='Native textual payload bytes; not component token counts'),
        expected_initial_rule_visible=expected_initial,delivered=delivered,quality_correct=correct,constraints_satisfied=constraints,delivery=delivery,inputs_unchanged=unchanged,
        process_exit_ms=(process_exit_ns-start)/1e6,independent_delivery_check_ms=(checked_ns-start)/1e6,
        timestamps=dict(submission_ns=start,process_exit_ns=process_exit_ns,independent_check_ns=checked_ns),resources=resources,
        observer_process_cpu_seconds=(after_self.ru_utime+after_self.ru_stime-before_self.ru_utime-before_self.ru_stime),
        observer_memory_reader_cpu_seconds=resources['memory_reader_cpu_seconds'],
        observer_cpu_scope='Controller, relay and collector process including sampling thread; memory-reader command is separate and disjoint; sampling-thread CPU overlaps parent CPU and is never added again',
        provider_request_count=len(requests),provider_requests=requests,provider_errors=getattr(provider,'errors',[]),
        token_usage=real_usage(requests) if live else dict(synthetic=True,actual_tokens=None),calibration_valid=calibration_valid)
    if product=='OpenClaw':
        try:
            metadata=json.loads(stdout)['meta'];result['native_metadata']={k:metadata.get(k) for k in ('systemPromptReport','toolSummary','completion','replayInvalid','requestShaping','agentMeta')}
        except (ValueError,KeyError):pass
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--live-model',action='store_true');p.add_argument('--calibration-report',type=Path);args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native execution requires a disposable hosted worker')
    protocol=json.loads(PROTOCOL.read_text());protocol_sha=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    versions={name:json.loads((args.runtime/'node_modules'/name/'package.json').read_text())['version'] for name in ('@deepseek-ai/dsh','openclaw')}
    if versions!={'@deepseek-ai/dsh':'0.2.2-alpha.2','openclaw':'2026.10.8'}:raise ValueError('Pinned runtime version mismatch')
    if args.live_model:
        if args.calibration_report is None:raise ValueError('Live study requires retained successful calibration for this protocol')
        calibration=json.loads(args.calibration_report.read_text())
        if calibration['protocol_sha256']!=protocol_sha or not all(r['calibration_valid'] for r in calibration['results']):raise ValueError('Calibration gate not passed for this protocol')
    args.output.mkdir(parents=True,exist_ok=True);seed=int.from_bytes(os.urandom(8),'big');rng=random.Random(seed);results=[];sequence=0
    blocks=protocol['real_model_blocks'] if args.live_model else protocol['calibration_blocks']
    report=dict(study_id='CTX-02',protocol_sha256=protocol_sha,controller_commit=os.environ.get('GITHUB_SHA'),run_id=os.environ.get('GITHUB_RUN_ID'),
        native_execution=True,formal_parent_studies_complete=False,live_model=args.live_model,installed_versions=versions,
        package_lock_sha256=hashlib.sha256((args.runtime/'package-lock.json').read_bytes()).hexdigest(),ordering_seed=seed,blocks=blocks,results=results)
    with tempfile.TemporaryDirectory(prefix='ctx-skill-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for block in range(1,blocks+1):
            rule=dict(prefix='pc_'+uuid.uuid4().hex,factor=rng.randrange(2,10),offset=rng.randrange(11,98));values=[rng.randrange(10,90) for _ in range(3)]
            arms=[(product,condition) for product in protocol['products'] for condition in protocol['conditions']];rng.shuffle(arms)
            for product,condition in arms:
                root=Path(tmp)/(str(block)+'-'+product+'-'+condition['id']);root.mkdir();sequence+=1
                row=run_arm(product,args.runtime,root,condition,block,values,rule,args.live_model,sequence,protocol['instruction_limits']);results.append(row)
                (args.output/'context-skill-report.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps({k:row[k] for k in ('product','block','sequence','calibration_valid','delivered','quality_correct','constraints_satisfied','observed')}),flush=True)
    report['cleanup_observation']=dict(task_roots_removed=True,retained_task_root_bytes=0,exported_evidence_excluded=True)
    (args.output/'context-skill-report.json').write_text(json.dumps(report,indent=2)+'\n')
    if not args.live_model and not all(r['calibration_valid'] for r in results):raise SystemExit('CTX-02 adapter/control calibration failed; inspect retained partial/failed evidence')
    if args.live_model and any(r['adapter_error'] or not r['resources']['complete'] for r in results):raise SystemExit('CTX-02 adapter/resource collection incomplete; task quality failures are separately retained')

if __name__=='__main__':main()
