#!/usr/bin/env python3
"""Validate a focused two-layer design and enumerate complete comparison blocks."""
import json
from pathlib import Path

DIMENSIONS = {'Reliability', 'Security', 'Performance', 'Resource & cost', 'Extensibility', 'Observability'}
STUDIES = {'platform': {'PA', 'PB', 'PC'}, 'harness': {'HA', 'HB', 'HC'}}


def plan_core(config):
    if config['profiles_per_product'] != 1 or config['long_soak_enabled'] is not False:
        raise ValueError('One declared profile per product; no default long soak')
    if len(config['products']) != 3 or set(config['products']) != {'Codex', 'DSH', 'OpenClaw'}:
        raise ValueError('Expected three distinct products')
    if set(config['dimensions']) != DIMENSIONS or set(config['layers']) != set(STUDIES):
        raise ValueError('Expected two layers and six dimensions')
    policy = config['execution_policy']
    if policy.get('scheduling_unit') != 'complete_comparison_block':
        raise ValueError('Schedule complete comparison blocks')
    if policy.get('campaign_wall_cutoff_seconds') is not None or policy.get('universal_unit_timeout_seconds') is not None:
        raise ValueError('Scope must not be controlled by truncating active comparisons')
    if policy.get('duration_control') != 'reduce_scope_before_admission':
        raise ValueError('Control duration before block admission')
    rows, blocks = [], []
    for layer, ids in STUDIES.items():
        selected = [s for s in config['studies'] if s['layer'] == layer]
        if len(selected) != 3 or {s['id'] for s in selected} != ids:
            raise ValueError(f'Expected three focused studies in {layer}')
        coverage = set()
        for study in selected:
            if len(study['primary_dimensions']) != 2 or not set(study['primary_dimensions']) <= DIMENSIONS:
                raise ValueError('Each study must focus on two primary dimensions')
            coverage.update(study['primary_dimensions'])
        if coverage != DIMENSIONS:
            raise ValueError(f'Missing primary dimension coverage in {layer}')
    if len(config['studies']) != 6:
        raise ValueError('Core design must contain six studies')
    for study in config['studies']:
        for field in ('question', 'alternative_explanations', 'required_observations', 'intervention',
                      'inference_rule', 'limit_and_tradeoff', 'completion_requirements'):
            if not study.get(field):
                raise ValueError(f'Missing evidence contract: {study["id"]}/{field}')
        conditions = study['conditions']
        if not 2 <= len(conditions) <= 5 or len(set(conditions)) != len(conditions):
            raise ValueError('Each study needs two to five distinct arms')
        if type(study['complete_blocks']) is not int or study['complete_blocks'] != 2:
            raise ValueError('Default is two complete blocks; extra repetitions need a separate extension plan')
        controls = study['control_conditions']
        if set(controls) != set(conditions) or not set(controls.values()) <= set(conditions):
            raise ValueError('Every arm needs a control in the same complete block')
        for product in config['products']:
            for repeat in range(1, study['complete_blocks'] + 1):
                block_id = f'{product}/{study["id"]}/b{repeat}'
                unit_ids = [f'{block_id}/{condition}' for condition in conditions]
                blocks.append({'block_id': block_id, 'product': product, 'study': study['id'],
                               'layer': study['layer'], 'dimensions': study['primary_dimensions'],
                               'unit_ids': unit_ids, 'admission': 'requires_calibration_and_whole_block_estimate',
                               'completion_requirements': study['completion_requirements'], 'plan_only': True})
                for condition, unit_id in zip(conditions, unit_ids):
                    rows.append({'unit_id': unit_id, 'block_id': block_id, 'product': product,
                                 'study': study['id'], 'layer': study['layer'], 'condition': condition,
                                 'repeat': repeat, 'control_unit_id': f'{block_id}/{controls[condition]}',
                                 'plan_only': True})
    return {'revision': config['revision'], 'plan_only': True, 'runtime_ready': False,
            'scope': {'studies': 6, 'complete_blocks': len(blocks), 'planned_arms': len(rows),
                      'duration_estimate': 'pending pilot; not a fixed runtime promise'},
            'execution_policy': policy, 'studies': config['studies'], 'blocks': blocks, 'units': rows}


if __name__ == '__main__':
    print(json.dumps(plan_core(json.loads(Path(__file__).with_name('architecture-core.json').read_text())), indent=2))
