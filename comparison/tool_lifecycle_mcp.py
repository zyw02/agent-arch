#!/usr/bin/env python3
"""Concurrent, read-only owned MCP fixture with observable failure/cancellation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time


class ReadFixture:
    def __init__(self,config,send):
        self.config=config;self.send=send;self.calls={};self.lock=threading.Lock();self.ledger_lock=threading.Lock();self.threads=[]

    def event(self,kind,**fields):
        row=dict(kind=kind,monotonic_ns=time.monotonic_ns(),pid=os.getpid(),**fields)
        with self.ledger_lock:
            with Path(self.config['ledger']).open('a') as file:file.write(json.dumps(row)+'\n')

    def dispatch(self,message):
        method=message.get('method');identifier=message.get('id');params=message.get('params',{})
        if method=='notifications/cancelled':
            target=params.get('requestId')
            with self.lock:
                event=self.calls.get(target)
                if event is not None:event.set()
            self.event('cancel_notification',mcp_call_id=target,known_call=event is not None)
            return
        if identifier is None:return
        if method=='tools/call':
            stop=threading.Event()
            with self.lock:
                if identifier in self.calls:
                    self.send(dict(jsonrpc='2.0',id=identifier,error=dict(code=-32600,message='Duplicate active request id')));return
                self.calls[identifier]=stop
            thread=threading.Thread(target=self.call,args=(identifier,params,stop));self.threads.append(thread);thread.start();return
        if method=='initialize':result=dict(protocolVersion=params.get('protocolVersion','2025-03-26'),capabilities=dict(tools={}),serverInfo=dict(name='owned-tool-lifecycle',version='1.0.0'))
        elif method=='tools/list':result=dict(tools=[dict(name='eval_read',description='Read one of four fixed synthetic files by index',annotations=dict(readOnlyHint=True,idempotentHint=True),inputSchema=dict(type='object',properties=dict(index=dict(type='integer',enum=[0,1,2,3])),required=['index'],additionalProperties=False))])
        elif method in ('resources/list','resources/templates/list','prompts/list'):result={('resourceTemplates' if method=='resources/templates/list' else method.split('/')[0]):[]}
        elif method=='ping':result={}
        else:self.send(dict(jsonrpc='2.0',id=identifier,error=dict(code=-32601,message='Unknown owned method')));return
        self.send(dict(jsonrpc='2.0',id=identifier,result=result))

    def call(self,identifier,params,stop):
        index=params.get('arguments',{}).get('index');reason='invalid'
        self.event('call_received',mcp_call_id=identifier,index=index,thread_id=threading.get_native_id())
        try:
            if params.get('name')!='eval_read' or type(index) is not int or index not in range(4):
                self.send(dict(jsonrpc='2.0',id=identifier,error=dict(code=-32602,message='Invalid owned read')));return
            if self.config.get('hold_index')==index:
                self.event('hold_entered',mcp_call_id=identifier,index=index)
                while not stop.wait(.01):
                    if Path(self.config['cleanup_release']).exists():
                        reason='cleanup_release';self.event('cleanup_released',mcp_call_id=identifier,index=index)
                        self.send(dict(jsonrpc='2.0',id=identifier,result=dict(isError=True,content=[dict(type='text',text='OWNED_CLEANUP_RELEASE_WITHOUT_READ')])));return
                reason='cancelled';return
            if stop.wait(self.config.get('delay_seconds',0)):reason='cancelled';return
            if self.config.get('fail_index')==index:
                text=self.config['failure_marker'];is_error=True;reason='controlled_failure';self.event('failure_injected',mcp_call_id=identifier,index=index,marker=text)
            else:
                path=Path(self.config['files'][index]);raw=path.read_bytes();text=raw.decode();is_error=False;reason='completed'
                self.event('file_read',mcp_call_id=identifier,index=index,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            if stop.is_set():reason='cancelled';return
            self.send(dict(jsonrpc='2.0',id=identifier,result=dict(content=[dict(type='text',text=text)],isError=is_error)))
            self.event('result_sent',mcp_call_id=identifier,index=index,is_error=is_error,content_sha256=hashlib.sha256(text.encode()).hexdigest())
        finally:
            with self.lock:self.calls.pop(identifier,None)
            self.event('call_stopped',mcp_call_id=identifier,index=index,reason=reason)

    def finish(self):
        with self.lock:
            for event in self.calls.values():event.set()
        for thread in self.threads:thread.join()


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);args=p.parse_args();config=json.loads(args.config.read_bytes());write_lock=threading.Lock()
    def send(value):
        with write_lock:print(json.dumps(value),flush=True)
    fixture=ReadFixture(config,send);fixture.event('fixture_started')
    try:
        for line in sys.stdin:fixture.dispatch(json.loads(line))
    finally:fixture.finish();fixture.event('fixture_stopped')


if __name__=='__main__':main()
