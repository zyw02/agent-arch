#!/usr/bin/env python3
"""Transparent DeepSeek relay for native read pilots; no evaluator answer generation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Credential-bearing provider requests cannot redirect')


def observe_event(event, row):
    if not isinstance(event,dict):return
    if event.get('type')=='message_stop':row['terminal_event']=True
    usage=event.get('usage')
    if event.get('type')=='message_start':usage=event.get('message',{}).get('usage',usage)
    if usage:row['usage_events'].append(usage)
    block=event.get('content_block',{})
    if block.get('type')=='tool_use':row['tool_names'].append(block.get('name'))
    for choice in event.get('choices',[]):
        if choice.get('finish_reason') is not None:row['terminal_event']=True
        for call in choice.get('delta',choice.get('message',{})).get('tool_calls',[]):
            name=call.get('function',{}).get('name')
            if name:row['tool_names'].append(name)


class LiveProvider:
    live=True
    def __init__(self,file_path,receipt,target_tool='read'):
        self.requests=[];self.errors=[];key=os.environ.get('DEEPSEEK_API_KEY','')
        if not key:raise ValueError('Configured DeepSeek Actions secret required for live pilot')
        self.opener=urllib.request.build_opener(NoRedirect());owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                raw=json.dumps(dict(object='list',data=[dict(id='deepseek-flash',object='model')])).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                if self.path not in ('/v1/messages','/v1/chat/completions'):
                    self.send_error(404);return
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4*1024**2:self.send_error(413);return
                raw=self.rfile.read(size);body=json.loads(raw)
                if body.get('model')!='deepseek-flash':self.send_error(400,'Explicit pilot model required');return
                anthropic=self.path.endswith('/messages')
                endpoint='https://api.deepseek.com'+('/anthropic/v1/messages' if anthropic else '/chat/completions')
                headers={'Content-Type':'application/json','Authorization':'Bearer '+key}
                if anthropic:headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
                row=dict(monotonic_ns=time.monotonic_ns(),endpoint=self.path,upstream_endpoint=endpoint,
                    request=body,usage_events=[],tool_names=[],response_bytes=0,synthetic=False)
                owner.requests.append(row)
                request=urllib.request.Request(endpoint,data=raw,headers=headers,method='POST')
                try:
                    with owner.opener.open(request,timeout=120) as response:
                        row['http_status']=response.status;row['first_header_ns']=time.monotonic_ns()
                        content_type=response.headers.get('Content-Type','application/json')
                        self.send_response(response.status);self.send_header('Content-Type',content_type);self.end_headers()
                        if 'event-stream' in content_type:
                            for line in response:
                                row['response_bytes']+=len(line)
                                self.wfile.write(line);self.wfile.flush()
                                if line.startswith(b'data: '):
                                    payload=line[6:].strip()
                                    if payload and payload!=b'[DONE]':
                                        try:observe_event(json.loads(payload),row)
                                        except (ValueError,TypeError):row['event_parse_error']=True
                        else:
                            data=response.read(8*1024**2+1);row['response_bytes']=len(data)
                            if len(data)>8*1024**2:raise ValueError('Provider response evidence bound exceeded')
                            observe_event(json.loads(data),row);self.wfile.write(data)
                except urllib.error.HTTPError as error:
                    # Do not log upstream error bodies or authentication material.
                    row['http_status']=error.code;owner.errors.append(dict(error='upstream_http',status=error.code))
                    self.send_error(502,'Upstream provider HTTP '+str(error.code))
                except Exception as error:
                    row['transport_error']=type(error).__name__;owner.errors.append(dict(error=type(error).__name__))
                    try:self.send_error(502,'Provider transport failure')
                    except OSError:pass
                finally:row['settled_ns']=time.monotonic_ns()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    @property
    def base(self):return f'http://127.0.0.1:{self.server.server_port}/v1'
    def close(self):self.server.shutdown();self.server.server_close()


def tool_names(body):
    names=[]
    for message in body.get('messages',[]):
        for call in message.get('tool_calls',[]):names.append(call.get('function',{}).get('name'))
        if isinstance(message.get('content'),list):
            names.extend(block.get('name') for block in message['content'] if block.get('type')=='tool_use')
    return names


def real_usage(requests):
    rows=[]
    for index,request in enumerate(requests):
        # Anthropic message_delta is cumulative output; merge updates, never sum stream deltas.
        merged={}
        for event in request['usage_events']:merged.update(event)
        rows.append(dict(request_index=index,endpoint=request['endpoint'],usage=merged,
            http_status=request.get('http_status'),complete=bool(merged) and bool(request.get('terminal_event')) and not request.get('transport_error')))
    return dict(synthetic=False,requests=rows,actual_charge=None,
        method='Raw provider counters per request; cumulative stream updates merged by key. Cache/reasoning partitions are not added to inclusive counters. Invoice charge unavailable.',
        component_token_attribution='unobserved; payload bytes are not source-specific token counts')
