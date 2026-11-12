#!/usr/bin/env python3
"""Measure three fresh native idle process trees on the hosted worker."""
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

from memory_probe import smaps_values
from resources import cgroup_snapshot, resolve_cgroup
from run import chown_tree, dump, execute


def native_memory(cgroup, namespace_pid):
    pids = {int(p) for path in cgroup.rglob('cgroup.procs') for p in path.read_text().split()}
    statuses = {}
    errors = []
    for pid in pids:
        try:
            statuses[pid] = dict(line.split(':', 1) for line in (Path('/proc')/str(pid)/'status').read_text().splitlines() if ':' in line)
        except OSError:
            pass
    roots = [p for p,s in statuses.items() if int(s.get('NSpid', str(p)).split()[-1]) == namespace_pid]
    if len(roots) != 1:
        return dict(complete=False, error='native_root_not_found', rss_kib=None, pss_kib=None)
    selected = set(roots)
    while True:
        more = {p for p,s in statuses.items() if int(s['PPid']) in selected}
        if more <= selected:
            break
        selected |= more
    processes = []
    for pid in sorted(selected):
        try:
            values = smaps_values((Path('/proc')/str(pid)/'smaps_rollup').read_text())
            if not all(k in values for k in ('Rss', 'Pss')):
                raise ValueError('missing_fields')
            processes.append(dict(pid=pid, name=statuses[pid]['Name'].strip(), smaps_kib=values))
        except (OSError, ValueError) as exc:
            errors.append(dict(pid=pid, error=type(exc).__name__))
    complete = bool(processes) and not errors and len(processes) == len(selected)
    return dict(complete=complete, processes=processes, errors=errors,
                rss_kib=sum(p['smaps_kib']['Rss'] for p in processes) if complete else None,
                pss_kib=sum(p['smaps_kib']['Pss'] for p in processes) if complete else None,
                scope='native process tree; Python probe and no-inference metadata stub excluded')


def repeat(args, index):
    target = args.output/f'repeat-{index}'; target.mkdir()
    work = args.output.parent/('idle-'+uuid.uuid4().hex); work.mkdir()
    home, workspace, scratch = [work/n for n in ('home', 'workspace', 'tmp')]
    for path in (home, workspace, scratch):
        path.mkdir()
    scratch.chmod(0o1777); chown_tree(work)
    container = 'idle-'+uuid.uuid4().hex[:12]
    result = dict(product=args.product, repeat=index, valid=False, phase='initial idle; no task',
                  settle_seconds=60, sample_seconds=60, memory_limit_bytes=8*1024**3,
                  swap_disabled=True, cpus=2, external_network='none', model_credentials=False)
    created = False
    try:
        execute(['docker', 'create', '--name', container, '--network', 'none', '--read-only',
                 '--cpus', '2', '--memory', str(8*1024**3), '--memory-swap', str(8*1024**3),
                 '--pids-limit', '512', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                 '--mount', f'type=bind,src={home},dst=/home/bench',
                 '--mount', f'type=bind,src={workspace},dst=/testbed',
                 '--mount', f'type=bind,src={scratch},dst=/tmp',
                 '--entrypoint', '/usr/bin/python3', args.image,
                 '/opt/bench/idle_native_entry.py', '--product', args.product])
        created = True; execute(['docker', 'start', container])
        deadline = time.monotonic()+540
        while not (home/'idle-ready.json').exists():
            state = json.loads(execute(['docker', 'inspect', container]).stdout)[0]
            if not state['State']['Running']:
                raise ValueError('Native idle startup failed; see terminal and container logs')
            if time.monotonic() > deadline:
                raise TimeoutError('No idle readiness within 540 seconds')
            time.sleep(2)
        ready = json.loads((home/'idle-ready.json').read_text())
        dump(target/'readiness.json', ready)
        state = json.loads(execute(['docker', 'inspect', container]).stdout)[0]
        cgroup = resolve_cgroup(state['State']['Pid'])
        if cgroup is None:
            raise ValueError('Container cgroup unavailable')
        print(json.dumps(dict(product=args.product, repeat=index, phase='idle_ready_settling_60_seconds')), flush=True)
        time.sleep(60)
        samples = []
        with (target/'memory-samples.jsonl').open('w') as stream:
            for _ in range(60):
                memory = native_memory(cgroup, ready['native_child_pid'])
                row = dict(utc=datetime.now(timezone.utc).isoformat(), memory=memory,
                           cgroup=cgroup_snapshot(cgroup))
                stream.write(json.dumps(row)+'\n'); stream.flush(); samples.append(row)
                time.sleep(1)
        state = json.loads(execute(['docker', 'inspect', container]).stdout)[0]
        if not state['State']['Running'] or not all(s['memory']['complete'] for s in samples):
            raise ValueError('Incomplete native process memory coverage or native process exited')
        network = json.loads((home/'idle-network.json').read_text())
        if network['inference_attempts'] != 0:
            raise ValueError('Inference attempted during idle observation')
        dump(target/'network.json', network)
        if args.product == 'openclaw57_patched':
            text = '\n'.join(p.read_text(errors='replace') for p in home.rglob('terminal.ansi'))
            if '[agentloop] all apps loaded' not in text or '[agentloop] tools prewarm complete' not in text:
                raise ValueError('AgentLoop idle initialization not verified')
            result['runtime']='agentloop'
        result.update(valid=True, samples=len(samples), native_command=ready['command'])
        for key in ('rss', 'pss'):
            values = [s['memory'][key+'_kib']/1024 for s in samples]
            result.update({f'median_{key}_mib':statistics.median(values),
                           f'min_{key}_mib':min(values), f'max_{key}_mib':max(values)})
    except Exception as exc:
        result['error'] = type(exc).__name__+': '+str(exc)
    finally:
        if created:
            subprocess.run(['docker', 'pause', container], capture_output=True)
            logs = subprocess.run(['docker', 'logs', '--timestamps', container], capture_output=True, text=True)
            (target/'stdout.log').write_text(logs.stdout); (target/'stderr.log').write_text(logs.stderr)
            dump(target/'container.json', json.loads(execute(['docker', 'inspect', container]).stdout)[0])
            with tarfile.open(target/'native-state.tar.gz','w:gz') as tf:
                for path in home.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        tf.add(path, arcname=path.relative_to(home), recursive=False)
            subprocess.run(['docker', 'unpause', container], capture_output=True)
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        shutil.rmtree(work)
        dump(target/'result.json', result); print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--product', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', default='six-harness-expanded')
    p.add_argument('--repeat', type=int, choices=[1,2,3])
    p.add_argument('--summarize', action='store_true')
    args = p.parse_args()
    if os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('Idle measurement must not receive real provider credentials')
    if args.product not in ('openclaw57_patched','openclaw','dsh','codex','claude','hermes'):
        raise ValueError('Unknown product')
    args.output = args.output.resolve(); args.output.mkdir(parents=True, exist_ok=True)
    if args.repeat:
        if not repeat(args,args.repeat)['valid']:
            raise ValueError('Invalid idle observation; no RSS/PSS admitted')
    if args.summarize:
        results = [json.loads(p.read_text()) for p in sorted(args.output.glob('repeat-*/result.json'))]
        valid = len(results)==3 and all(r['valid'] for r in results)
        summary = dict(product=args.product, all_valid=valid, results=results,
                       image_id=execute(['docker','image','inspect',args.image,'--format','{{.Id}}']).stdout.strip(),
                       controller_sha=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'))
        if valid:
            for k in ('rss','pss'):
                summary['mean_idle_'+k+'_mib']=statistics.mean(r['median_'+k+'_mib'] for r in results)
        dump(args.output/'summary.json',summary)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
                f.write('\n### Initial idle RSS/PSS: '+args.product+'\n\n```json\n'+json.dumps(summary,indent=2)+'\n```\n')
        if not valid:
            raise ValueError('Three valid idle observations required')


if __name__ == '__main__':
    main()
