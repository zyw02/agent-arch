#!/usr/bin/env python3
"""Expand planned units with matched controls; this never schedules experiments."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

BASE_OBSERVATIONS = {'native_outcome', 'independent_oracle'}
EXTENSIONS = {'P01': {'healthy_session_baseline', 'healthy_session_outcome', 'collateral_impact'},
              'P02': {'instruction_retention', 'completed_receipt', 'pending_operation', 'repeat_count'},
              'H14': {'state_policy_usage_owner'}}


def validate_load_freeze(path):
    freeze = json.loads(path.read_text())
    levels = freeze.get('selected_arrival_intervals_s', [])
    if len(levels) != 2 or len(set(levels)) != 2 or not set(levels) <= {'2', '0.5', '0.1'}:
        raise ValueError('Select two distinct common candidate levels')
    if freeze.get('capacity_controls_passed') is not True or not freeze.get('selection_rationale'):
        raise ValueError('Capacity controls and selection rationale are required')
    for field in ('fixture_capacity', 'observer_overhead'):
        entry = freeze.get(field, {})
        if not entry.get('path') or not entry.get('sha256'):
            raise ValueError(f'Missing {field} evidence')
        data = (path.parent / entry['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'Checksum mismatch: {field}')
    for field in ('max_generator_delay_ms', 'max_fixture_p95_ms', 'max_observer_cpu_percent',
                  'stop_memory_percent', 'stop_processes', 'stop_generator_delay_ms'):
        value = freeze.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float('inf'):
            raise ValueError(f'Missing positive threshold: {field}')
        if field.endswith('percent') and value > 100:
            raise ValueError(f'Percentage exceeds 100: {field}')
    return freeze


def expand(campaign, freeze=None):
    rows = []
    for case in campaign['cases']:
        if not (BASE_OBSERVATIONS | EXTENSIONS.get(case['id'], set())) <= set(case['required_observations']):
            raise ValueError(f"Missing required observations: {case['id']}")
        if case['id'] == 'P02' and set(case.get('factors', {}).get('state_contract', [])) != {'conversation', 'state_consistency'}:
            raise ValueError('Missing P02 state-contract variants')
        if case['id'] == 'H04' and set(case.get('factors', {}).get('task_kind', [])) != {'markers', 'distributed_aggregate'}:
            raise ValueError('Missing H04 task variants')
        if case['id'] == 'H14':
            for condition in ('C5', 'C6', 'C7'):
                if set(case.get('condition_factors', {}).get(condition, {}).get('integration_state', [])) != {'normal', 'failure', 'cancel'}:
                    raise ValueError('Missing H14 integration variants')
        if case['id'] == 'P03':
            if case.get('condition_controls', {}).get('C5') != 'C6' or 'C6' not in case['conditions']:
                raise ValueError('P03 C5 requires a tool positive control C6')
            if set(case.get('condition_factors', {}).get('C6', {}).get('admission', [])) != {'direct', 'external_fifo'}:
                raise ValueError('P03 tool control must cover both admission modes')
            for condition in ('C5', 'C6'):
                if not {'tool_call_receipt', 'tool_result_match'} <= set(case.get('condition_required_observations', {}).get(condition, [])):
                    raise ValueError('P03 tool conditions require independent tool evidence')
            if case.get('condition_control_match_factors', {}).get('C5') != ['admission']:
                raise ValueError('P03 C5 must match its control admission mode')
        for condition in case['conditions']:
            for track in case.get('condition_tracks', {}).get(condition, case.get('tracks', ['D'])):
                factors = dict(case.get('factors', {}))
                factors.update(case.get('condition_factors', {}).get(condition, {}))
                factors.update(case.get('track_factors', {}).get(track, {}))
                keys = sorted(factors)
                for values in itertools.product(*(factors[k] for k in keys)):
                    chosen = dict(zip(keys, values))
                    suffix = ''.join(f'_{k}-{chosen[k]}' for k in keys)
                    repeats = case.get('track_repetitions', {}).get(track, case['independent_units_per_condition'])
                    for repeat in range(1, repeats + 1):
                        gate = case.get('gated_conditions', {}).get(condition)
                        gate_satisfied = not gate or bool(freeze and chosen['arrival_interval_s'] in freeze['selected_arrival_intervals_s'])
                        contract = None
                        if case['id'] == 'H14' and condition in ('C5', 'C6', 'C7'):
                            state = chosen['integration_state']
                            contract = case.get('acceptance_contracts', {}).get(condition, {}).get(state)
                            required = {'boundary', 'intervention', 'terminal_outcomes', 'task_timeout_s',
                                        'quiescence_deadline_s', 'followup_s', 'hash_rule',
                                        'required_evidence', 'forbidden_effects', 'allowed_residue', 'result_rule',
                                        'cancellation_effective_deadline_s'}
                            if not contract or not required <= contract.keys():
                                raise ValueError(f'Missing H14 acceptance contract: {condition}/{state}')
                            if state != 'normal' and contract['hash_rule'] != 'diagnostic_only':
                                raise ValueError('Fault/cancel hashes must not use normal success acceptance')
                            if state == 'cancel' and (contract['cancellation_effective_deadline_s'] != 10 or contract['quiescence_deadline_s'] != 10 or contract['followup_s'] != [0.5, 2, 10]):
                                raise ValueError('H14 cancellation must have bounded follow-up')
                        observations = list(dict.fromkeys(case['required_observations'] + case.get('condition_required_observations', {}).get(condition, [])))
                        rows.append(dict(unit_id=f"{case['id']}_{condition}_{track}{suffix}_r{repeat:02d}",
                                         case=case['id'], condition=condition, track=track, repeat=repeat,
                                         factors=chosen, required_observations=observations, acceptance_contract=contract,
                                         load_gate=gate, load_gate_satisfied=gate_satisfied, plan_only=True))
    if len({r['unit_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate IDs')
    cases = {c['id']: c for c in campaign['cases']}
    for row in rows:
        case = cases[row['case']]
        target = case.get('condition_controls', {}).get(row['condition'], 'C0')
        match = set(case.get('condition_control_match_factors', {}).get(row['condition'], case['control_match_factors'])) | ({'instance'} if 'instance' in row['factors'] else set())
        controls = [r for r in rows if r['case'] == row['case'] and r['track'] == row['track']
                    and r['condition'] == target and r['repeat'] == row['repeat']
                    and all(r['factors'].get(k) == row['factors'].get(k) for k in match)]
        if len(controls) != 1:
            raise ValueError(f"Missing or ambiguous control: {row['unit_id']}")
        row['control_unit_id'] = controls[0]['unit_id']
        reference = case.get('performance_references', {}).get(row['condition'])
        if reference:
            row['performance_reference_unit_id'] = next(r['unit_id'] for r in rows
                if r['case'] == row['case'] and r['condition'] == reference
                and r['track'] == row['track'] and r['repeat'] == row['repeat'])
        if row['case'] == 'H14' and 'integration_state' in row['factors']:
            normal = dict(row['factors'], integration_state='normal')
            row['integration_control_unit_id'] = next(r['unit_id'] for r in rows if r['case'] == row['case']
                and r['condition'] == row['condition'] and r['track'] == row['track']
                and r['repeat'] == row['repeat'] and r['factors'] == normal)
        if row['case'] == 'H03' and row['condition'] == 'C4':
            other = dict(row['factors'], arm='uncompacted' if row['factors']['arm'] == 'compacted' else 'compacted')
            row['paired_unit_id'] = next(r['unit_id'] for r in rows if r['case'] == row['case']
                and r['condition'] == row['condition'] and r['track'] == row['track']
                and r['repeat'] == row['repeat'] and r['factors'] == other)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('core', 'full'), default='core')
    parser.add_argument('--load-freeze', type=Path)
    args = parser.parse_args()
    if args.profile == 'core':
        if args.load_freeze:
            parser.error('--load-freeze belongs to the explicitly selected full profile')
        from plan_core import plan_core
        print(json.dumps(plan_core(json.loads(Path(__file__).with_name('architecture-core.json').read_text())), indent=2))
        raise SystemExit(0)
    campaign = json.loads(Path(__file__).with_name('campaign.json').read_text())
    freeze = validate_load_freeze(args.load_freeze) if args.load_freeze else None
    print(json.dumps(expand(campaign, freeze), indent=2))
