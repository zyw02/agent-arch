#!/usr/bin/env python3
"""Observe an idle, initialized AgentLoop Gateway without sending a task."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tarfile
import time
import uuid

from memory_probe import process_memory
from resources import cgroup_snapshot, resolve_cgroup
from run import chown_tree, dump, execute


NODE_FLAGS = ['--max-old-space-size=700', '--max-semi-space-size=8',
              '--optimize-for-size', '--expose-gc']


def configuration(home):
    return dict(
        gateway=dict(mode='local', auth=dict(mode='token', token='idle-probe-only'),
                     controlUi=dict(enabled=False)),
        agents=dict(defaults=dict(workspace='/testbed', skipBootstrap=True,
                    agentRuntime=dict(id='agentloop'),
                    model=dict(primary='deepseek/deepseek-flash'),
                    memorySearch=dict(enabled=False))),
        models=dict(providers=dict(deepseek=dict(baseUrl='http://127.0.0.1:9/v1',
                    apiKey='idle-probe-only', api='openai-completions',
                    models=[dict(id='deepseek-flash', name='No inference', reasoning=True,
                                 input=['text'], contextWindow=1048576, maxTokens=16384)]))),
        plugins=dict(entries=dict(agentloop=dict(enabled=True,
                    config=dict(warmupAttempt=dict(enabled=False))))),
        logging=dict(level='debug', consoleLevel='info', file='/home/bench/gateway-debug.log'),
        cron=dict(enabled=False))


def validate_idle(home, logs):
    config = json.loads((home / '.openclaw/openclaw.json').read_text())
    if config['agents']['defaults']['agentRuntime']['id'] != 'agentloop':
        raise ValueError('AgentLoop is not configured as the runtime')
    if config['plugins']['entries']['agentloop']['config']['warmupAttempt']['enabled']:
        raise ValueError('Model warmup must be disabled in the idle observation')
    if '[agentloop] tools prewarm ==========' not in logs:
        raise ValueError('AgentLoop SDK initialization was not observed')
    if '[agentloop] all apps loaded' not in logs:
        raise ValueError('AgentLoop app prewarm did not finish')
    if '[agentloop] init failed:' in logs or 'apps warmup failed' in logs:
        raise ValueError('AgentLoop initialization failed')
    trajectories = list(home.rglob('*.trajectory.jsonl'))
    if trajectories:
        raise ValueError('Unexpected agent task trace in idle observation')
    return dict(configured_runtime='agentloop', sdk_initialized=True,
                apps_prewarm_complete=True, agent_task_traces=0,
                model_warmup_enabled=False)


def health(container):
    code = ('import json,urllib.request; '
            'r=urllib.request.urlopen("http://127.0.0.1:18789/readyz",timeout=2); '
            'print(r.read().decode())')
    result = subprocess.run(['docker', 'exec', container, '/usr/bin/python3', '-c', code],
                            capture_output=True, text=True, timeout=8)
    if result.returncode:
        return None
    data = json.loads(result.stdout)
    return data if data.get('ready') is True else None


def repeat(args, index):
    target = args.output / f'repeat-{index}'; target.mkdir()
    work = args.output.parent / ('idle-work-' + uuid.uuid4().hex[:8]); work.mkdir()
    home, workspace, scratch = [work / n for n in ('home', 'workspace', 'tmp')]
    for path in (home, workspace, scratch):
        path.mkdir()
    scratch.chmod(0o1777)
    config = home / '.openclaw/openclaw.json'; config.parent.mkdir()
    dump(config, configuration(home)); chown_tree(work)
    container = 'idle-agentloop-' + uuid.uuid4().hex[:8]
    result = dict(repeat=index, valid=False, phase='idle Gateway; no agent task sent',
                  requested_runtime='agentloop', node_flags=NODE_FLAGS,
                  settle_seconds=args.settle_seconds, sample_seconds=args.sample_seconds,
                  model_warmup_enabled=False, upstream_network='none')
    created = False
    try:
        execute(['docker', 'create', '--name', container, '--network', 'none',
                 '--cpus', '2', '--memory', '4g', '--pids-limit', '512', '--read-only',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                 '--env', 'OPENCLAW_AGENT_RUNTIME=agentloop',
                 '--env', 'OPENCLAW_STATE_DIR=/home/bench/.openclaw',
                 '--env', 'OPENCLAW_CONFIG_PATH=/home/bench/.openclaw/openclaw.json',
                 '--env', 'OPENCLAW_SKIP_CHANNELS=1', '--env', 'AGENTLOOP_WARMUP=0',
                 '--mount', f'type=bind,src={workspace},dst=/testbed',
                 '--mount', f'type=bind,src={home},dst=/home/bench',
                 '--mount', f'type=bind,src={scratch},dst=/tmp',
                 '--entrypoint', 'node', args.image, *NODE_FLAGS,
                 '/opt/openclaw57/openclaw.mjs', 'gateway', 'run',
                 '--bind', 'loopback', '--port', '18789', '--allow-unconfigured'])
        created = True; execute(['docker', 'start', container])
        deadline = time.monotonic() + 180
        while True:
            inspection = json.loads(execute(['docker', 'inspect', container]).stdout)[0]
            if not inspection['State']['Running']:
                raise ValueError('Gateway exited before readiness')
            ready = health(container)
            logs = subprocess.run(['docker', 'logs', container], capture_output=True, text=True)
            text = logs.stdout + logs.stderr
            if ready and '[agentloop] all apps loaded' in text:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Gateway/AgentLoop did not become ready within 180 seconds')
            time.sleep(2)
        result['ready_utc'] = datetime.now(timezone.utc).isoformat()
        dump(target / 'health-before.json', ready)
        cgroup = resolve_cgroup(inspection['State']['Pid'])
        if cgroup is None:
            raise ValueError('No container cgroup')
        time.sleep(args.settle_seconds)
        samples = []; start = time.monotonic()
        with (target / 'memory-samples.jsonl').open('w') as stream:
            while time.monotonic() - start < args.sample_seconds:
                memory = process_memory(cgroup)
                stat = {k: int(v) for k, v in (line.split() for line in (cgroup / 'memory.stat').read_text().splitlines())}
                row = dict(monotonic_ns=time.monotonic_ns(), elapsed_seconds=time.monotonic()-start,
                           processes=memory, cgroup=cgroup_snapshot(cgroup), memory_stat=stat)
                stream.write(json.dumps(row) + '\n'); stream.flush(); samples.append(row)
                time.sleep(1)
        if len(samples) < args.sample_seconds // 2 or any(not s['processes']['complete'] for s in samples):
            raise ValueError('Incomplete RSS/PSS coverage')
        ready = health(container)
        if not ready:
            raise ValueError('Gateway was not ready after the idle window')
        dump(target / 'health-after.json', ready)
        logs = subprocess.run(['docker', 'logs', container], capture_output=True, text=True)
        debug = home / 'gateway-debug.log'
        validation = validate_idle(home, logs.stdout + logs.stderr + (debug.read_text() if debug.exists() else ''))
        for key in ('rss', 'pss'):
            values = [s['processes'][key + '_kib'] / 1024 for s in samples]
            result.update({f'median_{key}_mib': statistics.median(values),
                           f'min_{key}_mib': min(values), f'max_{key}_mib': max(values)})
        result.update(valid=True, samples=len(samples), validation=validation,
                      median_cgroup_anon_mib=statistics.median(s['memory_stat']['anon'] for s in samples)/1024**2,
                      median_cgroup_file_mib=statistics.median(s['memory_stat']['file'] for s in samples)/1024**2)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if created:
            subprocess.run(['docker', 'pause', container], capture_output=True)
            dump(target / 'container.json', json.loads(execute(['docker', 'inspect', container]).stdout)[0])
            logs = subprocess.run(['docker', 'logs', '--timestamps', container], capture_output=True, text=True)
            (target / 'stdout.log').write_text(logs.stdout); (target / 'stderr.log').write_text(logs.stderr)
            with tarfile.open(target / 'native-state.tar.gz', 'w:gz', dereference=False) as archive:
                for path in sorted(home.rglob('*')):
                    if path.is_file() and not path.is_symlink():
                        archive.add(path, arcname=path.relative_to(home), recursive=False)
            subprocess.run(['docker', 'unpause', container], capture_output=True)
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        shutil.rmtree(work)
        dump(target / 'result.json', result); print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', default='five-harness-swe')
    p.add_argument('--settle-seconds', type=int, default=60)
    p.add_argument('--sample-seconds', type=int, default=60)
    args = p.parse_args()
    if os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('Idle memory observation must not receive model credentials')
    args.output = args.output.resolve(); args.output.mkdir(parents=True)
    dump(args.output / 'environment.json', dict(
        image=json.loads(execute(['docker', 'image', 'inspect', args.image]).stdout)[0],
        controller_sha=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'),
        phase='idle Gateway with AgentLoop enabled and prewarmed; no agent task',
        build='Full pinned source build; not the unprovided 231M departmental package',
        node_flags=NODE_FLAGS, flag_source='scripts/zte/package-minimal.mjs startup template',
        external_network=False, model_credentials_available=False))
    results = [repeat(args, i) for i in range(1, 4)]
    summary = dict(results=results, all_valid=all(r['valid'] for r in results))
    if summary['all_valid']:
        for key in ('rss', 'pss'):
            summary[f'mean_idle_{key}_mib'] = statistics.mean(r[f'median_{key}_mib'] for r in results)
    dump(args.output / 'summary.json', summary)
    if not summary['all_valid']:
        raise ValueError('Idle observation incomplete; no result admitted')


if __name__ == '__main__':
    main()
