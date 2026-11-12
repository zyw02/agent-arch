"""Opt-in corrected controls; historical protocols and measurements stay frozen."""
import hashlib
import json
import os
from pathlib import Path


def control_source_hashes():
    root=Path(__file__).resolve().parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
            for name in ('relay.py','validated_controls.py','agent_entry.py')}


def require_protocol_preflight(path):
    if not path:
        raise ValueError('Validated campaign requires BENCH_PROTOCOL_PREFLIGHT_RECEIPT from the live six-probe check')
    receipt=json.loads(Path(path).read_text())
    expected={(api,mode) for api in ('chat','messages','responses')
              for mode in ('main-high','auxiliary-disabled')}
    actual={(p['api'],p['mode']) for p in receipt.get('probes',[])}
    if (not receipt.get('complete') or actual!=expected or
            not receipt.get('response_integrity',{}).get('clean') or
            not receipt.get('accounting',{}).get('usage_complete') or
            receipt.get('control_source_hashes')!=control_source_hashes()):
        raise ValueError('Live protocol receipt is incomplete or belongs to different controller code; no model calls admitted')
    return dict(passed=True,receipt=str(Path(path).resolve()),control_source_hashes=control_source_hashes())


def apply_validated_controls(protocol):
    protocol['experiment_id'] += '-VALIDATED-V2'
    protocol['provider'].update(request_policy='native-aux-v2', requested_max_output_tokens=65536,
        auxiliary_reasoning='Preserve explicit native disabled/none decisions and native smaller budgets')
    protocol['execution'].update(maximum_provider_attempts_per_run=None,
        native_iteration_safety_limit=4096, require_fixed_runner=True)
    protocol['comparison_provenance']['validated_controls'] = dict(
        historical_results_comparable=False,
        description='New campaign only: native auxiliary intent, 64K main output, timeout-only relay, fixed host admission',
        output_budget='Requested common main budget, not a proven server-side cap on Messages compatibility paths')
    return protocol


def fixed_runner_admission(env=None, cpuinfo=None):
    env = os.environ if env is None else env
    expected_cpu = env.get('BENCH_EXPECTED_CPU_MODEL', '').strip()
    expected_runner = env.get('BENCH_EXPECTED_RUNNER_NAME', '').strip()
    if not expected_cpu or not expected_runner:
        raise ValueError('Validated comparison requires explicit expected CPU model and unique runner name')
    text = Path('/proc/cpuinfo').read_text() if cpuinfo is None else cpuinfo
    models = sorted({line.split(':', 1)[1].strip() for line in text.splitlines()
                     if line.startswith('model name') and ':' in line})
    actual_runner = env.get('RUNNER_NAME', '').strip()
    if models != [expected_cpu] or actual_runner != expected_runner:
        raise ValueError('Fixed-runner admission failed; no model calls admitted')
    return dict(passed=True, cpu_model=expected_cpu, runner_name=actual_runner,
                expected_cpu_model=expected_cpu, expected_runner_name=expected_runner)


def check_response_integrity(records):
    issues = []
    for r in records:
        if not r.get('forwarded'):
            if r.get('blocked_reason') == 'declared_request_limit':
                issues.append(dict(request_index=r['request_index'], kind='test_request_budget'))
            continue
        if r.get('finish_reason') in ('length', 'max_tokens', 'max_output_tokens'):
            issues.append(dict(request_index=r['request_index'], kind='output_truncated'))
        if not r.get('terminal'):
            issues.append(dict(request_index=r['request_index'], kind='missing_stream_terminal'))
        if not r.get('final_usage_observed'):
            issues.append(dict(request_index=r['request_index'], kind='missing_final_usage'))
    return dict(clean=not issues, issues=issues,
                interpretation='Diagnostics, not automatic blame or discarded attempts; retain every result')
