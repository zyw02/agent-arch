#!/usr/bin/env python3
"""Validate a focused two-layer design and enumerate complete comparison blocks."""
import json
from pathlib import Path

DIMENSIONS = {'Reliability', 'Security', 'Performance', 'Resource & cost', 'Extensibility', 'Observability'}
STUDIES = {'platform': {'PA', 'PB', 'PC'}, 'harness': {'HA', 'HB', 'HC', 'HD', 'HE', 'HF', 'HG'}}


MECHANISMS = {'HA': {'context_adoption',
        'context_retention_cost_effect',
        'context_skill_memory_assembly',
        'cross_session_persistence',
        'current_instruction_precedence',
        'native_memory_retrieval',
        'native_memory_write_update'},
 'HB': {'coordination_ownership_graph',
        'coordination_quality_cost_effect',
        'native_delegation',
        'parent_child_cancellation',
        'partial_failure',
        'result_join'},
 'HC': {'approval_dispatch_binding',
        'boundary_false_denial_and_collateral_effect',
        'child_authority_attenuation',
        'cross_session_memory_isolation',
        'policy_to_os_enforcement_graph',
        'sandbox_descendant_inheritance',
        'sandbox_filesystem_enforcement',
        'sandbox_network_enforcement',
        'untrusted_content_boundary'},
 'HD': {'extension_dispatch_ownership_graph',
        'extension_overhead_and_failure_effect',
        'logging_observer_overhead',
        'native_event_delivery_semantics',
        'native_trace_reconstruction',
        'public_tool_integration',
        'tool_dispatch_and_partial_failure'},
 'HE': {'cross_agent_session_os_blast_radius',
        'external_effect_boundary',
        'native_snapshot_scope',
        'restored_state_adoption',
        'rollback_granularity',
        'rollback_state_consistency'},
 'HF': {'budget_dispatch_enforcement',
        'budget_overshoot_and_inflight',
        'budget_skill_context_coupling',
        'native_cumulative_budget',
        'parent_child_budget_accounting',
        'quality_cost_interaction'},
 'HG': {'feedback_update_adoption_graph',
        'heldout_transfer_and_regression',
        'native_feedback_update',
        'native_update_reversal',
        'persistent_behavior_version',
        'quality_gain_cost_and_regression',
        'update_authorization_and_validation'}}


REQUIRED_CONTROLS = {'HA': {'fresh_session_memory_enabled': 'fresh_session_memory_disabled',
        'history_compacted': 'history_uncompacted'},
 'HB': {'native_two_children': 'single_agent_same_work',
        'one_child_failure': 'native_two_children',
        'parent_cancellation': 'native_two_children'},
 'HC': {'binding_violation': 'binding_control',
        'child_scope_escalation': 'child_scope_control',
        'memory_scope_cross_access': 'memory_scope_control',
        'sandbox_denied': 'sandbox_allowed',
        'untrusted_content_injection': 'untrusted_content_control'},
 'HD': {'four_extension_reads_batched': 'four_extension_reads_serial_reference',
        'four_extension_reads_diagnostic_logging': 'four_extension_reads_batched',
        'four_extension_reads_event_consumer_stalled': 'four_extension_reads_batched',
        'four_extension_reads_one_failure': 'four_extension_reads_batched',
        'four_extension_reads_serial_reference': 'public_extension_tool',
        'public_extension_tool': 'native_tool'},
 'HE': {'interrupted_coarse_restore': 'interrupted_snapshot_restore',
        'interrupted_native_resume': 'uninterrupted_state_control',
        'interrupted_snapshot_restore': 'interrupted_native_resume'},
 'HF': {'children_budget_exhausted': 'children_budget_sufficient',
        'effect_roomy_context_fixed': 'effect_roomy_adaptive',
        'effect_roomy_skill_fixed': 'effect_roomy_adaptive',
        'effect_tight_adaptive': 'effect_roomy_adaptive',
        'effect_tight_context_fixed': 'effect_roomy_context_fixed',
        'effect_tight_skill_fixed': 'effect_roomy_skill_fixed',
        'single_budget_exhausted': 'single_budget_sufficient'},
 'HG': {'native_policy_update': 'frozen_policy', 'native_update_reverted': 'native_policy_update'}}


CROSS_CUTTING_CHECKS = {'common_task_resource_accounting', 'usage_reconciliation', 'native_log_durability', 'synthetic_secret_redaction', 'native_event_semantics', 'causal_trace_reconstruction'}


MEASUREMENT_AXES = {'task_quality', 'completion_time', 'token_usage', 'cpu', 'memory', 'disk', 'log_event_semantics'}


def validate_measurement_contract(contract):
    if not MEASUREMENT_AXES <= set(contract.get('required_axes', [])):
        raise ValueError('Missing common task/resource measurement axis')
    for field in ('application', 'record_keys', 'time', 'tokens', 'cpu', 'memory', 'disk',
                  'quality', 'statistics', 'visualizations', 'missing_policy'):
        if not contract.get(field):
            raise ValueError(f'Missing measurement contract: {field}')


def validate_evaluation_contract(contract):
    for field in ('architecture_questions', 'coupling_edges', 'source_binding', 'causal_contrasts',
                  'measurement_unit', 'metrics', 'visualizations', 'artifact_contract', 'coupling_checks'):
        if not contract.get(field):
            raise ValueError(f'Missing harness evaluation contract: {field}')
    metric_ids = set()
    for metric in contract['metrics']:
        for field in ('id', 'unit', 'definition', 'evidence', 'denominator', 'missing_policy'):
            if not metric.get(field):
                raise ValueError(f'Missing metric contract: {field}')
        if metric['id'] in metric_ids:
            raise ValueError('Duplicate metric ID')
        metric_ids.add(metric['id'])
    chart_ids, plotted_metrics = set(), set()
    for chart in contract['visualizations']:
        for field in ('id', 'kind', 'metric_ids', 'group_by', 'interpretation'):
            if not chart.get(field):
                raise ValueError(f'Missing visualization contract: {field}')
        if chart['id'] in chart_ids:
            raise ValueError('Duplicate visualization ID')
        if not set(chart['metric_ids']) <= metric_ids:
            raise ValueError('Visualization references an undefined metric')
        chart_ids.add(chart['id'])
        plotted_metrics.update(chart['metric_ids'])
    if plotted_metrics != metric_ids:
        raise ValueError('Metric lacks a visualization mapping')


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
    validate_measurement_contract(config.get('measurement_contract', {}))
    if not evidence.get('event_contract') or not evidence.get('quantitative_rules'):
        raise ValueError('Missing event mechanism or quantitative reporting contract')
    for field in ('architecture', 'probes', 'metrics', 'evidence_rules', 'visualizations'):
        if not evidence['event_contract'].get(field):
            raise ValueError(f'Missing event contract: {field}')
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
        if study['layer'] == 'harness':
            validate_evaluation_contract(study.get('evaluation_contract', {}))
        conditions = study['conditions']
        if not 2 <= len(conditions) <= {'HC': 10, 'HD': 7, 'HF': 10}.get(study['id'], 5) or len(set(conditions)) != len(conditions):
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
                               'cross_cutting_evidence': evidence,
                               'measurement_contract_id': 'common',
                               'evaluation_contract_id': study['id'] if study['layer'] == 'harness' else None,
                               'plan_only': True})
                for condition, unit_id in zip(conditions, unit_ids):
                    rows.append({'unit_id': unit_id, 'block_id': block_id, 'product': product,
                                 'study': study['id'], 'layer': study['layer'], 'condition': condition,
                                 'repeat': repeat, 'control_unit_id': f'{block_id}/{controls[condition]}',
                                 'plan_only': True})
    return {'revision': config['revision'], 'plan_only': True, 'runtime_ready': False,
            'scope': {'studies': len(config['studies']), 'complete_blocks': len(blocks), 'planned_arms': len(rows),
                      'duration_estimate': 'pending pilot; not a fixed runtime promise'},
            'measurement_contract': config['measurement_contract'],
            'cross_cutting_evidence': evidence, 'execution_policy': policy, 'studies': config['studies'], 'blocks': blocks, 'units': rows}


if __name__ == '__main__':
    print(json.dumps(plan_core(json.loads(Path(__file__).with_name('architecture-core.json').read_text())), indent=2))
