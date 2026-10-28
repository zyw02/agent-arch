#!/usr/bin/env python3
"""Scripted protocol provider; emits complete native multi-tool responses."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import time
from native_read_probe import schemas


def response_parts(body,decision,identifier):
    calls=decision.get('calls',[]);text=decision.get('text','');anthropic=body.get('_anthropic',False)
    if anthropic:
        blocks=[dict(type='tool_use',id=c['id'],name=c['name'],input=c['arguments']) for c in calls] if calls else [dict(type='text',text=text)]
        message=dict(id=identifier,type='message',role='assistant',model='fixture-model',content=blocks,stop_reason='tool_use' if calls else 'end_turn',stop_sequence=None,usage=dict(input_tokens=1,output_tokens=1))
        if not body.get('stream'):return message,None
        events=[('message_start',dict(type='message_start',message={**message,'content':[],'stop_reason':None,'usage':dict(input_tokens=1,output_tokens=0)}))]
        for index,block in enumerate(blocks):
            call=block['type']=='tool_use';start={**block,'input':{}} if call else dict(type='text',text='')
            delta=dict(type='input_json_delta',partial_json=json.dumps(block['input'])) if call else dict(type='text_delta',text=block['text'])
            events.extend([('content_block_start',dict(type='content_block_start',index=index,content_block=start)),('content_block_delta',dict(type='content_block_delta',index=index,delta=delta)),('content_block_stop',dict(type='content_block_stop',index=index))])
        events.extend([('message_delta',dict(type='message_delta',delta=dict(stop_reason=message['stop_reason'],stop_sequence=None),usage=dict(output_tokens=1))),('message_stop',dict(type='message_stop'))])
        return message,[(('event: '+event+'\ndata: '+json.dumps(data)+'\n\n').encode()) for event,data in events]
    message=dict(role='assistant',content=None if calls else text)
    if calls:message['tool_calls']=[dict(id=c['id'],type='function',function=dict(name=c['name'],arguments=json.dumps(c['arguments']))) for c in calls]
    reason='tool_calls' if calls else 'stop';usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2)
    response=dict(id=identifier,object='chat.completion',created=int(time.time()),model='fixture-model',choices=[dict(index=0,message=message,finish_reason=reason)],usage=usage)
    if not body.get('stream'):return response,None
    delta=dict(message)
    if calls:delta['tool_calls']=[dict(index=i,**c) for i,c in enumerate(message['tool_calls'])]
    chunks=[dict(id=identifier,object='chat.completion.chunk',created=response['created'],model='fixture-model',choices=[dict(index=0,delta=part,finish_reason=finish)]) for part,finish in [(delta,None),({},reason)]]
    chunks[-1]['usage']=usage
    return response,[('data: '+json.dumps(chunk)+'\n\n').encode() for chunk in chunks]+[b'data: [DONE]\n\n']


class ToolProvider:
    def __init__(self,decide):
        self.requests=[];self.lock=threading.Lock();owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                raw=json.dumps(dict(object='list',data=[dict(id='fixture-model',object='model')])).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_POST(self):
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4*1024**2:self.send_error(413);return
                body=json.loads(self.rfile.read(size));row=dict(arrived_ns=time.monotonic_ns(),endpoint=self.path,request=body,schemas=schemas(body))
                with owner.lock:owner.requests.append(row);index=len(owner.requests)
                if index>50:self.send_error(429);row['fixture_error']='request_limit';return
                try:
                    decision=decide(body);row['decision']=decision;payload=dict(body,_anthropic=self.path.endswith('/messages'));response,events=response_parts(payload,decision,'hd_response_'+str(index));row['response']=response
                    self.send_response(200);self.send_header('Content-Type','text/event-stream' if events else 'application/json');self.end_headers();row['response_started_ns']=time.monotonic_ns()
                    for part in events if events else [json.dumps(response).encode()]:self.wfile.write(part);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError) as error:row['fixture_transport_error']=type(error).__name__
                except Exception as error:row['fixture_error']=type(error).__name__;self.send_error(500)
                finally:row['settled_ns']=time.monotonic_ns()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    @property
    def base(self):return f'http://127.0.0.1:{self.server.server_port}/v1'
    def close(self):self.server.shutdown();self.server.server_close()
