#!/usr/bin/env python3
"""Hosted native server/API calibration for PA fault-domain work; no paid model."""
import argparse
from collections import deque
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid
from native_read_probe import Provider
from context_skill_probe import request_text
from resource_collector import ResourceCollector
from export_read_metrics import request_stage

MARKER=re.compile(r'PLATFORM_INPUT_[a-f0-9]{32}')


def fixture_response(body,file_path,receipt,target_tool):
    text=request_text(body)
    if 'Generate the session title from this JSON array' in text:return dict(text='Platform calibration')
    markers=MARKER.findall(text)
    return dict(text='PLATFORM_ACK:'+markers[-1] if markers else 'CALIBRATION_MISSING_MARKER')


def fresh_session_bindings(product,tasks,requests):
    """Calibrate native identities and disjoint contexts, not just client-minted IDs."""
    task_requests=[r for r in requests if request_stage(r)!='auxiliary_session_title']
    rows=[]
    for task in tasks:
        reached=[r['request'] for r in task_requests if task['marker'] in request_text(r['request'])]
        disjoint=bool(reached) and all(other['marker'] not in request_text(body) for body in reached for other in tasks if other is not task)
        # DSH returns the identity from native session.create. OpenClaw must
        # additionally show the routed key in its native Runtime projection. The
        # submitted HTTP message is only a validated random marker; it cannot
        # itself contain that projection (which is appended in a user-role block).
        native_key=task['session_id'] if product=='DSH' else task['session_key']
        native_visible=product=='DSH' or any(re.search(r'(?m)^Runtime: agent=main \| session='+re.escape(native_key)+r' \|',request_text(body)) for body in reached)
        rows.append(dict(native_identity=native_key,matching_task_requests=len(reached),disjoint_context=disjoint,native_identity_confirmed=native_visible))
    valid=len(tasks)==2 and all(MARKER.fullmatch(t['marker']) for t in tasks) and len({r['native_identity'] for r in rows})==2 and all(r['matching_task_requests']==1 and r['disjoint_context'] and r['native_identity_confirmed'] for r in rows)
    return dict(valid=valid,sessions=rows)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def redact(text):return re.sub(r'([?&]token=)[^\s)]+',r'\1<redacted>',text)


class NativeServer:
    def __init__(self,product,runtime,root,provider):
        self.product=product;self.root=root;self.port=free_port();self.launch_url=None;self.logs=deque(maxlen=150)
        self.workspace=root/'workspace';self.workspace.mkdir();(self.workspace/'.git').mkdir()
        self.state=root/'state';self.state.mkdir();env=dict(os.environ);env.pop('DEEPSEEK_API_KEY',None)
        if product=='DSH':
            patch=root/'server.patch.yml';patch.write_text('- id: llm-deepseek\n  config:\n    thinking: disabled\n    reasoningEffort: off\n    maxTokens: 2048\n')
            env.update(DSH_HOME=str(self.state),DSH_AGENTS_HOME=str(root/'.agents'),DSH_TELEMETRY_DISABLED='1',
                DEEPSEEK_BASE_URL=provider.base,DEEPSEEK_API_KEY='synthetic-only',DSH_PERMISSION_MODE='read-only')
            command=[str(runtime/'node_modules/.bin/dsh'),'--profile','web','--patch',str(patch),'--no-open','--host','127.0.0.1','--port',str(self.port)]
        else:
            config=root/'openclaw.json';config.write_text(json.dumps(dict(gateway=dict(mode='local',auth=dict(mode='token',token='synthetic-platform-only'),
                http=dict(endpoints=dict(chatCompletions=dict(enabled=True)))),
                models=dict(providers=dict(fixture=dict(baseUrl=provider.base,apiKey='synthetic-only',api='openai-completions',models=[dict(id='fixture-model',name='Platform fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=2048)]))),
                agents=dict(defaults=dict(workspace=str(self.workspace),model=dict(primary='fixture/fixture-model'),skipBootstrap=True,thinkingDefault='off')),
                tools=dict(allow=['read'],toolSearch=False),cron=dict(enabled=False))))
            env.update(OPENCLAW_STATE_DIR=str(self.state),OPENCLAW_CONFIG_PATH=str(config),OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
            command=[str(runtime/'node_modules/.bin/openclaw'),'gateway','run','--bind','loopback','--port',str(self.port)]
        self.command=command;self.collector=ResourceCollector(dict(workspace=self.workspace,product_state=self.state));self.started_ns=time.monotonic_ns()
        self.process=subprocess.Popen(self.collector.command(command),env=env,cwd=self.workspace,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        self.reader=threading.Thread(target=self.read_log,daemon=True);self.reader.start();self.cookie=None

    def read_log(self):
        for line in self.process.stdout:
            found=re.search(r'dsh web: (http://[^\s]+)',line)
            if found:self.launch_url=found[1]
            self.logs.append(redact(line)[:2400])

    def http(self,method,path,body=None,headers=None,timeout=60):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=timeout)
        try:
            connection.request(method,path,body,headers or {});response=connection.getresponse();data=response.read()
            return response.status,{k.lower():v for k,v in response.getheaders()},data
        finally:connection.close()

    def ready(self):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise RuntimeError('Native server exited before ready; inspect sanitized native log')
            try:
                if self.product=='OpenClaw':
                    status,headers,body=self.http('GET','/readyz',timeout=.5)
                    if status==200:self.ready_ns=time.monotonic_ns();return
                elif self.launch_url:
                    url=urllib.parse.urlsplit(self.launch_url)
                    status,headers,body=self.http('GET',url.path+'?'+url.query,timeout=2)
                    if status not in (302,303) or 'set-cookie' not in headers:raise RuntimeError('Native browser launch-token exchange failed')
                    self.cookie=headers['set-cookie'].split(';',1)[0]
                    self.ready_ns=time.monotonic_ns();return
            except (OSError,http.client.HTTPException):pass
            time.sleep(.1)
        raise RuntimeError('Declared 90-second native startup handshake safeguard exceeded')

    def rpc(self,method,args):
        identifier=str(uuid.uuid4());body=json.dumps(dict(type='client-request',rpcId=identifier,method=method,payload=dict(args=args)))
        status,headers,raw=self.http('POST','/api/'+method,body,{'Content-Type':'application/json','Cookie':self.cookie})
        if status!=200:raise RuntimeError('Native RPC HTTP status '+str(status))
        data=json.loads(raw)
        if data.get('rpcId')!=identifier or data.get('type')!='server-response':raise RuntimeError('Native RPC envelope mismatch')
        result=data['result']
        if result.get('ok') is not True:raise RuntimeError('Native RPC failed: '+json.dumps(result.get('error'))[:1000])
        return result.get('value')

    def process_map(self):
        rows=[]
        if not self.collector.group:return rows
        for value in (self.collector.group/'cgroup.procs').read_text().split():
            pid=int(value)
            try:
                status=Path('/proc',value,'status').read_text();cmdline=Path('/proc',value,'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip()
                ppid=int(re.search(r'^PPid:\s*(\d+)',status,re.M)[1])
                rows.append(dict(pid=pid,ppid=ppid,cmdline=cmdline))
            except (OSError,TypeError):continue
        return rows

    def task(self,session_id,marker):
        started=time.monotonic_ns()
        if self.product=='DSH':
            created=self.rpc('session/create',dict(request=dict(sessionId=session_id,cwd=str(self.workspace))))
            session_id=created['sessionId']
            prompt=self.rpc('session/prompt',dict(request=dict(sessionId=session_id,requestId=str(uuid.uuid4()),mode='queue',content=[dict(type='text',text=marker)])))
            result=self.rpc('session/wait',dict(request=dict(sessionId=session_id,timeoutMs=60000)))
            accepted=prompt.get('accepted') is True and result.get('reason')=='idle' and 'PLATFORM_ACK:'+marker in json.dumps(result.get('output'))
            return dict(session_id=session_id,marker=marker,prompt_receipt=prompt,native_result=result,accepted=accepted,elapsed_ms=(time.monotonic_ns()-started)/1e6)
        session_key='agent:main:platform:'+session_id
        status,headers,raw=self.http('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',messages=[dict(role='user',content=marker)],user=session_id,stream=False)),
            {'Content-Type':'application/json','Authorization':'Bearer synthetic-platform-only','x-openclaw-session-key':session_key})
        result=json.loads(raw);content=''.join(str(c.get('message',{}).get('content','')) for c in result.get('choices',[]))
        return dict(session_id=session_id,session_key=session_key,marker=marker,status=status,native_result=result,accepted=status==200 and content=='PLATFORM_ACK:'+marker,elapsed_ms=(time.monotonic_ns()-started)/1e6)

    def stop(self):
        if self.process.poll() is None:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                self.process.wait()
        self.reader.join(timeout=2)
        return self.collector.finish()


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native execution requires a disposable hosted worker')
    args.output.mkdir(parents=True,exist_ok=True);results=[]
    versions={name:json.loads((args.runtime/'node_modules'/name/'package.json').read_text())['version'] for name in ('@deepseek-ai/dsh','openclaw')}
    if versions!={'@deepseek-ai/dsh':'0.2.2-alpha.2','openclaw':'2026.10.8'}:raise ValueError('Pinned native versions differ')
    with tempfile.TemporaryDirectory(prefix='platform-api-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for product in ('DSH','OpenClaw'):
            root=Path(tmp)/product;root.mkdir();provider=Provider(root/'unused','unused',decision_fn=fixture_response);server=None
            row=dict(product=product,valid=False,calibration_only=True,paid_model_calls=0)
            try:
                server=NativeServer(product,args.runtime,root,provider);server.ready();row['startup_ms']=(server.ready_ns-server.started_ns)/1e6;row['process_map']=server.process_map();row['command']=server.command
                # Two public native sessions share exactly one server and state root.
                row['tasks']=[server.task(str(uuid.uuid4()),'PLATFORM_INPUT_'+uuid.uuid4().hex) for _ in range(2)]
                row['session_bindings']=fresh_session_bindings(product,row['tasks'],provider.requests)
                row['valid']=row['session_bindings']['valid'] and all(t['accepted'] and any(t['marker'] in request_text(r['request']) for r in provider.requests) for t in row['tasks'])
            except Exception as error:row['adapter_error']=type(error).__name__+': '+str(error)[:1800]
            finally:
                if server is not None:row.update(resources=server.stop(),sanitized_native_log=list(server.logs),process_exit=server.process.returncode)
                provider.close();row['provider_requests']=provider.requests
            row['valid']=row['valid'] and row.get('resources',{}).get('complete',False);results.append(row)
            report=dict(kind='native-platform-api-calibration',run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),installed_versions=versions,
                formal_study_complete=False,synthetic_usage=True,paid_model_calls=0,results=results)
            (args.output/'platform-api-report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k in ('product','valid','startup_ms','adapter_error')}),flush=True)
    if not all(r['valid'] for r in results):raise SystemExit('Public native server/API calibration incomplete; inspect original retained evidence')

if __name__=='__main__':main()
