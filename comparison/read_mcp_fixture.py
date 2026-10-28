#!/usr/bin/env python3
"""Owned stdio MCP read fixture; only exposes one fixed synthetic file."""
import argparse
import json
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--file',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);args=p.parse_args()
    for line in sys.stdin:
        message=json.loads(line);method=message.get('method');identifier=message.get('id')
        if identifier is None:continue
        result={};error=None
        if method=='initialize':
            result=dict(protocolVersion=message.get('params',{}).get('protocolVersion','2025-03-26'),capabilities=dict(tools={}),serverInfo=dict(name='owned-read-fixture',version='1.0.0'))
        elif method=='tools/list':
            result=dict(tools=[dict(name='eval_read',description='Read the fixed synthetic evaluation file',inputSchema=dict(type='object',properties={},additionalProperties=False))])
        elif method=='tools/call':
            if message.get('params',{}).get('name')!='eval_read':error=dict(code=-32602,message='Unknown owned tool')
            else:
                start=time.monotonic_ns();text=args.file.read_text()
                with args.ledger.open('a') as f:f.write(json.dumps(dict(kind='owned-mcp-read',start_ns=start,end_ns=time.monotonic_ns(),bytes=len(text.encode()),call_id=identifier))+'\n')
                result=dict(content=[dict(type='text',text=text)])
        elif method in ('resources/list','resources/templates/list','prompts/list'):
            result={('resourceTemplates' if method=='resources/templates/list' else method.split('/')[0]):[]}
        elif method!='ping':error=dict(code=-32601,message='Method not supported by owned fixture')
        response=dict(jsonrpc='2.0',id=identifier)
        response.update(error=error) if error else response.update(result=result)
        print(json.dumps(response),flush=True)

if __name__=='__main__':main()
