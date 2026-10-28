#!/usr/bin/env python3
"""Validate and enumerate a bounded architecture study plan; never execute it."""
import json
from pathlib import Path


def plan_core(config):
    if config['profiles_per_product'] != 1 or config['long_soak_enabled'] is not False:
        raise ValueError('Core plan allows one profile per product and no long soak')
    products = config['products']
    if len(products) != len(set(products)) or set(products) != {'Codex', 'DSH', 'OpenClaw'}:
        raise ValueError('Freeze exactly three distinct product configurations')
    for field in ('unit_timeout_seconds', 'setup_seconds_per_product', 'max_units_per_product',
                  'max_aggregate_runner_seconds', 'max_wall_seconds'):
        if type(config[field]) is not int or config[field] <= 0:
            raise ValueError(f'Invalid budget: {field}')
    if config['max_aggregate_runner_seconds'] > 14400 or config['max_wall_seconds'] > 14400:
        raise ValueError('Core campaign exceeds the four-hour core budget')
    rows = []
    for study in config['studies']:
        for field in ('question', 'alternative_explanations', 'required_observations', 'intervention', 'inference_rule', 'limit_and_tradeoff'):
            if not study.get(field):
                raise ValueError(f'Missing architecture evidence contract: {study["id"]}/{field}')
        if type(study['repetitions']) is not int or study['repetitions'] <= 0 or not study['conditions']:
            raise ValueError('Invalid study size')
        for product in products:
            for condition in study['conditions']:
                for repeat in range(1, study['repetitions'] + 1):
                    rows.append({'unit_id': f'{product}/{study["id"]}/{condition}/{repeat}', 'product': product,
                                 'study': study['id'], 'condition': condition, 'repeat': repeat,
                                 'timeout_seconds': config['unit_timeout_seconds'], 'plan_only': True})
    if len({r['unit_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate unit IDs')
    if any(sum(r['product'] == p for r in rows) > config['max_units_per_product'] for p in products):
        raise ValueError('Per-product unit budget exceeded')
    seconds = len(rows) * config['unit_timeout_seconds'] + len(products) * config['setup_seconds_per_product']
    if seconds > min(config['max_aggregate_runner_seconds'], config['max_wall_seconds']):
        raise ValueError('Worst-case setup plus unit time exceeds campaign budget')
    return {'revision': config['revision'], 'plan_only': True, 'runtime_ready': False,
            'budget': {'units': len(rows), 'setup_seconds': len(products) * config['setup_seconds_per_product'],
                       'unit_seconds': len(rows) * config['unit_timeout_seconds'], 'worst_case_runner_seconds': seconds,
                       'wall_limit_seconds': config['max_wall_seconds']},
            'studies': config['studies'], 'units': rows}


if __name__ == '__main__':
    print(json.dumps(plan_core(json.loads(Path(__file__).with_name('architecture-core.json').read_text())), indent=2))
