#!/usr/bin/env python3
"""Native idle entrypoints: fresh state and no user task or model inference."""
import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import re
import signal
import socket
import struct
import subprocess
import termios
import threading
import time
import urllib.request

ROOT = Path('/home/bench/idle')
PREFIX = Path('/opt/products/node_modules')
NODE = '/usr/local/bin/node'
ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[=>]')

def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class NoInference:
    def __init__(self):
        self.requests=[];owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,body,status=200):
                raw=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                owner.requests.append(dict(method='GET',path=self.path,time=time.time()))
                self.reply(dict(object='list',data=[dict(id='deepseek-flash',object='model')]))
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'));self.rfile.read(size)
                owner.requests.append(dict(method='POST',path=self.path,time=time.time()))
                self.reply(dict(error=dict(type='idle_probe_no_inference',message='No model inference is allowed during idle observation')),400)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):self.server.shutdown();self.server.server_close()

class Application:
    def __init__(self,product,index,base):
        self.product=product;self.path=ROOT/f'block-{index}'/product;self.path.mkdir(parents=True)
        self.home=self.path/'home';self.home.mkdir();self.workspace=Path('/testbed');scratch=self.path/'tmp';scratch.mkdir()
        self.env=dict(PATH=f'/opt/hermes-venv/bin:{PREFIX}/.bin:/usr/local/bin:/usr/bin:/bin',
            HOME=str(self.home),TMPDIR=str(scratch),LANG='C.UTF-8',TERM='xterm-256color',COLORTERM='truecolor',COLUMNS='120',LINES='35')
        self.port=None;self.ready_at=None;self.startup_actions=[];self.process=None;self.closed=False;self.raw=bytearray();self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        token='idle-probe-only';model='deepseek-flash';self.cwd=self.workspace
        if product in ('openclaw','openclaw57_patched'):
            self.port=port();state=self.home/'.openclaw';state.mkdir();config=state/'openclaw.json'
            cfg=dict(gateway=dict(mode='local',auth=dict(mode='token',token=token),controlUi=dict(enabled=False)),
                agents=dict(defaults=dict(workspace=str(self.workspace),skipBootstrap=True,memorySearch=dict(enabled=False),model=dict(primary='deepseek/'+model))),
                models=dict(providers=dict(deepseek=dict(baseUrl=base+'/v1',apiKey=token,api='openai-completions',models=[dict(id=model,name='Idle only',reasoning=True,input=['text'],contextWindow=1048576,maxTokens=16384)]))),
                cron=dict(enabled=False),logging=dict(level='debug',consoleLevel='info',file=str(self.home/'gateway-debug.log')))
            self.env.update(OPENCLAW_STATE_DIR=str(state),OPENCLAW_CONFIG_PATH=str(config),OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BONJOUR='1')
            if product=='openclaw57_patched':
                from agentloop_app import prepare_default_app
                prepare_default_app(self.home)
                cfg['agents']['defaults']['agentRuntime']=dict(id='agentloop');cfg['plugins']=dict(entries=dict(agentloop=dict(enabled=True)))
                self.env.update(OPENCLAW_AGENT_RUNTIME='agentloop',AGENTLOOP_WARMUP='0')
                entry=Path('/opt/openclaw57/openclaw.mjs')
                flags=['--max-old-space-size=700','--max-semi-space-size=8','--optimize-for-size','--expose-gc']
            else:
                entry=PREFIX/'openclaw/openclaw.mjs';flags=[]
                cfg['agents']['defaults'].pop('memorySearch')
                cfg['memory']=dict(search=dict(enabled=False))
            dump(config,cfg);self.command=[NODE,*flags,str(entry),'gateway','run','--bind','loopback','--port',str(self.port),'--allow-unconfigured']
        elif product == 'codex':
            state=self.home/'.codex';state.mkdir();self.env.update(CODEX_HOME=str(state),BENCH_API_KEY=token)
            (state/'config.toml').write_text(f'''model = "{model}"
model_provider = "bench"
model_context_window = 1048576
[model_providers.bench]
name = "Idle only"
base_url = "{base}/v1"
env_key = "BENCH_API_KEY"
wire_api = "responses"
requires_openai_auth = false
[projects."{self.workspace}"]
trust_level = "trusted"
''')
            executable=str(PREFIX/'@openai/codex/bin/codex.js')
            self.command=[NODE,executable,'--no-alt-screen','--no-daemon']
        elif product=='claude':
            self.env.update(ANTHROPIC_BASE_URL=base+'/anthropic',ANTHROPIC_API_KEY=token,
                ANTHROPIC_MODEL=model,CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',DISABLE_AUTOUPDATER='1',CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')
            dump(self.home/'.claude.json',dict(hasCompletedOnboarding=True,theme='dark',
                customApiKeyResponses=dict(approved=[token],rejected=[]),
                projects={str(self.workspace):dict(hasTrustDialogAccepted=True,hasCompletedProjectOnboarding=True,allowedTools=[])}))
            self.command=[str(PREFIX/'@anthropic-ai/claude-code/bin/claude.exe'),'--model',model]
        elif product=='dsh':
            self.port=port();self.env.update(DSH_HOME=str(self.home/'.dsh'),DEEPSEEK_BASE_URL=base+'/anthropic',DEEPSEEK_API_KEY=token)
            self.command=[NODE,str(PREFIX/'@deepseek-ai/dsh/lib/bin.js'),'--profile','web','--no-open','--host','127.0.0.1','--port',str(self.port)]
        elif product=='hermes':
            state=self.home/'.hermes';state.mkdir()
            self.env.update(HERMES_HOME=str(state),HERMES_RUNTIME_DIR='/home/bench/hermes-tools',
                DEEPSEEK_API_KEY=token,DEEPSEEK_BASE_URL=base+'/v1')
            (state/'config.yaml').write_text(f'''model:
  default: {model}
  provider: deepseek
  base_url: {base}/v1
  api_key: {token}
memory:
  memory_enabled: false
  user_profile_enabled: false
telemetry:
  shared_metrics:
    enabled: false
    send: false
    offer_version: 2
terminal:
  backend: local
  cwd: {self.workspace}
''')
            self.command=['/opt/hermes-venv/bin/hermes','--cli','--model',model,'--provider','deepseek']
        else:raise ValueError(product)
        dump(self.path/'launch.json',dict(product=product,command=self.command,environment=self.env,cwd=str(self.cwd),phase='idle; no task or prompt submitted',cpus=sorted(os.sched_getaffinity(0))[:2]))
    def start(self):
        master,slave=pty.openpty();self.master=master
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',35,120,0,0))
        def setup():
            os.setsid();fcntl.ioctl(slave,termios.TIOCSCTTY,0);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
        self.process=subprocess.Popen(self.command,cwd=self.cwd,env=self.env,stdin=slave,stdout=slave,stderr=slave,preexec_fn=setup)
        os.close(slave)
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start()
    def read(self):
        with (self.path/'terminal.ansi').open('wb') as stream:
            while True:
                try:data=os.read(self.master,65536)
                except OSError:break
                if not data:break
                self.raw.extend(data);stream.write(data);stream.flush()
                for query,answer in [(b'\x1b[6n',b'\x1b[1;1R'),(b'\x1b]11;?',b'\x1b]11;rgb:0000/0000/0000\x07'),(b'\x1b[c',b'\x1b[?1;2c')]:
                    if query in data:
                        try:os.write(self.master,answer)
                        except OSError:pass
    def text(self):return ANSI.sub('',bytes(self.raw).decode(errors='replace'))
    def send(self,value,reason):
        os.write(self.master,value);self.startup_actions.append(dict(reason=reason,bytes_hex=value.hex(),at=time.time()));dump(self.path/'startup-actions.json',self.startup_actions)
    def ready(self):
        if self.process.poll() is not None:raise RuntimeError(f'{self.product} exited: {self.process.returncode}')
        text=self.text()
        if self.port:
            try:
                path='/readyz' if self.product.startswith('openclaw') else '/'
                if self.product=='dsh':
                    match=re.search(r'dsh web: (http://127\.0\.0\.1:\d+/\?token=[^\s]+)',text)
                    if not match:return False
                    path=match.group(1).split(str(self.port),1)[1]
                with self.opener.open(f'http://127.0.0.1:{self.port}{path}',timeout=1) as response:
                    payload=response.read();status=response.status
                valid=status==200
                if self.product.startswith('openclaw'):valid=valid and json.loads(payload).get('ready') is True
                if self.product=='openclaw57_patched':valid=valid and '[agentloop] tools prewarm complete' in text and '[agentloop] all apps loaded' in text
                if valid:dump(self.path/'readiness.json',dict(at=time.time(),url=f'http://127.0.0.1:{self.port}{path}',status=status,body=payload.decode(errors='replace')[:4000]))
                return valid
            except (OSError,ValueError):return False
        if self.product.startswith('codex'):
            return 'OpenAI Codex' in text and 'deepseek-flash' in text and ('context left' in text or '›' in text) and 'Error: app server' not in text
        if self.product=='claude':
            if 'trust this folder' in text.lower() and not any(a['reason']=='trust fresh empty workspace' for a in self.startup_actions):self.send(b'\r','trust fresh empty workspace')
            return 'Claude Code' in text and ('❯' in text or 'Try "' in text) and 'Do you want to use this API key?' not in text[-2500:]
        if self.product=='hermes':
            return ('You:' in text or 'Message Hermes' in text or 'Type a message' in text or '❯' in text) and ('Hermes' in text or 'hermes' in text)
    def close(self):
        if self.closed:return
        self.closed=True
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            try:self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait()
        if self.process:
            try:os.close(self.master)
            except OSError:pass
            self.reader.join(timeout=1)
            (self.path/'terminal.txt').write_text(self.text())

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', required=True)
    args = parser.parse_args()
    trap = NoInference()
    app = Application(args.product, 1, trap.base)
    try:
        app.start()
        deadline = time.monotonic() + 540
        while not app.ready():
            if time.monotonic() > deadline:
                raise TimeoutError('Native idle entrypoint did not become ready')
            time.sleep(1)
        dump(Path('/home/bench/idle-ready.json'), dict(product=args.product,
             ready_utc=time.time(), native_child_pid=app.process.pid,
             phase='native UI/server ready; no user task submitted', command=app.command))
        while True:
            if app.process.poll() is not None:
                raise ValueError('Native process exited during idle observation')
            generation = [r for r in trap.requests if r['method']=='POST' and
                          any(p in r['path'] for p in ('/messages','/chat/completions','/responses'))]
            dump(Path('/home/bench/idle-network.json'), dict(requests=trap.requests,
                 inference_attempts=len(generation), external_network='none', real_credentials=False))
            if generation:
                raise ValueError('Unexpected inference attempt; idle measurement invalid')
            time.sleep(1)
    finally:
        app.close()
        trap.close()
