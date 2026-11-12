#!/usr/bin/env python3
"""Small live protocol check, separate from scored benchmark attempts."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.request

from relay import Relay
from suite import selected_protocol
from validated_controls import check_response_integrity, control_source_hashes


def run(output):
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        raise ValueError('DEEPSEEK_API_KEY is absent; no live preflight launched')
    output.mkdir(parents=True, exist_ok=False)
    request = urllib.request.Request('https://api.deepseek.com/models',
                                     headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(request,timeout=60) as response:
        models = json.load(response)
    (output/'model-discovery.json').write_text(json.dumps(models,indent=2)+'\n')
    model = next(m for m in models['data'] if m['id']=='deepseek-flash')
    if model.get('max_output_tokens',0)<65536:
        raise ValueError('Provider does not advertise the corrected output budget')
    protocol = selected_protocol('openclaw57_patched','pytest-dev__pytest-7236',validated=True)
    relay = Relay.from_protocol(key,'127.0.0.1',output/'provider','protocol-preflight-only',protocol)
    probes=[]
    try:
        for api,route in [('chat','/v1/chat/completions'),('messages','/anthropic/v1/messages'),
                          ('responses','/v1/responses')]:
            for mode in ('main-high','auxiliary-disabled'):
                body=dict(model='deepseek-flash',stream=True)
                if api=='responses':
                    body['input']='Reply with READY only.'
                    if mode=='auxiliary-disabled':
                        body.update(reasoning=dict(effort='none'),max_output_tokens=4096)
                else:
                    body['messages']=[dict(role='user',content='Reply with READY only.')]
                    if mode=='auxiliary-disabled':
                        body.update(thinking=dict(type='disabled'),max_tokens=4096)
                request=urllib.request.Request(relay.base+route,data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=600) as response:
                    response.read()
                probes.append(dict(api=api,mode=mode,request_index=len(relay.records)-1))
        deadline=time.monotonic()+45
        while any(not r['settled'] for r in relay.records) and time.monotonic()<deadline:
            time.sleep(.05)
    finally:
        relay.close()
    integrity=check_response_integrity(relay.records)
    summary=json.loads((output/'provider/ledger.json').read_text())['summary']
    complete=(len(probes)==6 and integrity['clean'] and summary['usage_complete'] and
              all(r.get('http_status')==200 for r in relay.records))
    report=dict(complete=complete,probes=probes,response_integrity=integrity,
        accounting=summary,model=model,scope='Six tiny protocol probes only; not framework or task performance validation',
        control_source_hashes=control_source_hashes(),controller_sha=os.environ.get('GITHUB_SHA'),
        credentials_retained=False)
    (output/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(complete=complete,probes=len(probes),integrity=integrity)))
    if not complete:
        raise ValueError('Protocol preflight failed; formal benchmark must not be admitted')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
