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


def schemas(body):
    return {t.get('function',t)['name']:t.get('function',t).get('parameters',t.get('input_schema',{})) for t in body.get('tools',[]) if 'name' in t.get('function',t)}


def choose_response(body, file_path, receipt):
    messages=body.get('messages',[])
    results=[m for m in messages if m.get('role')=='tool' or (isinstance(m.get('content'),list) and any(v.get('type')=='tool_result' for v in m['content'] if isinstance(v,dict)))]
    visible=receipt in json.dumps(results)
    if visible:return dict(text='VERIFIED:'+receipt)
    available=schemas(body)
    if 'read' not in available:return dict(text='CALIBRATION_MISSING_NATIVE_READ')
    props=available['read'].get('properties',{})
    key=next((k for k in ('file_path','path') if k in props),None)
    if key is None:return dict(text='CALIBRATION_UNSUPPORTED_READ_SCHEMA')
    if results:return dict(text='CALIBRATION_TOOL_RESULT_WITHOUT_RECEIPT')
    return dict(tool='read',arguments={key:str(file_path)})


class Provider:
    def __init__(self, file_path, receipt):
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
                body=json.loads(self.rfile.read(size));decision=choose_response(body,owner.file_path,owner.receipt)
                owner.requests.append(dict(monotonic_ns=time.monotonic_ns(),endpoint=self.path,
                    schemas=schemas(body),request=body,decision=decision))
                if len(owner.requests)>10:self.send_error(429);return
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


def run_product(product,runtime,root):
    workspace=root/'workspace';workspace.mkdir();input_file=workspace/'receipt.txt'
    receipt='OWNED_NATIVE_READ_'+uuid.uuid4().hex;input_file.write_text(receipt+'\n')
    original=hashlib.sha256(input_file.read_bytes()).hexdigest()
    provider=Provider(input_file,receipt);env=dict(os.environ)
    # Synthetic launch-time credentials and task-owned product roots.
    prompt=f'NATIVE_READ_CALIBRATION: Use the native read tool to read {input_file}, then report its exact content.'
    if product=='DSH':
        home=root/'dsh-home';home.mkdir();env.update(DSH_HOME=str(home),DEEPSEEK_BASE_URL=provider.base,DEEPSEEK_API_KEY='synthetic-only',DSH_PERMISSION_MODE='read-only')
        command=[str(runtime/'node_modules/.bin/dsh'),'--profile','headless','--json',prompt]
    else:
        state=root/'openclaw-state';state.mkdir();config=root/'openclaw.json'
        config.write_text(json.dumps(dict(gateway=dict(mode='local',auth=dict(mode='token',token='synthetic-only')),
            models=dict(providers=dict(fixture=dict(baseUrl=provider.base,apiKey='synthetic-only',api='openai-completions',models=[dict(id='fixture-model',name='Native read fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=1024)]))),
            agents=dict(defaults=dict(workspace=str(workspace),model=dict(primary='fixture/fixture-model'),skipBootstrap=True,thinkingDefault='off')),
            tools=dict(allow=['read'],toolSearch=False),cron=dict(enabled=False))))
        env.update(OPENCLAW_STATE_DIR=str(state),OPENCLAW_CONFIG_PATH=str(config))
        command=[str(runtime/'node_modules/.bin/openclaw'),'agent','--local','--session-id',str(uuid.uuid4()),'--json','--message',prompt]
    start=time.monotonic_ns();before=resource.getrusage(resource.RUSAGE_CHILDREN)
    result={};child=None
    try:
        child=subprocess.Popen(command,env=env,cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        stdout,stderr=child.communicate(timeout=120)
        result.update(exit_code=child.returncode,stdout=stdout[-20000:],stderr=stderr[-8000:])
    except subprocess.TimeoutExpired:
        result.update(exit_code=None,adapter_error='native read calibration did not settle within the declared 120-second handshake safeguard')
    finally:
        if child is not None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
        end=time.monotonic_ns();after=resource.getrusage(resource.RUSAGE_CHILDREN);provider.close()
    visible=any(v['decision'].get('text')=='VERIFIED:'+receipt for v in provider.requests)
    native_attempt=any(v['decision'].get('tool')=='read' for v in provider.requests)
    final_receipt=('VERIFIED:'+receipt) in result.get('stdout','')
    unchanged=hashlib.sha256(input_file.read_bytes()).hexdigest()==original
    result.update(product=product,phase='adapter-calibration-only',paid_model_calls=0,
        receipt_was_absent_from_initial_prompt=receipt not in prompt,native_read_requested=native_attempt,
        receipt_observed_in_tool_result=visible,receipt_observed_in_final_output=final_receipt,input_unchanged=unchanged,
        valid=result.get('exit_code')==0 and visible and native_attempt and final_receipt and unchanged,
        invocation_wall_ms=(end-start)/1e6,child_cpu_user_seconds=after.ru_utime-before.ru_utime,
        child_cpu_system_seconds=after.ru_stime-before.ru_stime,
        provider_request_count=len(provider.requests),provider_requests=provider.requests,
        resource_limitations='CPU is invocation children rusage, not per-stage attribution. Full cgroup/PSS/disk collectors and same-operation extension control are pending. Synthetic usage is not real token cost.',
        file_sha256=original,configuration='DSH shipped headless read-only; OpenClaw local native read-only tool allowlist with public direct-schema setting')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
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
            root=Path(tmp)/product;root.mkdir();results.append(run_product(product,args.runtime,root))
    report=dict(kind='two-product-native-read-calibration',run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),formal_new_experiments=False,installed_versions=versions,package_lock_sha256=lock_sha256,results=results)
    raw=json.dumps(report,indent=2).encode()
    if len(raw)>4*1024**2:raise ValueError('Compact calibration report bound exceeded')
    (args.output/'native-read-calibration.json').write_bytes(raw)
    print(json.dumps([dict(product=r['product'],valid=r['valid'],exit_code=r['exit_code'],requests=r['provider_request_count']) for r in results]))
    if not all(r['valid'] for r in results):raise SystemExit('Native adapter calibration incomplete; inspect retained report')

if __name__=='__main__':main()
