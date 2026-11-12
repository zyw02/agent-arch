#!/usr/bin/env python3
"""Four frozen tasks, isolated attempts, explicit AgentLoop admission."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from observed import require_gate
from run import Campaign, HERE, calibration_prompt, formal_prompt, dump


def selected_protocol(product, task_id):
    protocol = json.loads((HERE / 'protocol-six.json').read_text())
    selection = json.loads((HERE / 'suite-selection.json').read_text())
    entry = next((t for t in selection['tasks'] if t['instance_id'] == task_id), None)
    if entry is None or product not in protocol['products']:
        raise ValueError('Task/product is outside the frozen suite')
    if hashlib.sha256((HERE / entry['task_file']).read_bytes()).hexdigest() != entry['task_sha256']:
        raise ValueError('Frozen task checksum mismatch')
    protocol['products'] = {product: protocol['products'][product]}
    protocol.update(instance_id=task_id, experiment_id='SWE-FOUR-AGENTLOOP-' +
                    os.environ.get('GITHUB_RUN_ID', 'local') + '-' + task_id + '-' + product,
                    purpose='New 72-attempt campaign; never pool with historical PI results')
    controls = protocol['execution']
    controls.update(task_timeout_seconds=1800, smoke_timeout_seconds=540,
                    grading_timeout_seconds=540, provider_request_timeout_seconds=540,
                    relay_settle_seconds=45, memory_bytes=8*1024**3,
                    memory_swap_bytes=8*1024**3, native_timeout_seconds=1800,
                    session_time_budget_seconds=54000, formal_agent_time_budget_seconds=27000,
                    controller_deadline_seconds=43200, formal_step_timeout_minutes=120,
                    aios_runtime='agentloop', live_observation=True,
                    order='24 task/product shards; three sequential fresh attempts in each shard',
                    cross_run_memory=False, isolated_home_and_workspace_each_run=True)
    protocol['comparison_provenance']['expanded_campaign'] = dict(
        task_count=4, products=6, formal_repeats_per_task=3, formal_attempts=72,
        timeouts_multiplier=3, original_memory_bytes=4*1024**3, memory_swap_disabled=True,
        github_single_job_hard_limit_minutes=360,
        original_job_timeout_minutes=270, requested_tripled_job_timeout_minutes=810,
        scheduling='Split into 24 fresh hosted jobs because GitHub cannot accept an 810-minute job',
        aios='Exact delivered 5.7 patch and SDK with native AgentLoop selected; no PI fallback admitted',
        aios_apps='User default App: default/main, SDK-native complex loop, no custom executor or extra task prompt',
        provider_cache='Fresh local memory each attempt; provider-side cache cannot be reset',
        controls='2 CPU, 8 GiB, same common image and frozen dependency locks for all products',
        difficulty='Same human-verified 15 min - 1 hour tier, not a claim of identical difficulty')
    if product == 'openclaw57_patched':
        protocol['products'][product]['execution'] = 'Native local agent; AgentLoop runtime enabled and verified from SDK loop-entry log'
    return protocol


def shard_summary(root, task_id, product, require_complete=False):
    rows = []
    for stage in ('calibration', 'block-1', 'block-2', 'block-3'):
        path = root / 'segments' / stage / 'summary.json'
        if path.exists():
            rows.extend(json.loads(path.read_text())['results'])
    formal = [r for r in rows if not r['smoke']]
    expected = {f'block-{i}-{product}' for i in range(1, 4)}
    complete = {r['run_id'] for r in formal} == expected
    summary = dict(task_id=task_id, product=product, formal_completed=len(formal),
                   formal_expected=3, complete=complete,
                   resolved=sum(r['resolved'] for r in formal),
                   runs=[dict(run_id=r['run_id'], smoke=r['smoke'], resolved=r['resolved'],
                              termination=r['termination'], wall_seconds=r['wall_seconds'],
                              native_execution_ok=r['native_execution_ok'],
                              runtime_validation=r.get('runtime_validation')) for r in rows])
    dump(root / 'shard-summary.json', summary)
    if require_complete and not complete:
        raise ValueError('Shard incomplete; absent attempts are not counted as measured zero')
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--task-id', required=True)
    p.add_argument('--product', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--image', default='six-harness-expanded')
    p.add_argument('--stage', choices=['controls', 'calibration', 'block-1', 'block-2', 'block-3', 'summarize'], required=True)
    args = p.parse_args()
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    protocol = selected_protocol(args.product, args.task_id)
    path = root / 'suite-protocol.json'; dump(path, protocol)
    if args.stage == 'summarize':
        print(json.dumps(shard_summary(root, args.task_id, args.product, require_complete=True)), flush=True)
        return
    require_gate(root, args.product, args.stage, args.image, path)
    task = HERE / 'tasks' / (args.task_id + '.json')
    source = args.sources / args.task_id
    if not (source / 'src/_pytest').is_dir() or (source / '.git').exists():
        raise ValueError('Missing gold-free task source or exposed Git history')
    segment = argparse.Namespace(output=root/'segments'/args.stage, image=args.image,
        protocol=path, task=task, task_source=source, mode='formal', deadline_seconds=43200)
    campaign = Campaign(segment)
    started = time.monotonic()
    print(json.dumps(dict(phase='stage_started', task=args.task_id, product=args.product,
                          stage=args.stage, utc=datetime.now(timezone.utc).isoformat())), flush=True)
    try:
        campaign.prepare()
        if args.stage == 'controls':
            if not campaign.controls():
                raise ValueError('Hidden-test controls failed; no paid task admitted')
        elif args.stage == 'calibration':
            result = campaign.run_product(args.product, 'smoke-' + args.product, calibration_prompt(), smoke=True)
            if not result['calibration_passed']:
                raise ValueError('Native tool, usage or runtime calibration failed; formal calls blocked')
        else:
            campaign.run_product(args.product, args.stage + '-' + args.product, formal_prompt(campaign.task))
    except Exception as exc:
        dump(campaign.out/'campaign-error.json', dict(error=type(exc).__name__, message=str(exc)))
        raise
    finally:
        campaign.cleanup()
        summary = shard_summary(root, args.task_id, args.product)
        progress = dict(stage=args.stage, elapsed_seconds=time.monotonic()-started, **summary)
        dump(root/(args.stage+'-progress.json'), progress)
        print(json.dumps(progress), flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write('\n### '+args.task_id+' / '+args.product+' / '+args.stage+'\n\n```json\n'+
                             json.dumps(progress, indent=2)+'\n```\n')


if __name__ == '__main__':
    main()
