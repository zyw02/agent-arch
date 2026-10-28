#!/usr/bin/env python3
"""Expand frozen scenario factors into product-independent planned units."""
import itertools
import json
from pathlib import Path

campaign = json.loads((Path(__file__).parent / 'campaign.json').read_text())
rows = []
for case in campaign['cases']:
    for condition in case['conditions']:
        tracks = case.get('condition_tracks', {}).get(condition, case.get('tracks', [case['track']]))
        for track in tracks:
            factors = dict(case.get('factors', {}))
            factors.update(case.get('condition_factors', {}).get(condition, {}))
            factors.update(case.get('track_factors', {}).get(track, {}))
            keys = sorted(factors)
            for values in itertools.product(*(factors[k] for k in keys)):
                selected = dict(zip(keys, values))
                suffix = ''.join(f'_{k}-{selected[k]}' for k in keys)
                for unit in range(1, case['independent_units_per_condition'] + 1):
                    rows.append({'unit_id': f"{case['id']}_{condition}_{track}{suffix}_r{unit:02d}",
                                 'case': case['id'], 'condition': condition, 'factors': selected,
                                 'repeat': unit, 'track': track})
assert len({r['unit_id'] for r in rows}) == len(rows)
assert all(r['track'] != 'model_and_scripted' for r in rows)
assert all(any(c['case'] == r['case'] and c['track'] == r['track'] and c['condition'] == 'C0' for c in rows) for r in rows)
for track in ('N', 'C'):
    for condition in ('C0', 'C1'):
        for size in (8, 64, 256):
            matching = [r for r in rows if r['case'] == 'H04' and r['track'] == track and r['condition'] == condition and r['factors']['size_kib'] == size]
            assert len(matching) == 15 and {r['factors']['instance'] for r in matching} == set(range(1, 6))
for track in ('N', 'C'):
    paired = [r for r in rows if r['case'] == 'H03' and r['condition'] == 'C4' and r['track'] == track]
    assert len(paired) == 30 and {r['factors']['arm'] for r in paired} == {'compacted', 'uncompacted'}
assert {r['factors']['idempotency'] for r in rows if r['case'] == 'H05' and r['condition'] == 'C0'} == {'on', 'off'}
assert {(r['factors']['family'], r['factors']['instance']) for r in rows if r['case'] == 'H18'} == {(f, i) for f in ('repository', 'data', 'effect') for i in range(1, 6)}
print(json.dumps(rows, indent=2))
