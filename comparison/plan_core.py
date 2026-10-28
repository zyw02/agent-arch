#!/usr/bin/env python3
"""Validate a focused two-layer design and enumerate complete comparison blocks."""
import json
from pathlib import Path

DIMENSIONS = {'Reliability', 'Security', 'Performance', 'Resource & cost', 'Extensibility', 'Observability'}
STUDIES = {'platform': {'PA', 'PB', 'PC'}, 'harness': {'HA', 'HB', 'HC', 'HD', 'HE', 'HF', 'HG'}}


MECHANISMS = {
    'HA': {'context_adoption', 'native_memory_write_update', 'cross_session_persistence', 'native_memory_retrieval', 'current_instruction_precedence'},
    'HB': {'native_delegation', 'result_join', 'partial_failure', 'parent_child_cancellation'},
    'HC': {'approval_dispatch_binding', 'untrusted_content_boundary', 'child_authority_attenuation', 'cross_session_memory_isolation',
           'sandbox_filesystem_enforcement', 'sandbox_network_enforcement', 'sandbox_descendant_inheritance'},
    'HD': {'public_tool_integration', 'tool_dispatch_and_partial_failure', 'native_trace_reconstruction'},
    'HE': {'restored_state_adoption', 'native_snapshot_scope', 'rollback_state_consistency', 'external_effect_boundary'},
    'HF': {'parent_child_budget_accounting', 'budget_overshoot_and_inflight', 'native_cumulative_budget', 'budget_dispatch_enforcement'},
    'HG': {'persistent_behavior_version', 'update_authorization_and_validation', 'native_update_reversal', 'native_feedback_update', 'heldout_transfer_and_regression'},
}


REQUIRED_CONTROLS = {
    'HA': {'history_compacted': 'history_uncompacted', 'fresh_session_memory_enabled': 'fresh_session_memory_disabled'},
    'HB': {'native_two_children': 'single_agent_same_work', 'one_child_failure': 'native_two_children', 'parent_cancellation': 'native_two_children'},
    'HC': {'binding_violation': 'binding_control', 'untrusted_content_injection': 'untrusted_content_control',
           'child_scope_escalation': 'child_scope_control', 'memory_scope_cross_access': 'memory_scope_control', 'sandbox_denied': 'sandbox_allowed'},
    'HD': {'public_extension_tool': 'native_tool', 'four_extension_reads_batched': 'four_extension_reads_serial_reference',
           'four_extension_reads_one_failure': 'four_extension_reads_batched'},
    'HE': {'interrupted_native_resume': 'uninterrupted_state_control', 'interrupted_snapshot_restore': 'interrupted_native_resume'},
    'HF': {'single_budget_exhausted': 'single_budget_sufficient', 'children_budget_exhausted': 'children_budget_sufficient'},
    'HG': {'native_policy_update': 'frozen_policy', 'native_update_reverted': 'native_policy_update'},
}


CROSS_CUTTING_CHECKS = {'native_log_durability', 'causal_trace_reconstruction', 'usage_reconciliation', 'synthetic_secret_redaction'}


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
    evidence = config.get('cross_cutting_evidence', {})
    if not CROSS_CUTTING_CHECKS <= set(evidence.get('mechanism_checks', [])):
        raise ValueError('Missing cross-cutting observability mechanism')
    for field in ('required_observations', 'inference_rule', 'limit_and_tradeoff'):
        if not evidence.get(field):
            raise ValueError(f'Missing cross-cutting evidence contract: {field}')
    rows, blocks = [], []
    for layer, ids in STUDIES.items():
        selected = [s for s in config['studies'] if s['layer'] == layer]
        if len(selected) != len(ids) or {s['id'] for s in selected} != ids:
            raise ValueError(f'Expected {len(ids)} focused studies in {layer}')
        coverage = set()
        for study in selected:
            if len(study['primary_dimensions']) != 2 or not set(study['primary_dimensions']) <= DIMENSIONS:
                raise ValueError('Each study must focus on two primary dimensions')
            coverage.update(study['primary_dimensions'])
        if coverage != DIMENSIONS:
            raise ValueError(f'Missing primary dimension coverage in {layer}')
    if len(config['studies']) != sum(map(len, STUDIES.values())):
        raise ValueError('Core design must contain ten studies')
    for study in config['studies']:
        for field in ('question', 'alternative_explanations', 'required_observations', 'intervention',
                      'inference_rule', 'limit_and_tradeoff', 'completion_requirements'):
            if not study.get(field):
                raise ValueError(f'Missing evidence contract: {study["id"]}/{field}')
        if not MECHANISMS.get(study['id'], set()) <= set(study.get('mechanism_checks', [])):
            raise ValueError(f'Missing required harness mechanism: {study["id"]}')
        conditions = study['conditions']
        if not 2 <= len(conditions) <= (10 if study['id'] == 'HC' else 5) or len(set(conditions)) != len(conditions):
            raise ValueError('Unexpected or duplicate study arms')
        if type(study['complete_blocks']) is not int or study['complete_blocks'] != 2:
            raise ValueError('Default is two complete blocks; extra repetitions need a separate extension plan')
        controls = study['control_conditions']
        if set(controls) != set(conditions) or not set(controls.values()) <= set(conditions):
            raise ValueError('Every arm needs a control in the same complete block')
        for arm, control in REQUIRED_CONTROLS.get(study['id'], {}).items():
            if controls.get(arm) != control:
                raise ValueError(f'Missing matched mechanism control: {study["id"]}/{arm}')
        for product in config['products']:
            for repeat in range(1, study['complete_blocks'] + 1):
                block_id = f'{product}/{study["id"]}/b{repeat}'
                unit_ids = [f'{block_id}/{condition}' for condition in conditions]
                blocks.append({'block_id': block_id, 'product': product, 'study': study['id'],
                               'layer': study['layer'], 'dimensions': study['primary_dimensions'],
                               'unit_ids': unit_ids, 'admission': 'requires_calibration_and_whole_block_estimate',
                               'completion_requirements': study['completion_requirements'],
                               'mechanism_checks': study.get('mechanism_checks', []),
                               'cross_cutting_evidence': evidence, 'plan_only': True})
                for condition, unit_id in zip(conditions, unit_ids):
                    rows.append({'unit_id': unit_id, 'block_id': block_id, 'product': product,
                                 'study': study['id'], 'layer': study['layer'], 'condition': condition,
                                 'repeat': repeat, 'control_unit_id': f'{block_id}/{controls[condition]}',
                                 'plan_only': True})
    return {'revision': config['revision'], 'plan_only': True, 'runtime_ready': False,
            'scope': {'studies': len(config['studies']), 'complete_blocks': len(blocks), 'planned_arms': len(rows),
                      'duration_estimate': 'pending pilot; not a fixed runtime promise'},
            'cross_cutting_evidence': evidence, 'execution_policy': policy, 'studies': config['studies'], 'blocks': blocks, 'units': rows}


if __name__ == '__main__':
    print(json.dumps(plan_core(json.loads(Path(__file__).with_name('architecture-core.json').read_text())), indent=2))
