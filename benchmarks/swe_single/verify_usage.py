#!/usr/bin/env python3
"""Independently replay raw responses to verify final, not initial, usage snapshots."""
import argparse
import hashlib
import json
from pathlib import Path

from accounting import summarize_requests
from relay import Observation


def verify(campaign):
    results = {}
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
        results[ledger['run_id']] = dict(summary=summarize_requests(rows),
            ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            forwarded_attempts=[dict(request_index=r['request_index'],
                final_usage_observed=r.get('final_usage_observed', False),
                terminal=r.get('terminal'), settled=r.get('settled'),
                replay_error=r.get('offline_replay_error')) for r in rows if r.get('forwarded')])
    payload = dict(runs=results,
        semantics='Derived from retained raw responses; original ledgers/results are unchanged. Final usage evidence is mandatory.',
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (campaign / 'validated-accounting.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    verify(parser.parse_args().campaign)
