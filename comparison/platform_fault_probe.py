#!/usr/bin/env python3
"""PA public HTTP fault-domain pilot/formal blocks, hosted workers only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from context_skill_probe import request_text
from export_read_metrics import request_stage
from native_read_probe import Provider
from platform_api_probe import NativeServer,fixture_response,MARKER

PROTOCOL=Path(__file__).with_name('platform-fault-protocol.json')


class Gate:
    def __init__(self,markers):
        self.markers=markers;self.arrived={m:threading.Event() for m in markers}
        self.release=threading.Event();self.ledger=[];self.lock=threading.Lock()

    def decide(self,body,*unused):
        # Receipt is recorded BEFORE blocking. Provider.requests records after
        # decide returns, so its timestamp cannot prove the fault boundary.
        text=request_text(body);title='Generate the session title from this JSON array' in text
        latest=MARKER.findall(text);marker=latest[-1] if latest else None
        row=dict(received_ns=time.monotonic_ns(),marker=marker,title=title,
            request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),request=body)
        with self.lock:self.ledger.append(row)
        if not title and marker in self.arrived:
            self.arrived[marker].set()
            if not self.release.wait(90):raise RuntimeError('Fixture boundary release safeguard exceeded')
            row['released_ns']=time.monotonic_ns()
        return fixture_response(body,None,None,None)


def child_main():
    config=json.loads(sys.stdin.readline());server=NativeServer.__new__(NativeServer)
    server.product=config['product'];server.port=config['port'];server.cookie=config['cookie']
    def sent(method,path):print(json.dumps(dict(kind='request_sent',method=method,path=path,ns=time.monotonic_ns())),flush=True)
    server.on_http_sent=sent
    try:
        result=server.task(config['session_id'],config['marker'],create=False)
        print(json.dumps(dict(kind='terminal',ns=time.monotonic_ns(),result=result)),flush=True)
    except Exception as error:
        print(json.dumps(dict(kind='transport_error',ns=time.monotonic_ns(),error=type(error).__name__+': '+str(error)[:1000])),flush=True)


class Client:
    def __init__(self,server,session_id,marker):
        self.events=[];self.started_ns=time.monotonic_ns()
        self.process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--client'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.process.stdin.write(json.dumps(dict(product=server.product,port=server.port,cookie=server.cookie,session_id=session_id,marker=marker))+'\n');self.process.stdin.close()
        def read():
            for line in self.process.stdout:self.events.append(json.loads(line))
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()

    def result_request_sent(self,product):
        path='/api/session/wait' if product=='DSH' else '/v1/chat/completions'
        return any(e.get('kind')=='request_sent' and e.get('path')==path for e in self.events)

    def terminal(self):
        return any(e.get('kind') in ('terminal','transport_error') for e in self.events)

    def finish(self):
        cleanup=False
        if self.process.poll() is None:self.process.kill();cleanup=True
        self.process.wait();self.thread.join(timeout=2)
        return dict(pid=self.process.pid,started_ns=self.started_ns,exit_code=self.process.returncode,
            killed_at_cleanup=cleanup,events=self.events,stderr=self.process.stderr.read()[-1000:])


def wait_until(predicate,seconds,description):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return time.monotonic_ns()
        time.sleep(.02)
    raise RuntimeError(description+' was not observed within its declared safeguard')


def message_text(message):
    content=message.get('content','')
    if isinstance(content,str):return content
    if isinstance(content,list):return ''.join(c.get('text','') for c in content if isinstance(c,dict) and c.get('type')=='text')
    return ''


def history_facts(product,history,marker):
    if product=='DSH':
        records=history.get('events',{}).get('records',[])
        messages=[]
        for record in records:
            event=record.get('event',{});data=event.get('data',{})
            if event.get('type')=='user/message':messages.append(dict(role='user',content=data.get('content',[])))
            elif event.get('type')=='assistant/message':messages.append(data.get('message',{}))
    else:messages=history.get('history',{}).get('messages',[])
    return dict(user_retained=any(m.get('role')=='user' and marker in message_text(m) for m in messages),
        assistant_ack=any(m.get('role')=='assistant' and message_text(m)=='PLATFORM_ACK:'+marker for m in messages))


def safe_histories(server,tasks):
    rows={}
    for role,task in tasks.items():
        start=time.monotonic_ns()
        try:
            native=server.history(task['session_id']);rows[role]=dict(started_ns=start,finished_ns=time.monotonic_ns(),native=native,facts=history_facts(server.product,native,task['marker']))
        except Exception as error:rows[role]=dict(started_ns=start,error=type(error).__name__+': '+str(error)[:1600])
    return rows


def run_arm(product,condition,runtime,root,observation_seconds):
    started=time.monotonic_ns();tasks={role:dict(session_id=str(uuid.uuid4()),marker='PLATFORM_INPUT_'+uuid.uuid4().hex) for role in ('primary','companion')}
    gate=Gate([t['marker'] for t in tasks.values()]);provider=Provider(root/'unused','unused',decision_fn=gate.decide,max_requests=40)
    server=None;clients={};row=dict(product=product,condition=condition,tasks=tasks,validity='adapter_error',paid_model_calls=0,cycles=[])
    try:
        server=NativeServer(product,runtime,root,provider);server.ready();owner=server.service_owner()
        row.update(startup_ms=(server.ready_ns-server.started_ns)/1e6,initial_process_map=server.process_map(),owner=owner,command=server.command)
        for role,task in tasks.items():
            if product=='DSH':task['session_id']=server.rpc('session/create',dict(request=dict(sessionId=task['session_id'],cwd=str(server.workspace))))['sessionId']
            clients[role]=Client(server,task['session_id'],task['marker'])
        row['boundary_ns']=wait_until(lambda:all(e.is_set() for e in gate.arrived.values()) and all(c.result_request_sent(product) for c in clients.values()),60,'Both admitted model requests and waiting result consumers')
        row['boundary_process_map']=server.process_map()
        if condition=='client_exit':
            target=clients['primary'].process
            if target.poll() is not None:raise RuntimeError('Primary client no longer alive at intervention')
            row['intervention']=dict(signal='SIGKILL',pid=target.pid,requested_ns=time.monotonic_ns());target.kill();target.wait();row['intervention']['delivered_ns']=time.monotonic_ns()
        elif condition=='owner_exit':row['intervention']=server.kill_service_owner(owner)
        else:row['intervention']=dict(signal=None,requested_ns=time.monotonic_ns(),delivered_ns=time.monotonic_ns())
        row['release_ns']=time.monotonic_ns();gate.release.set()
        row['observation']=[dict(ns=time.monotonic_ns(),process_map=server.process_map())]
        for seconds in (.5,2,observation_seconds):
            delay=seconds-(time.monotonic_ns()-row['release_ns'])/1e9
            if delay>0:time.sleep(delay)
            row['observation'].append(dict(seconds_after_release=seconds,ns=time.monotonic_ns(),process_map=server.process_map(),client_exit_codes={r:c.process.poll() for r,c in clients.items()}))
        row['clients']={r:c.finish() for r,c in clients.items()};clients={}
        if condition!='owner_exit':row['before_restart_histories']=safe_histories(server,tasks)
        row['cycles'].append(dict(resources=server.stop(),sanitized_native_log=list(server.logs),exit_code=server.process.returncode));server=None
        # This new carrier uses exactly the original product-owned state. No
        # evaluator history copy, retry of old input or new session.create.
        row['restart_requested_ns']=time.monotonic_ns();server=NativeServer(product,runtime,root,provider);server.ready();row['restart_ready_ns']=time.monotonic_ns()
        row['restart_process_map']=server.process_map();row['passive_histories']=safe_histories(server,tasks)
        row['passive_window_started_ns']=time.monotonic_ns();time.sleep(observation_seconds)
        row['after_passive_window_histories']=safe_histories(server,tasks)
        row['followup_started_ns']=time.monotonic_ns();row['followups']={}
        for role,task in tasks.items():
            marker='PLATFORM_INPUT_'+uuid.uuid4().hex;follow=dict(marker=marker)
            try:follow['result']=server.task(task['session_id'],marker,create=False)
            except Exception as error:follow['error']=type(error).__name__+': '+str(error)[:1600]
            reached=[e for e in gate.ledger if not e['title'] and MARKER.findall(request_text(e['request']))[-1:]==[marker]]
            follow['provider_contexts']=[dict(request_sha256=e['request_sha256'],prior_user=task['marker'] in request_text(e['request']),prior_ack='PLATFORM_ACK:'+task['marker'] in request_text(e['request'])) for e in reached]
            row['followups'][role]=follow
        row['final_histories']=safe_histories(server,tasks);row['validity']='valid'
    except Exception as error:row['adapter_error']=type(error).__name__+': '+str(error)[:2000]
    finally:
        gate.release.set()
        if clients:row['clients']={r:c.finish() for r,c in clients.items()}
        if server is not None:row['cycles'].append(dict(resources=server.stop(),sanitized_native_log=list(server.logs),exit_code=server.process.returncode))
        provider.close();row.update(provider_requests=provider.requests,boundary_ledger=gate.ledger,elapsed_ms=(time.monotonic_ns()-started)/1e6)
    row['resource_collection_complete']=bool(row['cycles']) and all(c['resources']['complete'] for c in row['cycles'])
    # Negative fault outcomes remain valid observations. Positive-control and
    # observer failure cannot be used to admit the formal study.
    row['pilot_ready']=row['validity']=='valid' and row['resource_collection_complete'] and all('error' not in h for h in row.get('after_passive_window_histories',{}).values()) and len(row.get('after_passive_window_histories',{}))==2
    if condition=='healthy':row['pilot_ready']=row['pilot_ready'] and all(h['facts']['assistant_ack'] for h in row.get('before_restart_histories',{}).values()) and all(f.get('result',{}).get('accepted') for f in row.get('followups',{}).values())
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--client',action='store_true');parser.add_argument('--runtime',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--phase',choices=['pilot','formal'],default='pilot');parser.add_argument('--blocks',type=int,default=1);args=parser.parse_args()
    if args.client:child_main();return
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native fault execution requires a disposable hosted worker')
    protocol_raw=PROTOCOL.read_bytes();protocol=json.loads(protocol_raw)
    if args.phase=='pilot' and args.blocks!=1:raise ValueError('Pilot must be one complete block per product')
    versions={p:json.loads((args.runtime/'node_modules'/p/'package.json').read_text())['version'] for p in ('@deepseek-ai/dsh','openclaw')}
    if versions!={'@deepseek-ai/dsh':'0.2.2-alpha.2','openclaw':'2026.10.8'}:raise ValueError('Installed product versions differ')
    args.output.mkdir(parents=True,exist_ok=True);results=[];report=dict(kind='native-platform-fault-domains',phase=args.phase,protocol_sha256=hashlib.sha256(protocol_raw).hexdigest(),protocol=protocol,
        run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),installed_versions=versions,paid_model_calls=0,results=results)
    (args.output/'protocol.json').write_bytes(protocol_raw)
    with tempfile.TemporaryDirectory(prefix='platform-fault-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for block in range(1,args.blocks+1):
            products=('DSH','OpenClaw') if block%2 else ('OpenClaw','DSH')
            for condition in ('healthy','client_exit','owner_exit'):
                for product in products:
                    root=Path(tmp)/(str(block)+'-'+product+'-'+condition);root.mkdir()
                    row=run_arm(product,condition,args.runtime,root,protocol['observation_seconds']);row['block']=block;results.append(row)
                    (args.output/'platform-fault-report.json').write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps({k:row[k] for k in ('product','condition','block','validity','pilot_ready','elapsed_ms')}),flush=True)
                    if condition=='healthy' and not row['pilot_ready']:raise SystemExit('Healthy complete-block control incomplete; fault arms withheld')
    if not all(r['pilot_ready'] for r in results):raise SystemExit('Fault pilot observer or adapter incomplete; retain all original observations')

if __name__=='__main__':main()
