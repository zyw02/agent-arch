#!/usr/bin/env python3
"""Replay two saved DSH requests directly and through the relay, without tools.

Diagnostic requests are separately billed and never included in benchmark ranks.
Historical payloads are downloaded from retained artifacts, never committed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from relay import Observation, Relay


def run(inputs, output):
    key = os.environ['DEEPSEEK_API_KEY']
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for block, request_index in ((2, 14), (3, 19)):
        candidates = list(inputs.glob(f'block-{block}/**/{request_index:04d}/request.effective.json'))
        if len(candidates) != 1:
            raise ValueError(f'Expected one original failing payload for block {block}')
        source = candidates[0]
        payload = source.read_bytes()
        ledger = json.loads((source.parent.parent/'ledger.json').read_text())
        old = ledger['records'][request_index]
        if hashlib.sha256(payload).hexdigest() != old['effective_sha256']:
            raise ValueError('Historical payload hash mismatch')
        # Alternate order to reduce a systematic direct-versus-relay time effect.
        for mode in (('direct', 'relay') if block == 2 else ('relay', 'direct')):
            target = output/f'block-{block}-{mode}'
            target.mkdir()
            row = dict(block=block, mode=mode, source_payload_sha256=hashlib.sha256(payload).hexdigest(),
                terminal=False, final_usage_observed=False, stream=True, forwarded=True)
            observer = Observation('messages', row)
            relay = None
            headers = {'Content-Type':'application/json', 'anthropic-version':'2023-06-01',
                       'User-Agent':old.get('user_agent') or 'relay-forensics'}
            if mode == 'direct':
                headers.update(Authorization='Bearer '+key, **{'x-api-key':key})
                url = 'https://api.deepseek.com/anthropic/v1/messages'
            else:
                relay = Relay(key, '127.0.0.1', target/'provider', 'forensic-only', None,
                              16384, request_timeout=540, request_policy='legacy-v1')
                url = relay.base+'/anthropic/v1/messages'
            started = time.monotonic()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=headers),
                                            timeout=600) as response, (target/'client-response.raw').open('wb') as saved:
                    row['http_status'] = response.status
                    row['response_framing'] = {k:response.headers.get(k) for k in
                        ('Content-Type','Content-Length','Transfer-Encoding','Content-Encoding')}
                    for line in response:
                        saved.write(line)
                        if line.startswith(b'data:'):
                            data = line[5:].strip()
                            if data:
                                try:
                                    observer.event(json.loads(data), time.monotonic_ns())
                                except ValueError:
                                    row['event_parse_error'] = True
            except Exception as exc:
                row['error_type'] = type(exc).__name__
                # Exception messages may contain response bodies: retain no text.
            finally:
                if relay:
                    deadline = time.monotonic()+30
                    while any(not r['settled'] for r in relay.records) and time.monotonic()<deadline:
                        time.sleep(.05)
                    relay.close()
                    row['relay_records'] = relay.records
                observer.finish()
            row['elapsed_seconds'] = time.monotonic()-started
            raw = target/'client-response.raw'
            row['client_response_bytes'] = raw.stat().st_size if raw.exists() else 0
            row['client_response_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None
            reports.append(row)
            (output/'replay.json').write_text(json.dumps(dict(
                scope='Four diagnostic calls, no tool execution, not task completion or performance measurement',
                historical_headers_not_fully_retained=True, no_hidden_retries=True,
                controller_sha=os.environ.get('GITHUB_SHA'), results=reports), indent=2)+'\n')
            print(json.dumps({k:row.get(k) for k in ('block','mode','http_status','terminal',
                              'final_usage_observed','elapsed_seconds','error_type')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.inputs, args.output)
