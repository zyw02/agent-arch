#!/usr/bin/env python3
"""Enumerate protocol units; execution profiles and product adapters are selected later."""
import itertools
import json
from pathlib import Path

campaign = json.loads((Path(__file__).parent / 'campaign.json').read_text())
rows = []
for case in campaign['cases']:
    for condition in case['conditions']:
        factors = dict(case.get('factors', {}))
        factors.update(case.get('condition_factors', {}).get(condition, {}))
        keys = sorted(factors)
        for values in itertools.product(*(factors[k] for k in keys)):
            selected = dict(zip(keys, values))
            suffix = ''.join(f'_{k}-{selected[k]}' for k in keys)
            for unit in range(1, case['independent_units_per_condition'] + 1):
                rows.append({'unit_id': f"{case['id']}_{condition}{suffix}_r{unit:02d}",
                             'case': case['id'], 'condition': condition, 'factors': selected,
                             'repeat': unit, 'track': case['track']})
assert len({r['unit_id'] for r in rows}) == len(rows)
print(json.dumps(rows, indent=2))
