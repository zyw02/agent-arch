#!/usr/bin/env python3
"""Independently replay raw responses to verify final, not initial, usage snapshots."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from accounting import summarize_requests
from relay import Observation


def verify(campaign):
    results = {}
    requests = []
    for ledger_path in sorted((campaign / 'runs').glob('*/provider/ledger.json')):
        ledger = json.loads(ledger_path.read_text())
        rows = []
        for original in ledger['records']:
            row = dict(original)
            row['final_usage_observed'] = False
            if row.get('forwarded') and row.get('api'):
                folder = ledger_path.parent / f"{row['request_index']:04d}"
                observer = Observation(row['api'], row)
                row['usage_events'] = []
                try:
                    if row.get('stream'):
                        for raw in (folder / 'events.jsonl').read_text().splitlines():
                            event = json.loads(raw)
                            observer.event(event['event'], event['monotonic_ns'])
                    else:
                        observer.event(json.loads((folder / 'response.raw').read_text()), row.get('ended_ns', 0))
                except (OSError, ValueError, KeyError) as exc:
                    row['offline_replay_error'] = type(exc).__name__
                observer.finish()
            rows.append(row)
            normalized = row.get('normalized_usage') or {}
            request = dict(run_id=ledger['run_id'], request_index=row['request_index'],
                api=row.get('api'), path=row.get('path'), started_utc=row.get('started_utc'),
                forwarded=row.get('forwarded'), blocked_reason=row.get('blocked_reason'),
                http_status=row.get('http_status'), terminal=row.get('terminal'),
                terminal_kind=row.get('terminal_kind'), settled=row.get('settled'),
                final_usage_observed=row.get('final_usage_observed', False),
                core_usage_complete=normalized.get('core_complete', False),
                known_final_core_usage=bool(normalized.get('core_complete') and row.get('final_usage_observed')),
                missing_reason=normalized.get('missing_reason'),
                replay_error=row.get('offline_replay_error'),
                request_bytes=row.get('upstream_request_bytes'), response_bytes=row.get('response_bytes'),
                model_emitted_tool_calls=len(row.get('model_emitted_tool_calls', [])))
            for label, key in (('duration_seconds', 'ended_ns'),
                               ('headers_seconds', 'headers_ns'),
                               ('first_byte_seconds', 'first_byte_ns'),
                               ('first_meaningful_event_seconds', 'first_meaningful_event_ns')):
                request[label] = ((row[key] - row['started_ns']) / 1e9
                                  if row.get(key) is not None and row.get('started_ns') is not None else None)
            for key in ('input_total', 'input_noncache_billed', 'cache_read', 'cache_write',
                        'output_total', 'reasoning_subset'):
                request[key] = normalized.get(key)
            requests.append(request)
        results[ledger['run_id']] = dict(summary=summarize_requests(rows),
            ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            forwarded_attempts=[dict(request_index=r['request_index'],
                final_usage_observed=r.get('final_usage_observed', False),
                terminal=r.get('terminal'), settled=r.get('settled'),
                replay_error=r.get('offline_replay_error')) for r in rows if r.get('forwarded')])
    payload = dict(runs=results,
        semantics='Derived from retained raw responses; original ledgers/results are unchanged. Final usage evidence is mandatory.',
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependency_sha256={name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                           for name in ('accounting.py', 'relay.py')})
    (campaign / 'validated-accounting.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    if requests:
        with (campaign / 'requests.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(requests[0]))
            writer.writeheader()
            writer.writerows(requests)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    verify(parser.parse_args().campaign)
