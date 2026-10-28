#!/usr/bin/env python3
"""Direct four-request calibration of the actual owned stdio MCP process."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import resource
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from tool_lifecycle_probe import read_ledger
from summarize_tool_lifecycle import active_peak

PROTOCOL=Path(__file__).with_name('tool-lifecycle-fixture-protocol.json')


def check():
    protocol=json.loads(PROTOCOL.read_bytes());started=time.monotonic_ns();before=resource.getrusage(resource.RUSAGE_CHILDREN)
    with tempfile.TemporaryDirectory(prefix='owned-mcp-preflight-') as directory:
        root=Path(directory);values=['TOOL_VALUE_'+uuid.uuid4().hex for _ in range(4)];files=[]
        for i,value in enumerate(values):
            path=root/str(i);path.write_text(value);files.append(str(path))
        ledger=root/'ledger.jsonl';config=root/'config.json';config.write_text(json.dumps(dict(files=files,ledger=str(ledger),cleanup_release=str(root/'release'),delay_seconds=protocol['delay_seconds'])))
        command=[sys.executable,str(Path(__file__).with_name('tool_lifecycle_mcp.py')),'--config',str(config)];process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);responses=queue.Queue()
        def read():
            for line in process.stdout:
                try:responses.put(json.loads(line))
                except ValueError:responses.put(dict(parse_error=True))
        reader=threading.Thread(target=read,daemon=True);reader.start();received=[];error=None
        try:
            process.stdin.write(json.dumps(dict(jsonrpc='2.0',id=0,method='initialize',params=dict(protocolVersion='2025-03-26',capabilities={},clientInfo=dict(name='owned-preflight',version='1'))))+'\n');process.stdin.flush()
            initialization=responses.get(timeout=protocol['response_safeguard_seconds'])
            if initialization.get('id')!=0:raise ValueError('MCP initialize correlation failed')
            for i in range(4):process.stdin.write(json.dumps(dict(jsonrpc='2.0',id=i+1,method='tools/call',params=dict(name='eval_read',arguments=dict(index=i))))+'\n')
            process.stdin.flush()
            for _ in range(4):received.append(responses.get(timeout=protocol['response_safeguard_seconds']))
        except Exception as caught:error=type(caught).__name__
        finally:
            process.stdin.close()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait();error=error or 'fixture_stop_timeout'
            reader.join(timeout=2)
        events=read_ledger(ledger);starts=[e for e in events if e['kind']=='call_received'];reads=[e for e in events if e['kind']=='file_read'];stops=[e for e in events if e['kind']=='call_stopped'];sent=[e for e in events if e['kind']=='result_sent']
        after=resource.getrusage(resource.RUSAGE_CHILDREN);by_id={r.get('id'):r for r in received};complete_values=len(received)==len(by_id)==4 and all(by_id.get(i+1,{}).get('result',{}).get('content')==[dict(type='text',text=values[i])] for i in range(4))
        overshoots=[(r['monotonic_ns']-s['monotonic_ns'])/1e6-protocol['delay_seconds']*1000 for r in sent for s in starts if r['mcp_call_id']==s['mcp_call_id']];spread=(max(e['monotonic_ns'] for e in starts)-min(e['monotonic_ns'] for e in starts))/1e6 if len(starts)==4 else None
        peak=active_peak(events);all_before_first=len(starts)==len(reads)==4 and max(s['monotonic_ns'] for s in starts)<min(r['monotonic_ns'] for r in reads)
        hashes_correct=len(reads)==4 and all(r['sha256']==hashlib.sha256(values[r['index']].encode()).hexdigest() for r in reads)
        valid=not error and process.returncode==0 and complete_values and hashes_correct and len(stops)==len(sent)==4 and all(s['reason']=='completed' for s in stops) and peak==4 and all_before_first and max(overshoots,default=float('inf'))<=protocol['max_release_overshoot_ms'] and spread is not None and spread<=protocol['max_arrival_spread_ms']
        return dict(protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),valid=valid,error=error,exact_values=complete_values,read_hashes_correct=hashes_correct,active_peak=peak,max_release_overshoot_ms=max(overshoots,default=None),arrival_spread_ms=spread,
            elapsed_seconds=(time.monotonic_ns()-started)/1e9,fixture_child_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,events=events,responses=received,values=values,
            scope=protocol['limits'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();result=check();args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('events','responses','values')}))
    if not result['valid']:raise SystemExit('Owned MCP fixture preflight failed; native execution withheld')


if __name__=='__main__':main()
