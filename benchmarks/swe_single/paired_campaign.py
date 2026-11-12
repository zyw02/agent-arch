#!/usr/bin/env python3
"""Two tasks, six products, three repeats, sequential on one allocated host.

No hidden retry or dropped attempt. Each solver launch, including calibration,
has an immediately preceding, separate no-task native idle measurement.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from accounting import summarize_requests
from run import Campaign, HERE, calibration_prompt, dump, execute, formal_prompt
from suite import selected_protocol
from suite_idle import repeat as idle_repeat
from validated_controls import check_response_integrity, fixed_runner_admission, require_protocol_preflight

TASKS = ('pytest-dev__pytest-7236', 'pytest-dev__pytest-7324')
PRODUCTS = ('openclaw57_patched', 'codex', 'dsh', 'claude', 'hermes', 'openclaw')


def schedule():
    # Across six blocks every product occupies each order position once.
    return [dict(index=i, task_id=TASKS[i % 2], repeat=i//2+1,
                 products=list(PRODUCTS[i:] + PRODUCTS[:i])) for i in range(6)]


def event(root, phase, **details):
    row = dict(utc=datetime.now(timezone.utc).isoformat(), phase=phase, **details)
    with (root/'progress.jsonl').open('a') as stream:
        stream.write(json.dumps(row, ensure_ascii=False)+'\n')
    dump(root/'current-status.json', row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def admit_time(deadline, smoke=False, now=None):
    # Full native timeout + grading + idle readiness/settling/sampling + pending
    # billed provider settlement + cleanup, then retain 5 minutes for upload.
    needed = (540 if smoke else 1800) + 540 + 660 + 545 + 120 + 300
    remaining = deadline - (time.time() if now is None else now)
    if remaining < needed:
        raise RuntimeError(f'Insufficient job time for an unshortened attempt: {remaining:.0f}s < {needed}s')
    return dict(remaining_seconds=remaining, reserved_seconds=needed)


def protocol_for(task_id):
    protocol = selected_protocol('openclaw57_patched', task_id, validated=True)
    base = json.loads((HERE/'protocol-six.json').read_text())['products']
    protocol['products'] = {p:base[p] for p in PRODUCTS}
    protocol['experiment_id'] = 'TWO-TASK-SAME-HOST-'+os.environ.get('GITHUB_RUN_ID','local')+'-'+task_id
    protocol['purpose'] = 'Two tasks, six products, three repeats, all on one allocated hosted runner'
    protocol['comparison_provenance']['expanded_campaign'].update(task_count=2, formal_attempts=36,
        scheduling='One hosted job; all products sequential, identical allocated vCPUs and frozen runtime')
    protocol['execution'].update(single_host_campaign=True, cpuset_cpus=os.environ['BENCH_CPUSET_CPUS'],
        cpus=int(os.environ['BENCH_ALLOCATED_CPUS']),
        order='Six sequential rotated blocks; fixed before execution; see plan.json',
        controller_deadline_seconds=21600)
    protocol['comparison_provenance']['single_host'] = dict(
        tasks=list(TASKS), products=list(PRODUCTS), repeats=3, formal_attempts=36,
        all_measured_in_one_job=True, concurrent_solver_containers=1,
        initial_idle='Before every calibration/formal launch: fresh native UI/server, no task, '
                     '60s settle + 60s sampling, same task base source and CPU/memory limits',
        idle_scope='Separate idle process, then disposed; formal headless process starts fresh. '
                   'Idle native modes and product startup flags retained from prior suite.',
        cpu_policy='All actually allocated vCPUs, identical quota and affinity for every product',
        old_results_comparable=False)
    return protocol


def verify_host(root):
    recorded = json.loads((root/'host.json').read_text())
    current = fixed_runner_admission()
    if (Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=recorded['boot_id'] or
            current != recorded['admission'] or
            os.environ['BENCH_CPUSET_CPUS'] != recorded['cpuset_cpus'] or
            int(os.environ['BENCH_ALLOCATED_CPUS']) != recorded['allocated_cpus']):
        raise ValueError('Host identity or CPU binding changed; refusing comparison')
    if execute(['docker','image','inspect','six-harness-expanded','--format','{{.Id}}']).stdout.strip()!=recorded['image_id']:
        raise ValueError('Frozen runtime image changed')
    require_protocol_preflight(os.environ['BENCH_PROTOCOL_PREFLIGHT_RECEIPT'])
    return recorded


def campaign_for(args, task_id, name):
    protocol_path = args.output/'protocols'/f'{task_id}.json'
    if not protocol_path.exists():
        dump(protocol_path, protocol_for(task_id))
    source = args.sources/task_id
    if not (source/'src/_pytest').is_dir() or (source/'.git').exists():
        raise ValueError('Frozen gold-free source missing or Git history exposed')
    return Campaign(argparse.Namespace(protocol=protocol_path, task=HERE/'tasks'/f'{task_id}.json',
        output=args.output/'segments'/name, image='six-harness-expanded', task_source=source,
        mode='formal', deadline_seconds=21600))


def require_controls(args):
    verify_host(args.output)
    for task in TASKS:
        root = args.output/'segments'/('controls-'+task)
        if not json.loads((root/'controls/acceptance.json').read_text())['passed']:
            raise ValueError('Hidden-test controls did not pass')
        env = json.loads((root/'environment.json').read_text())
        if env['protocol_sha256'] != hashlib.sha256((args.output/'protocols'/f'{task}.json').read_bytes()).hexdigest():
            raise ValueError('Protocol changed after hidden-test controls')


def measure_before(args, product, task, identity):
    root = args.output/'idle'/identity
    root.mkdir(parents=True)
    event(args.output, 'idle_started', product=product, task_id=task, identity=identity)
    # Idle native containers receive disposable credentials and network=none.
    result = idle_repeat(argparse.Namespace(product=product, output=root,
        image='six-harness-expanded', workspace_source=args.sources/task,
        cpuset_cpus=os.environ['BENCH_CPUSET_CPUS'], cpus=int(os.environ['BENCH_ALLOCATED_CPUS'])), 1)
    result['paired_attempt'] = identity
    result['task_id'] = task
    dump(root/'paired-result.json', result)
    event(args.output, 'idle_completed', product=product, task_id=task, identity=identity,
          valid=result['valid'], rss_mib=result.get('median_rss_mib'), pss_mib=result.get('median_pss_mib'))
    if not result['valid']:
        raise ValueError('Required idle RSS/PSS invalid; solver not admitted')
    return root/'paired-result.json'


def settle(campaign):
    deadline = time.monotonic()+545
    while any(not r['settled'] for relay in campaign.relays for r in relay.records):
        if time.monotonic() >= deadline:
            raise TimeoutError('Provider settlement incomplete; retain unknown usage explicitly')
        time.sleep(.5)


def solve(args, campaign, product, task, repeat, smoke=False):
    identity = ('calibration' if smoke else f'{task}-repeat-{repeat}')+'-'+product
    verify_host(args.output)
    budget = admit_time(float(os.environ['BENCH_JOB_DEADLINE_UTC']), smoke=smoke)
    event(args.output, 'attempt_admitted', identity=identity, **budget)
    idle = measure_before(args, product, task, identity)
    # The idle process/home has been removed; run_product creates a new home,
    # task checkout, tmp and session. No idle memory or prior task is reused.
    run_id = ('smoke-' if smoke else f'block-{repeat}-')+product
    event(args.output, 'solver_started', product=product, task_id=task, identity=identity)
    result = campaign.run_product(product, run_id, calibration_prompt() if smoke else formal_prompt(campaign.task), smoke=smoke)
    settle(campaign)
    relay = next(r for r in campaign.relays if r.run_id == run_id)
    result['provider'] = summarize_requests(relay.records)
    result['response_integrity'] = check_response_integrity(relay.records)
    result['preceding_idle_result'] = str(idle.relative_to(args.output))
    result['comparison_ready'] = bool(result['response_integrity']['clean'] and result['provider']['usage_complete'])
    result['comparison_warning'] = None if result['comparison_ready'] else 'Retain attempt; provider/protocol anomaly requires review before product ranking'
    dump(campaign.out/'runs'/run_id/'result.json', result)
    campaign.write_summary()
    event(args.output, 'solver_completed', product=product, task_id=task, identity=identity,
        resolved=result['resolved'], wall_seconds=result['wall_seconds'],
        response_integrity=result['response_integrity'], usage_complete=result['provider']['usage_complete'])
    return result


def controls(args):
    verify_host(args.output)
    for task in TASKS:
        campaign = campaign_for(args, task, 'controls-'+task)
        try:
            campaign.prepare()
            if not campaign.controls():
                raise ValueError('Base-red/reference-green controls failed')
            event(args.output, 'controls_passed', task_id=task)
        finally:
            campaign.cleanup()


def calibrate(args):
    require_controls(args)
    campaign = campaign_for(args, TASKS[0], 'calibration')
    try:
        campaign.prepare()
        for product in PRODUCTS:
            result = solve(args, campaign, product, TASKS[0], 0, smoke=True)
            if not result['calibration_passed'] or not result['comparison_ready']:
                raise ValueError(f'Native calibration failed for {product}; formal calls blocked')
        dump(args.output/'calibration-acceptance.json', dict(passed=True, products=list(PRODUCTS)))
    finally:
        campaign.cleanup()


def round_stage(args):
    require_controls(args)
    if not json.loads((args.output/'calibration-acceptance.json').read_text())['passed']:
        raise ValueError('All six native calibrations must pass')
    block = schedule()[args.round]
    if args.round:
        previous = args.output/'blocks'/f'round-{args.round-1}.json'
        if not previous.exists():
            raise ValueError('Previous block incomplete; fixed planned order must be retained')
    product = args.product
    if product not in block['products']:
        raise ValueError('Product is outside this block')
    position = block['products'].index(product)
    if position:
        previous_product = block['products'][position-1]
        previous = result_path(args.output, block, previous_product)
        if not previous.exists() or not json.loads(previous.read_text()).get('preceding_idle_result'):
            raise ValueError('Previous product incomplete; fixed planned order must be retained')
    campaign = campaign_for(args, block['task_id'], f'round-{args.round}-{product}')
    try:
        campaign.prepare()
        solve(args, campaign, product, block['task_id'], block['repeat'])
        if all(result_path(args.output, block, p).exists() for p in block['products']):
            dump(args.output/'blocks'/f'round-{args.round}.json', block)
    finally:
        campaign.cleanup()


def result_path(root, block, product):
    return root/'segments'/f"round-{block['index']}-{product}"/'runs'/f"block-{block['repeat']}-{product}"/'result.json'


def finalize(args):
    rows = []
    for block in schedule():
        for product in block['products']:
            identity = f"{block['task_id']}-repeat-{block['repeat']}-{product}"
            path = result_path(args.output, block, product)
            if not path.exists():
                rows.append(dict(identity=identity, measured=False, status='not_completed'))
                continue
            result = json.loads(path.read_text())
            idle_path = args.output/result.get('preceding_idle_result', f'idle/{identity}/paired-result.json')
            idle = json.loads(idle_path.read_text()) if idle_path.exists() else dict(valid=False)
            rows.append(dict(identity=identity, task_id=block['task_id'], product=product,
                repeat=block['repeat'], measured=True, resolved=result['resolved'],
                comparison_ready=result.get('comparison_ready', False), response_integrity=result.get('response_integrity', dict(clean=False)),
                wall_seconds=result['wall_seconds'], provider=result['provider'],
                idle_rss_mib=idle.get('median_rss_mib'), idle_pss_mib=idle.get('median_pss_mib'),
                idle_valid=idle['valid'], result_path=str(path.relative_to(args.output))))
    summary = dict(expected=36, completed=sum(r['measured'] for r in rows),
        complete=all(r['measured'] for r in rows),
        comparison_ready=all(r.get('comparison_ready', False) and r.get('idle_valid', False) for r in rows),
        host=json.loads((args.output/'host.json').read_text()), attempts=rows,
        hidden_retries=0, missing_attempts_are_not_zero=True,
        scope='New two-task same-host campaign; never pool with historical heterogeneous-host runs')
    dump(args.output/'two-task-summary.json', summary)
    event(args.output, 'campaign_finalized', completed=summary['completed'], expected=36,
          comparison_ready=summary['comparison_ready'])
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
            stream.write(f"\nCompleted {summary['completed']}/36; comparison ready: {summary['comparison_ready']}\n\n")
            stream.write('| Task/repeat/product | Result | Idle RSS MiB | Idle PSS MiB | Seconds |\n|---|---|---:|---:|---:|\n')
            for r in rows:
                stream.write('| '+r['identity']+' | '+('passed' if r.get('resolved') else 'failed' if r['measured'] else 'not completed')+
                    ' | '+str(r.get('idle_rss_mib',''))+' | '+str(r.get('idle_pss_mib',''))+' | '+str(r.get('wall_seconds',''))+' |\n')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--stage', choices=['init','controls','calibration','round','finalize'], required=True)
    parser.add_argument('--round', type=int, choices=range(6))
    parser.add_argument('--product', choices=PRODUCTS)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'protocols').mkdir(exist_ok=True)
    (args.output/'blocks').mkdir(exist_ok=True)
    if args.stage == 'init':
        admission = fixed_runner_admission()
        require_protocol_preflight(os.environ['BENCH_PROTOCOL_PREFLIGHT_RECEIPT'])
        dump(args.output/'host.json', dict(admission=admission,
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            cpuset_cpus=os.environ['BENCH_CPUSET_CPUS'],
            allocated_cpus=int(os.environ['BENCH_ALLOCATED_CPUS']),
            image_id=execute(['docker','image','inspect','six-harness-expanded','--format','{{.Id}}']).stdout.strip(),
            controller_sha=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'),
            job_deadline_utc=float(os.environ['BENCH_JOB_DEADLINE_UTC'])))
        dump(args.output/'plan.json', dict(tasks=list(TASKS), products=list(PRODUCTS), blocks=schedule(),
            formal_attempts=36, pre_solver_idle_samples=42, idle_window_seconds=120,
            task_timeout_seconds=1800, provider_timeout_seconds=540, grading_timeout_seconds=540,
            legacy_relay_request_limit=None, formal_concurrency=1, no_hidden_retries=True))
        event(args.output, 'campaign_initialized')
    else:
        try:
            if args.stage == 'controls': controls(args)
            elif args.stage == 'calibration': calibrate(args)
            elif args.stage == 'round': round_stage(args)
            else:
                summary = finalize(args)
                if not summary['complete']:
                    raise ValueError('Incomplete campaign; partial results retained without final ranking')
        except Exception as exc:
            event(args.output, 'stage_error', stage=args.stage, round=args.round,
                error_type=type(exc).__name__, message=str(exc).replace(os.environ.get('DEEPSEEK_API_KEY','__NO_KEY__'), '[REDACTED]')[:500])
            raise


if __name__ == '__main__':
    main()
