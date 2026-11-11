#!/usr/bin/env python3
"""Run controls, native tool smoke, then complete sequential comparison blocks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tarfile
import time
import uuid

from accounting import summarize_requests
from grading import compare_source, grading_workspace, parse_junit, score
from native import inspect_native
from relay import Relay
from resources import Collector, disk_tree

HERE = Path(__file__).resolve().parent


def execute(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def apply_patch(root, patch, output):
    result = subprocess.run(['git', 'apply', '-'], input=patch,
                            cwd=root, text=True, capture_output=True)
    Path(output).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('Frozen controller patch did not apply')


def chown_tree(root):
    for parent, directories, files in os.walk(root, followlinks=False):
        os.chown(parent, 1000, 1000)
        for name in directories + files:
            os.chown(Path(parent) / name, 1000, 1000, follow_symlinks=False)


class Campaign:
    def __init__(self, args):
        self.args = args
        self.protocol = json.loads((HERE / 'protocol.json').read_text())
        self.task = json.loads((HERE / 'task.json').read_text())
        self.out = args.output.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.work = self.out.parent / (self.out.name + '-working-' + uuid.uuid4().hex[:8])
        self.work.mkdir()
        self.initial = self.work / 'initial'
        self.initial.mkdir()
        self.key = os.environ.get('DEEPSEEK_API_KEY', '')
        if not self.key:
            raise ValueError('DEEPSEEK_API_KEY is absent; no paid run launched')
        self.network = 'swe-bench-' + uuid.uuid4().hex[:10]
        self.started = time.monotonic()
        self.results = []
        self.relays = []
        self.containers = []

    def prepare(self):
        # This container never starts. It contains only base source and packages.
        name = execute(['docker', 'create', self.args.image]).stdout.strip()
        execute(['docker', 'cp', name + ':/testbed/.', str(self.initial)])
        execute(['docker', 'cp', name + ':/opt/test-dependencies.txt', str(self.out / 'test-dependencies.txt')])
        execute(['docker', 'cp', name + ':/opt/products/package-lock.json', str(self.out / 'package-lock.json')])
        execute(['docker', 'rm', name])
        execute(['docker', 'network', 'create', '--internal', self.network])
        info = json.loads(execute(['docker', 'network', 'inspect', self.network]).stdout)[0]
        self.gateway = info['IPAM']['Config'][0]['Gateway']
        image = json.loads(execute(['docker', 'image', 'inspect', self.args.image]).stdout)[0]
        dump(self.out / 'environment.json', dict(
            image_id=image['Id'], image_size=image['Size'], image_repo_digests=image.get('RepoDigests'),
            docker_version=execute(['docker', 'version', '--format', '{{.Server.Version}}']).stdout.strip(),
            controller_sha=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'),
            started_utc=datetime.now(timezone.utc).isoformat(), network=info,
            protocol_sha256=hashlib.sha256((HERE / 'protocol.json').read_bytes()).hexdigest(),
            task_sha256=hashlib.sha256((HERE / 'task.json').read_bytes()).hexdigest(),
            initial_storage=disk_tree(self.initial)))
        shutil.copyfile(HERE / 'protocol.json', self.out / 'protocol.json')
        shutil.copyfile(HERE / 'task.json', self.out / 'controller-task.json')
        inventory_code = (HERE / 'resources.py').read_text() + '''
paths = {
    'npm_shared_install': '/opt/products',
    'dsh_package': '/opt/products/node_modules/@deepseek-ai/dsh',
    'openclaw_package': '/opt/products/node_modules/openclaw',
    'codex_package': '/opt/products/node_modules/@openai/codex',
    'claude_package': '/opt/products/node_modules/@anthropic-ai/claude-code',
    'hermes_source': '/opt/hermes',
    'hermes_environment': '/opt/hermes-venv',
    'task_environment': '/opt/testenv',
    'shared_python': '/opt/python',
}
print(json.dumps({'paths': {k: disk_tree(v) for k, v in paths.items()},
    'semantics': 'Package directory diagnostics; shared or optional dependencies are not exclusive standalone product footprints'}))
'''
        inventory = execute(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                             '--entrypoint', 'python3', self.args.image, '-c', inventory_code])
        dump(self.out / 'installation-storage.json', json.loads(inventory.stdout))

    def grade(self, workspace, output):
        output.mkdir(parents=True, exist_ok=True)
        apply_patch(workspace, self.task['test_patch'], output / 'hidden-patch-application.log')
        chown_tree(workspace)
        # Only test paths touched by the frozen hidden patch; hidden F2P/P2P
        # membership comes from the immutable dataset, not agent-created tests.
        test_paths = sorted({line[6:] for line in self.task['test_patch'].splitlines() if line.startswith('+++ b/')})
        command = ['docker', 'run', '--rm', '--network', 'none', '--cpus', '2', '--memory', '4g',
                   '--pids-limit', '256', '--user', '1000:1000',
                   '--mount', f'type=bind,src={workspace},dst=/testbed',
                   '--entrypoint', '/opt/testenv/bin/python', self.args.image,
                   '-m', 'pytest', '-rA', '-vv', '--tb=short', '-o', 'junit_family=xunit1',
                   '--junitxml=/testbed/benchmark-junit.xml', *test_paths]
        started = time.monotonic()
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=180)
            (output / 'stdout.log').write_text(p.stdout)
            (output / 'stderr.log').write_text(p.stderr)
            junit = workspace / 'benchmark-junit.xml'
            shutil.copyfile(junit, output / 'junit.xml')
            statuses = parse_junit(junit)
            result = score(self.task, statuses)
            result.update(exit_code=p.returncode, wall_seconds=time.monotonic() - started,
                          full_test_file_passed=p.returncode == 0)
        except Exception as exc:
            result = dict(grading_error=type(exc).__name__ + ': ' + str(exc),
                          official_subset_resolved=False)
        dump(output / 'grade.json', result)
        return result

    def controls(self):
        controls = self.out / 'controls'
        base = self.work / 'control-base'
        shutil.copytree(self.initial, base)
        result = self.grade(base, controls / 'base')
        f2p = result.get('FAIL_TO_PASS', {})
        base_ok = f2p.get('passed') == 0 and f2p.get('missing') == 0 and all(
            row['status'] == 'FAILED' for row in f2p.get('outcomes', []))
        if not base_ok:
            dump(controls / 'acceptance.json', dict(passed=False, reason='base_did_not_fail_every_hidden_fix_case'))
            return False
        gold_results = []
        for index in range(2):
            root = self.work / f'control-gold-{index}'
            shutil.copytree(self.initial, root)
            target = controls / f'gold-{index}'
            target.mkdir(parents=True)
            apply_patch(root, self.task['patch'], target / 'gold-patch-application.log')
            gold_results.append(self.grade(root, target))
        accepted = all(r.get('official_subset_resolved') and r.get('full_test_file_passed') for r in gold_results)
        dump(controls / 'acceptance.json', dict(passed=accepted, base_hidden_red=True,
                                               gold_repetitions=2, gold_all_green=accepted))
        return accepted

    def run_product(self, product, run_id, prompt, smoke=False):
        output = self.out / 'runs' / run_id
        output.mkdir(parents=True)
        root = self.work / run_id
        workspace, home, scratch = root / 'workspace', root / 'home', root / 'tmp'
        shutil.copytree(self.initial, workspace)
        home.mkdir()
        scratch.mkdir()
        scratch.chmod(0o1777)
        if smoke:
            receipt = uuid.uuid4().hex + '\n'
            (workspace / 'BENCH_RECEIPT.txt').write_text(receipt)
            expected_digest = hashlib.sha256(receipt.encode()).hexdigest()
        prompt_path = home / 'prompt.txt'
        prompt_path.write_text(prompt)
        chown_tree(root)
        collector = Collector(output, workspace, home, scratch, self.protocol['execution']['writable_paths_limit_bytes'])
        relay = Relay(self.key, self.gateway, output / 'provider', run_id,
                      self.protocol['execution']['maximum_provider_attempts_per_run'])
        self.relays.append(relay)
        container = 'swe-' + run_id
        command = ['docker', 'create', '--name', container, '--network', self.network,
                   '--cpus', '2', '--memory', '4g', '--pids-limit', '512', '--read-only',
                   '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges',
                   '--env', 'BENCH_RUN_ID=' + run_id,
                   '--mount', f'type=bind,src={workspace},dst=/testbed',
                   '--mount', f'type=bind,src={home},dst=/home/bench',
                   '--mount', f'type=bind,src={scratch},dst=/tmp',
                   self.args.image, product, relay.base, '/home/bench/prompt.txt']
        execute(command)
        self.containers.append(container)
        started_ns = time.monotonic_ns()
        execute(['docker', 'start', container])
        pid = json.loads(execute(['docker', 'inspect', container]).stdout)[0]['State']['Pid']
        collector.start(pid)
        timeout = self.protocol['execution']['smoke_timeout_seconds' if smoke else 'task_timeout_seconds']
        termination = None
        report_path = home / 'agent-exit.json'
        while not report_path.exists():
            elapsed = (time.monotonic_ns() - started_ns) / 1e9
            if elapsed > timeout:
                termination = 'timeout'
                break
            if collector.storage_limit_exceeded:
                termination = 'storage_limit'
                break
            # Early native/container crashes must not burn the whole timeout.
            if elapsed > 2 and not Path(f'/proc/{pid}').exists():
                termination = 'container_exited_before_agent_receipt'
                break
            time.sleep(0.2)
        observed_ns = time.monotonic_ns()
        exit_report = json.loads(report_path.read_text()) if report_path.exists() else None
        subprocess.run(['docker', 'pause', container], capture_output=True)
        measurements = collector.finish()
        inspection = json.loads(execute(['docker', 'inspect', container]).stdout)[0]
        dump(output / 'container.json', inspection)
        logs = subprocess.run(['docker', 'logs', '--timestamps', container], capture_output=True, text=True)
        (output / 'stdout.log').write_text(logs.stdout)
        (output / 'stderr.log').write_text(logs.stderr)
        # These reads are after pause: DB files and their WAL/SHM are a single
        # frozen snapshot. No checkpoint operation changes product state.
        native = inspect_native(product, home, output / 'stdout.log', output)
        with tarfile.open(output / 'native-state.tar.gz', 'w:gz', dereference=False) as tf:
            for path in sorted(home.rglob('*')):
                if path.is_file() and not path.is_symlink():
                    tf.add(path, arcname=path.relative_to(home), recursive=False)
        subprocess.run(['docker', 'unpause', container], capture_output=True)
        subprocess.run(['docker', 'kill', container], capture_output=True)
        # Relay continues to read any already-admitted upstream response, rather
        # than silently losing its usage when the client was terminated.
        settle_end = time.monotonic() + 15
        while any(not r['settled'] for r in relay.records) and time.monotonic() < settle_end:
            time.sleep(0.1)
        relay.flush()
        ended_ns = exit_report['agent_ended_ns'] if exit_report else observed_ns
        result = dict(run_id=run_id, product=product, smoke=smoke,
                      wall_seconds=(ended_ns - started_ns) / 1e9,
                      timeout_seconds=timeout, termination=termination, exit_report=exit_report,
                      storage=measurements, native=native,
                      provider=summarize_requests(relay.records),
                      time_to_first_provider_request_seconds=None,
                      resolved=False)
        forwarded = [r for r in relay.records if r['forwarded']]
        if forwarded:
            result['time_to_first_provider_request_seconds'] = (min(r['started_ns'] for r in forwarded) - started_ns) / 1e9
        result['native_execution_ok'] = bool(exit_report and exit_report['exit_code'] == 0 and termination is None)
        if smoke:
            path = workspace / 'BENCH_RESULT.txt'
            result['smoke_effect_verified'] = path.exists() and path.read_text().strip() == expected_digest
            result['calibration_passed'] = result['native_execution_ok'] and result['smoke_effect_verified'] and result['provider']['usage_complete']
        else:
            result['patch'] = compare_source(self.initial, workspace, output / 'patch.diff')
            grade_root = root / 'grading'
            grading_workspace(self.initial, workspace, grade_root)
            result['grade'] = self.grade(grade_root, output / 'grading')
            result['patch_resolved'] = bool(result['patch']['policy_passed'] and result['grade']['official_subset_resolved'])
            result['resolved'] = result['patch_resolved'] and result['native_execution_ok']
        dump(output / 'result.json', result)
        self.results.append(result)
        self.write_summary()
        print(json.dumps(dict(run_id=run_id, product=product, smoke=smoke,
                              native_execution_ok=result['native_execution_ok'],
                              resolved=result['resolved'], usage_complete=result['provider']['usage_complete'],
                              wall_seconds=result['wall_seconds'],
                              calibration_passed=result.get('calibration_passed')), ensure_ascii=False), flush=True)
        execute(['docker', 'rm', container])
        self.containers.remove(container)
        return result

    def write_summary(self):
        # Re-read accounting so responses settled after an earlier receipt can
        # improve coverage without overwriting any original run result.
        accounting = {relay.run_id: summarize_requests(relay.records) for relay in self.relays}
        dump(self.out / 'summary.json', dict(mode=self.args.mode, experiment_id=self.protocol['experiment_id'],
                                           instance_id=self.task['instance_id'], results=self.results,
                                           latest_accounting=accounting, elapsed_seconds=time.monotonic() - self.started))

    def run(self):
        self.prepare()
        if not self.controls():
            raise RuntimeError('Task environment controls failed; no model calls admitted')
        products = list(self.protocol['products'])
        random.Random(self.protocol['execution']['order_seed']).shuffle(products)
        dump(self.out / 'order.json', dict(smoke=products, formal=[products[i:] + products[:i]
                                                                 for i in range(self.protocol['execution']['formal_repeats'])]))
        smoke_prompt = ('Read BENCH_RECEIPT.txt, run Python to compute the SHA-256 of its exact bytes, '
                        'and write the hex digest to BENCH_RESULT.txt. Use your local tools to do this. '
                        'Do not change other files. Work in /testbed.')
        calibration = [self.run_product(product, 'smoke-' + product, smoke_prompt, smoke=True) for product in products]
        if not all(r['calibration_passed'] for r in calibration):
            raise RuntimeError('Native tool/usage calibration failed; no formal runs admitted')
        if self.args.mode == 'calibration':
            return
        prompt = (self.task['problem_statement'] + '\n\n'
                  'Fix this issue in the production source under src/. Work in /testbed. '
                  'Use the preinstalled Python and pytest to reproduce and verify your repair. '
                  'Limit final source changes to src/. Put temporary reproduction files under /tmp. '
                  'Do not modify existing tests, configuration, or dependency files. '
                  'The source snapshot has no original Git history. Network retrieval is unavailable. '
                  'Implement the fix and report the validation you performed.')
        for index in range(self.protocol['execution']['formal_repeats']):
            for product in products[index:] + products[:index]:
                if time.monotonic() - self.started > self.args.deadline_seconds - 800:
                    raise RuntimeError('Declared session deadline prevents admitting another complete run')
                self.run_product(product, f'block-{index + 1}-{product}', prompt)

    def cleanup(self):
        for container in self.containers:
            subprocess.run(['docker', 'unpause', container], capture_output=True)
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        for relay in self.relays:
            relay.close()
        if self.out.exists():
            self.write_summary()
            # Rendering is independent of solving/scoring and also retains
            # calibration failures in a directly reviewable report.
            subprocess.run(['python3', str(HERE / 'report.py'), str(self.out)], check=True)
        subprocess.run(['docker', 'network', 'rm', self.network], capture_output=True)
        # Only task-owned scratch trees, with raw state already archived above.
        if self.work.name.startswith(self.out.name + '-working-') and self.work.parent == self.out.parent:
            shutil.rmtree(self.work)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['calibration', 'formal'], default='calibration')
    p.add_argument('--deadline-seconds', type=int, default=14400)
    args = p.parse_args()
    campaign = Campaign(args)
    try:
        campaign.run()
    except Exception as exc:
        dump(campaign.out / 'campaign-error.json', dict(error=type(exc).__name__, message=str(exc)))
        raise
    finally:
        campaign.cleanup()


if __name__ == '__main__':
    main()
