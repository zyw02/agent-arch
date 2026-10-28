#!/usr/bin/env python3
"""PC hosted native lifecycle/idle/sequential/concurrent complete blocks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import resource
import tempfile
import threading
import time
import uuid
from context_skill_probe import request_text
from native_read_probe import Provider
from platform_api_probe import NativeServer,fixture_response,MARKER,fresh_session_bindings
from resource_collector import counters

PROTOCOL=Path(__file__).with_name('platform-resource-protocol.json')


class DelayedFixture:
    def __init__(self,delay):self.delay=delay;self.ledger=[];self.lock=threading.Lock();self.active=0
    def decide(self,body,*unused):
        title='Generate the session title from this JSON array' in request_text(body)
        with self.lock:
            self.active+=1;event=dict(received_ns=time.monotonic_ns(),active_including_titles=self.active,title=title,request=body);self.ledger.append(event)
        try:time.sleep(self.delay);return fixture_response(body,None,None,None)
        finally:
            with self.lock:self.active-=1;event['released_ns']=time.monotonic_ns()


def cpu_snapshot(server):
    before=time.monotonic_ns()
    values=counters((server.collector.group/'cpu.stat').read_text()) if server.collector.group else {}
    return dict(before_read_ns=before,after_read_ns=time.monotonic_ns(),cpu=values,process_map=server.process_map())


def phase_boundary(server,edge):
    # Bracket the CPU/time cut with a live memory sample. Main and background
    # samples share the collector lock, so helper RPC responses cannot cross.
    if edge=='start':server.collector.sample()
    cut=cpu_snapshot(server)
    if edge=='end':server.collector.sample()
    return cut


def integrate_memory(samples,start,end,key):
    # Piecewise-linear integration with nearest observed endpoint values.
    values=sorted((s['monotonic_ns'],s[key]) for s in samples if key in s)
    if not values or end<=start:return None
    def value_at(t):
        if t<=values[0][0]:return values[0][1]
        for (ta,a),(tb,b) in zip(values,values[1:]):
            if ta<=t<=tb:return a+(b-a)*(t-ta)/(tb-ta)
        return values[-1][1]
    points=[(start,value_at(start)),*((t,v) for t,v in values if start<t<end),(end,value_at(end))]
    return sum((b-a)*(va+vb)/2/1e9 for (a,va),(b,vb) in zip(points,points[1:]))


def fixture_capacity(protocol):
    fixture=DelayedFixture(protocol['provider_delay_seconds']);provider=Provider(Path('/unused'),'unused',decision_fn=fixture.decide,max_requests=4)
    def request(index):
        marker='PLATFORM_INPUT_'+uuid.uuid4().hex;connection=http.client.HTTPConnection('127.0.0.1',provider.server.server_port,timeout=5);started=time.monotonic_ns()
        try:
            connection.request('POST','/v1/chat/completions',json.dumps(dict(messages=[dict(role='user',content=marker)])),{'Content-Type':'application/json'})
            response=connection.getresponse();body=json.loads(response.read())
            return dict(status=response.status,elapsed_ms=(time.monotonic_ns()-started)/1e6,accepted=body['choices'][0]['message']['content']=='PLATFORM_ACK:'+marker)
        finally:connection.close()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(request,range(4)))
    finally:provider.close()
    overshoot=max((e['released_ns']-e['received_ns'])/1e6-protocol['provider_delay_seconds']*1000 for e in fixture.ledger)
    spread=(max(e['received_ns'] for e in fixture.ledger)-min(e['received_ns'] for e in fixture.ledger))/1e6
    return dict(requests=results,active_peak=max(e['active_including_titles'] for e in fixture.ledger),max_release_overshoot_ms=overshoot,arrival_spread_ms=spread,
        valid=all(r['status']==200 and r['accepted'] for r in results) and overshoot<=protocol['fixture_max_release_overshoot_ms'] and spread<=protocol['fixture_max_arrival_spread_ms'],
        scope='Four simultaneous direct HTTP fixture requests before product runs; synthetic protocol/capacity check, not native task throughput or disabled-observer causal calibration')


def run_arm(product,condition,runtime,root,protocol):
    fixture=DelayedFixture(protocol['provider_delay_seconds']);provider=Provider(root/'unused','unused',decision_fn=fixture.decide,max_requests=40);server=None
    row=dict(product=product,condition=condition,valid=False,tasks=[],paid_model_calls=0);started=time.monotonic_ns();observer=resource.getrusage(resource.RUSAGE_SELF)
    try:
        server=NativeServer(product,runtime,root,provider,sample_interval=protocol['sample_interval_seconds']);server.ready();row['startup_ms']=(server.ready_ns-server.started_ns)/1e6;row['startup_process_map']=server.process_map();row['owner']=server.service_owner()
        if condition in ('warm_single','four_sequential','four_concurrent'):
            row['priming_task']=server.task(str(uuid.uuid4()),'PLATFORM_INPUT_'+uuid.uuid4().hex)
            if not row['priming_task']['accepted']:raise RuntimeError('Native warmup positive control failed')
        row['phase_start']=phase_boundary(server,'start')
        if condition=='idle':time.sleep(protocol['idle_seconds'])
        else:
            identifiers=[(str(uuid.uuid4()),'PLATFORM_INPUT_'+uuid.uuid4().hex) for _ in range(4 if condition.startswith('four_') else 1)]
            def task(args):
                try:return server.task(*args)
                except Exception as error:return dict(session_id=args[0],marker=args[1],accepted=False,native_error=type(error).__name__+': '+str(error)[:1600])
            if condition=='four_concurrent':
                with ThreadPoolExecutor(max_workers=4) as pool:row['tasks']=list(pool.map(task,identifiers))
            else:row['tasks']=[task(args) for args in identifiers]
        row['phase_end']=phase_boundary(server,'end');row['valid']=all(t['accepted'] for t in row['tasks'])
    except Exception as error:row['adapter_error']=type(error).__name__+': '+str(error)[:2000]
    finally:
        if server is not None:row.update(resources=server.stop(),sanitized_native_log=list(server.logs),exit_code=server.process.returncode)
        provider.close();row['provider_requests']=provider.requests;row['fixture_ledger']=fixture.ledger
        end_observer=resource.getrusage(resource.RUSAGE_SELF);row.update(elapsed_ms=(time.monotonic_ns()-started)/1e6,
            observer_parent_cpu_seconds=end_observer.ru_utime+end_observer.ru_stime-observer.ru_utime-observer.ru_stime)
    # Per-pair native identity validation reuses the calibrated public binding.
    # Single-task controls additionally verify actual provider marker/OC key.
    task_requests=[r for r in provider.requests if 'Generate the session title from this JSON array' not in request_text(r['request'])]
    bindings=[]
    for task in row['tasks']:
        reached=[r for r in task_requests if task['marker'] in request_text(r['request'])]
        native_key=task.get('session_key') if product=='OpenClaw' else task['session_id']
        visible=product=='DSH' or any(('session='+str(native_key)+' |') in request_text(r['request']) for r in reached)
        disjoint=all(other['marker'] not in request_text(r['request']) for r in reached for other in row['tasks'] if other is not task)
        bindings.append(dict(native_identity=native_key,matching_requests=len(reached),native_identity_visible=visible,disjoint_context=disjoint))
    row['task_bindings']=bindings
    row['valid']=row['valid'] and len({b['native_identity'] for b in bindings})==len(bindings) and all(b['matching_requests']==1 and b['native_identity_visible'] and b['disjoint_context'] for b in bindings)
    if 'phase_end' in row:
        start=row['phase_start']['after_read_ns'];end=row['phase_end']['before_read_ns'];samples=row['resources']['samples']
        row['phase_metrics']=dict(elapsed_ms=(end-start)/1e6,cpu_seconds=(row['phase_end']['cpu']['usage_usec']-row['phase_start']['cpu']['usage_usec'])/1e6,
            integrated_rss_byte_seconds=integrate_memory(samples,start,end,'sampled_rss_sum_bytes'),
            sampled_peak_pss_bytes=max((s['sampled_pss_bytes'] for s in samples if start<=s['monotonic_ns']<=end and 'sampled_pss_bytes' in s),default=None),
            memory_samples_within_phase=sum(start<=s['monotonic_ns']<=end and 'sampled_rss_sum_bytes' in s for s in samples),
            memory_integration='Piecewise linear between observed samples, nearest observed values at phase endpoints. Not exact resident integral; sub-sample lifetimes/peaks may be missed')
    row['valid']=row['valid'] and row.get('resources',{}).get('complete',False)
    return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=['pilot','formal'],default='pilot');p.add_argument('--blocks',type=int,default=1);args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Native lifecycle execution requires a disposable hosted worker')
    if args.phase=='pilot' and args.blocks!=1:raise ValueError('One pilot block per product required')
    raw=PROTOCOL.read_bytes();protocol=json.loads(raw);versions={p:json.loads((args.runtime/'node_modules'/p/'package.json').read_text())['version'] for p in ('@deepseek-ai/dsh','openclaw')}
    if args.phase=='formal':
        admission=json.loads(Path(__file__).with_name('platform-resource-formal-admission.json').read_bytes());pilot_raw=gzip.decompress((Path(__file__).parent/admission['pilot_report_gzip']).read_bytes());pilot=json.loads(pilot_raw)
        expected={(p,c,1) for p in ('DSH','OpenClaw') for c in protocol['conditions']}
        if args.blocks!=2 or admission['status']!='admitted' or admission['protocol_sha256']!=hashlib.sha256(raw).hexdigest() or hashlib.sha256(pilot_raw).hexdigest()!=admission['pilot_report_sha256'] or len(pilot['results'])!=10 or {(r['product'],r['condition'],r['block']) for r in pilot['results']}!=expected or not all(r['valid'] for r in pilot['results']):
            raise ValueError('Complete PC pilot/formal admission not verified')
    if versions!={'@deepseek-ai/dsh':'0.2.2-alpha.2','openclaw':'2026.10.8'}:raise ValueError('Pinned versions differ')
    args.output.mkdir(parents=True,exist_ok=True);results=[];report=dict(kind='native-platform-lifecycle-resources',phase=args.phase,blocks=args.blocks,protocol=protocol,protocol_sha256=hashlib.sha256(raw).hexdigest(),installed_versions=versions,
        run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),paid_model_calls=0,results=results)
    report['fixture_capacity']=fixture_capacity(protocol)
    report['host']=dict(cpu_count=os.cpu_count(),meminfo=Path('/proc/meminfo').read_text(),observer_cpu_method='Whole controller process CPU includes sampling thread and fixture threads; separate memory-reader command CPU is disjoint. Same observer cadence across all arms; no zero-overhead claim')
    (args.output/'platform-resource-report.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['fixture_capacity']['valid']:raise SystemExit('Four-request fixture capacity control failed before native execution')
    with tempfile.TemporaryDirectory(prefix='platform-resource-',dir=os.environ['RUNNER_TEMP']) as tmp:
        for block in range(1,args.blocks+1):
            for condition in protocol['conditions']:
                for product in (('DSH','OpenClaw') if block%2 else ('OpenClaw','DSH')):
                    root=Path(tmp)/(str(block)+'-'+product+'-'+condition);root.mkdir();row=run_arm(product,condition,args.runtime,root,protocol);row['block']=block;results.append(row)
                    (args.output/'platform-resource-report.json').write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps({k:row.get(k) for k in ('product','condition','block','valid','adapter_error','elapsed_ms','phase_metrics')}),flush=True)
                    if not row['valid']:raise SystemExit('Native lifecycle control incomplete; retain original observations and withhold dependent arms')

if __name__=='__main__':main()
