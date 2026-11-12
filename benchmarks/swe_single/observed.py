#!/usr/bin/env python3
"""Expose controls, calibration and each repeat as separate Actions steps.

The solver, relay, resources, limits and hidden grader are the normal Campaign.
Only the scheduling and evidence upload boundaries differ from the six-way run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from run import Campaign, HERE, calibration_prompt, formal_prompt, dump


def require_gate(root, product, stage, image):
    if stage == 'controls':
        return
    controls = root / 'segments/controls'
    if not json.loads((controls / 'controls/acceptance.json').read_text())['passed']:
        raise ValueError('Hidden-test controls did not pass; no model calls admitted')
    paths = [controls]
    if stage.startswith('block-'):
        calibration = root / 'segments/calibration'
        results = json.loads((calibration / 'summary.json').read_text())['results']
        if len(results) != 1 or results[0]['product'] != product or not results[0]['calibration_passed']:
            raise ValueError('Native tool/usage calibration did not pass; no formal run admitted')
        paths.append(calibration)
    current_id = subprocess.check_output(['docker', 'image', 'inspect', image,
                                          '--format', '{{.Id}}'], text=True).strip()
    for path in paths:
        if json.loads((path / 'environment.json').read_text())['image_id'] != current_id:
            raise ValueError('Image differs from the accepted controls/calibration')


class ObservedCampaign(Campaign):
    def run_stage(self, product, stage):
        self.prepare()
        dump(self.out / 'observation.json', dict(stage=stage, product=product,
             source_protocol_sha256=hashlib.sha256((HERE / 'protocol-six.json').read_bytes()).hexdigest(),
             scheduling='Independent observed batch; not a rotated six-product comparison block',
             prompt_sha256=hashlib.sha256(formal_prompt(self.task).encode()).hexdigest()))
        if stage == 'controls':
            if not self.controls():
                raise RuntimeError('Task controls failed; no model calls admitted')
        elif stage == 'calibration':
            result = self.run_product(product, 'smoke-' + product, calibration_prompt(), smoke=True)
            if not result['calibration_passed']:
                raise RuntimeError('Native tool/usage calibration failed; no formal runs admitted')
        else:
            self.run_product(product, stage + '-' + product, formal_prompt(self.task))


def combine(root):
    def retain_once(source, target):
        if not Path(target).exists():
            os.link(source, target)
        return target

    segments = [root / 'segments' / s for s in ('controls', 'calibration', 'block-1', 'block-2', 'block-3')]
    available = [p for p in segments if all((p / name).is_file()
                 for name in ('summary.json', 'environment.json', 'observation.json'))]
    campaign = root / 'campaign'
    campaign.mkdir(exist_ok=True)
    summaries = [json.loads((p / 'summary.json').read_text()) for p in available]
    for p in available:
        for name in ('environment.json', 'protocol.json', 'controller-task.json',
                     'test-dependencies.txt', 'package-lock.json', 'installation-storage.json'):
            if (p / name).is_file() and not (campaign / name).exists():
                shutil.copyfile(p / name, campaign / name)
        for name in ('runs', 'controls'):
            if (p / name).exists():
                shutil.copytree(p / name, campaign / name, dirs_exist_ok=True, copy_function=retain_once)
    if summaries:
        summary = dict(summaries[0])
        summary.update(results=[r for s in summaries for r in s['results']],
                       latest_accounting={k: v for s in summaries for k, v in s['latest_accounting'].items()},
                       elapsed_seconds=sum(s['elapsed_seconds'] for s in summaries))
        dump(campaign / 'summary.json', summary)
        dump(campaign / 'observed-batch.json', dict(
             scheduling='Single-product diagnostic batch alongside the original six-product campaign',
             segments=[dict(stage=p.name, environment=json.loads((p / 'environment.json').read_text()),
                            observation=json.loads((p / 'observation.json').read_text())) for p in available],
             original_campaign_run_id=43144468826,
             not_paired_with_original_campaign=True))
        for script in ('verify_usage.py', 'reconcile.py', 'report.py'):
            subprocess.run(['python3', str(HERE / script), str(campaign)], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default='five-harness-swe')
    parser.add_argument('--product', default='openclaw57_patched')
    parser.add_argument('--stage', choices=['controls', 'calibration', 'block-1', 'block-2', 'block-3'], required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    protocol = json.loads((HERE / 'protocol-six.json').read_text())
    if args.product not in protocol['products']:
        raise ValueError('Unknown product')
    root.mkdir(parents=True, exist_ok=True)
    protocol['products'] = {args.product: protocol['products'][args.product]}
    protocol['experiment_id'] = 'SWE-OBSERVED-' + os.environ.get('GITHUB_RUN_ID', 'local') + '-' + args.product
    protocol['purpose'] = 'Observed single-product batch; same task and execution controls; separate from rotated comparison'
    protocol_path = root / 'observed-protocol.json'
    dump(protocol_path, protocol)
    require_gate(root, args.product, args.stage, args.image)
    segment_args = argparse.Namespace(output=root / 'segments' / args.stage, image=args.image,
                                     protocol=protocol_path, mode='formal', deadline_seconds=14400)
    segment_args.output.parent.mkdir(parents=True, exist_ok=True)
    campaign = ObservedCampaign(segment_args)
    started = time.monotonic()
    try:
        campaign.run_stage(args.product, args.stage)
    finally:
        campaign.cleanup()
        progress = dict(product=args.product, stage=args.stage,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        elapsed_seconds=time.monotonic() - started,
                        results=[dict(run_id=r['run_id'], resolved=r['resolved'],
                                      native_execution_ok=r['native_execution_ok'],
                                      termination=r['termination'], wall_seconds=r['wall_seconds'],
                                      calibration_passed=r.get('calibration_passed')) for r in campaign.results])
        dump(root / (args.stage + '-progress.json'), progress)
        print(json.dumps(progress), flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write('\n```json\n' + json.dumps(progress, indent=2) + '\n```\n')
        combine(root)


if __name__ == '__main__':
    main()
