#!/usr/bin/env python3
"""Measure native model-ready RSS/PSS without forwarding any inference request."""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tarfile
import threading
import time
from urllib.parse import urlsplit
import uuid

from relay import ROUTES
from resources import cgroup_snapshot, resolve_cgroup
from run import HERE, chown_tree, dump, execute, formal_prompt


def smaps_values(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == 'kB':
            values[parts[0].rstrip(':')] = int(parts[1])
    return values


def process_memory(cgroup, proc=Path('/proc')):
    pids = set()
    errors = []
    for path in cgroup.rglob('cgroup.procs'):
        try:
            pids.update(int(p) for p in path.read_text().split())
        except OSError as exc:
            errors.append(dict(path=str(path), error=type(exc).__name__))
    processes = []
    for pid in sorted(pids):
        try:
            values = smaps_values((proc / str(pid) / 'smaps_rollup').read_text())
            if not all(k in values for k in ('Rss', 'Pss')):
                raise ValueError('RSS/PSS fields unavailable')
            processes.append(dict(pid=pid, comm=(proc / str(pid) / 'comm').read_text().strip(),
                                  smaps_kib=values))
        except (OSError, ValueError) as exc:
            errors.append(dict(pid=pid, error=type(exc).__name__))
    complete = bool(pids) and not errors and len(processes) == len(pids)
    return dict(complete=complete, pids_seen=len(pids), processes=processes, errors=errors,
                rss_kib=sum(p['smaps_kib']['Rss'] for p in processes) if complete else None,
                pss_kib=sum(p['smaps_kib']['Pss'] for p in processes) if complete else None)


class ReadinessRelay:
    """Hold the first native model stream open. No upstream client exists."""
    def __init__(self, bind, output):
        self.output = output
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def send_json(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path in ('/models', '/v1/models', '/anthropic/v1/models'):
                    self.send_json(200, dict(object='list', data=[dict(id='deepseek-flash', object='model')]))
                else:
                    self.send_json(404, dict(error=dict(message='unexposed endpoint')))

            def do_POST(self):
                if urlsplit(self.path).path not in ROUTES:
                    return self.send_json(404, dict(error=dict(message='unexposed endpoint')))
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 16 * 1024**2:
                    return self.send_json(400, dict(error=dict(message='invalid body size')))
                raw = self.rfile.read(size)
                body = json.loads(raw)
                if body.get('model') != 'deepseek-flash':
                    return self.send_json(400, dict(error=dict(message='unexpected native request')))
                with owner.lock:
                    index = len(owner.requests)
                    owner.requests.append(dict(index=index, path=self.path,
                        started_utc=datetime.now(timezone.utc).isoformat(), forwarded=False,
                        upstream_requests=0, request_sha256=hashlib.sha256(raw).hexdigest()))
                    (owner.output / f'request-{index:02d}.json').write_bytes(raw)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                try:
                    heartbeat = b': readiness-probe; no upstream inference\n\n' if body.get('stream') else b' '
                    self.wfile.write(heartbeat)
                    self.wfile.flush()
                    owner.ready.set()
                    while not owner.stop.wait(2):
                        self.wfile.write(heartbeat)
                        self.wfile.flush()
                except OSError:
                    pass
                self.close_connection = True

        self.server = ThreadingHTTPServer((bind, 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://{bind}:{self.server.server_port}'

    def close(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        dump(self.output / 'readiness-requests.json', dict(requests=self.requests,
             upstream_requests=0, generated_tokens=0, external_provider_key_available=False))


def probe(args, initial, work, gateway, index):
    target = args.output / args.product / f'repeat-{index}'
    target.mkdir(parents=True)
    root = work / f'repeat-{index}'
    workspace, home, scratch = [root / name for name in ('workspace', 'home', 'tmp')]
    shutil.copytree(initial, workspace)
    home.mkdir(); scratch.mkdir(); scratch.chmod(0o1777)
    prompt = formal_prompt(json.loads((HERE / 'task.json').read_text()))
    (home / 'prompt.txt').write_text(prompt)
    chown_tree(root)
    relay = ReadinessRelay(gateway, target)
    container = 'rss-' + args.product + '-' + uuid.uuid4().hex[:8]
    result = dict(product=args.product, repeat=index, valid=False,
                  measurement='Model-ready native process tree, held before inference; not idle daemon or task peak',
                  prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                  settle_seconds=args.settle_seconds, sample_seconds=args.sample_seconds,
                  upstream_requests=0, generated_tokens=0)
    created = False
    try:
        execute(['docker', 'create', '--name', container, '--network', args.network,
                 '--cpus', '2', '--memory', '4g', '--pids-limit', '512', '--read-only',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                 '--env', f'BENCH_RUN_ID=memory-{args.product}-{index}',
                 '--mount', f'type=bind,src={workspace},dst=/testbed',
                 '--mount', f'type=bind,src={home},dst=/home/bench',
                 '--mount', f'type=bind,src={scratch},dst=/tmp',
                 args.image, args.product, relay.base, '/home/bench/prompt.txt'])
        created = True
        execute(['docker', 'start', container])
        pid = json.loads(execute(['docker', 'inspect', container]).stdout)[0]['State']['Pid']
        cgroup = resolve_cgroup(pid)
        if cgroup is None:
            raise ValueError('Cannot locate native container cgroup')
        deadline = time.monotonic() + 120
        while not relay.ready.wait(.2):
            if (home / 'agent-exit.json').exists():
                raise ValueError('Native CLI exited before model readiness')
            if time.monotonic() > deadline:
                raise TimeoutError('Native first model request not observed in 120 seconds')
        result['ready_utc'] = datetime.now(timezone.utc).isoformat()
        time.sleep(args.settle_seconds)
        samples = []
        end = time.monotonic() + args.sample_seconds
        with (target / 'memory-samples.jsonl').open('w') as stream:
            while time.monotonic() < end:
                if (home / 'agent-exit.json').exists():
                    raise ValueError('Native CLI exited during the memory window')
                memory = process_memory(cgroup)
                stat = {k: int(v) for k, v in (line.split() for line in (cgroup / 'memory.stat').read_text().splitlines())}
                row = dict(monotonic_ns=time.monotonic_ns(), processes=memory,
                           cgroup=cgroup_snapshot(cgroup), memory_stat=stat)
                stream.write(json.dumps(row) + '\n'); stream.flush()
                samples.append(row)
                time.sleep(1)
        good = [s for s in samples if s['processes']['complete']]
        if len(good) != len(samples) or len(good) < max(3, args.sample_seconds // 2):
            raise ValueError('Incomplete process-tree RSS/PSS coverage')
        result.update(valid=True, samples=len(samples),
            median_rss_mib=statistics.median(s['processes']['rss_kib'] for s in good) / 1024,
            median_pss_mib=statistics.median(s['processes']['pss_kib'] for s in good) / 1024,
            min_pss_mib=min(s['processes']['pss_kib'] for s in good) / 1024,
            max_pss_mib=max(s['processes']['pss_kib'] for s in good) / 1024,
            median_cgroup_anon_mib=statistics.median(s['memory_stat']['anon'] for s in good) / 1024**2,
            median_cgroup_file_mib=statistics.median(s['memory_stat']['file'] for s in good) / 1024**2)
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if created:
            subprocess.run(['docker', 'pause', container], capture_output=True)
            inspection = execute(['docker', 'inspect', container]).stdout
            dump(target / 'container.json', json.loads(inspection)[0])
            logs = subprocess.run(['docker', 'logs', '--timestamps', container], capture_output=True, text=True)
            (target / 'stdout.log').write_text(logs.stdout); (target / 'stderr.log').write_text(logs.stderr)
            with tarfile.open(target / 'native-state.tar.gz', 'w:gz', dereference=False) as archive:
                for path in sorted(home.rglob('*')):
                    if path.is_file() and not path.is_symlink():
                        archive.add(path, arcname=path.relative_to(home), recursive=False)
            subprocess.run(['docker', 'unpause', container], capture_output=True)
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        relay.close()
        result['native_requests_held'] = len(relay.requests)
        if not relay.requests:
            result.update(valid=False, error='No native model readiness request')
        dump(target / 'result.json', result)
        print(json.dumps(result), flush=True)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', default='five-harness-swe')
    p.add_argument('--product')
    p.add_argument('--summarize', action='store_true')
    p.add_argument('--settle-seconds', type=int, default=10)
    p.add_argument('--sample-seconds', type=int, default=20)
    args = p.parse_args()
    protocol = json.loads((HERE / 'protocol-six.json').read_text())
    args.output = args.output.resolve()
    if args.summarize:
        products = {}
        images = set()
        for product in protocol['products']:
            path = args.output / product
            data = json.loads((path / 'summary.json').read_text())
            if len(data['results']) != 3 or not data['all_valid'] or data['upstream_requests'] != 0:
                raise ValueError('Incomplete memory measurement: ' + product)
            images.add(json.loads((path / 'environment.json').read_text())['image_id'])
            products[product] = dict(repeats=data['results'],
                mean_ready_pss_mib=statistics.mean(r['median_pss_mib'] for r in data['results']),
                mean_ready_rss_mib=statistics.mean(r['median_rss_mib'] for r in data['results']))
        if len(images) != 1:
            raise ValueError('Memory products did not use one common image')
        dump(args.output / 'summary.json', dict(
            phase='Initialized native CLI waiting for its first model response; no task solving',
            image_id=next(iter(images)), products=products, upstream_requests=0, generated_tokens=0,
            pss_order=sorted(products, key=lambda p: products[p]['mean_ready_pss_mib'])))
        return
    if os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('Memory-only measurement must not receive provider credentials')
    if args.product not in protocol['products']:
        raise ValueError('Unknown product')
    args.output.mkdir(parents=True, exist_ok=True)
    product_out = args.output / args.product; product_out.mkdir()
    work = args.output.parent / ('memory-working-' + uuid.uuid4().hex[:8]); work.mkdir()
    initial = work / 'initial'; initial.mkdir()
    args.network = 'memory-' + uuid.uuid4().hex[:10]
    network_created = False
    results = []
    try:
        template = execute(['docker', 'create', args.image]).stdout.strip()
        try:
            execute(['docker', 'cp', template + ':/testbed/.', str(initial)])
        finally:
            execute(['docker', 'rm', template])
        execute(['docker', 'network', 'create', '--internal', args.network]); network_created = True
        info = json.loads(execute(['docker', 'network', 'inspect', args.network]).stdout)[0]
        image = json.loads(execute(['docker', 'image', 'inspect', args.image]).stdout)[0]
        dump(product_out / 'environment.json', dict(image_id=image['Id'], network=info,
             controller_sha=os.environ.get('GITHUB_SHA'), github_run_id=os.environ.get('GITHUB_RUN_ID'),
             products=protocol['products'], task_sha256=hashlib.sha256((HERE / 'task.json').read_bytes()).hexdigest(),
             same_native_launcher=True, upstream_requests=0))
        for index in range(1, 4):
            results.append(probe(args, initial, work, info['IPAM']['Config'][0]['Gateway'], index))
        dump(product_out / 'summary.json', dict(product=args.product, results=results,
            all_valid=all(r['valid'] for r in results), upstream_requests=0))
        if not all(r['valid'] for r in results):
            raise ValueError('Memory observation incomplete; no valid ranking admitted')
    finally:
        if network_created:
            subprocess.run(['docker', 'network', 'rm', args.network], capture_output=True)
        shutil.rmtree(work)


if __name__ == '__main__':
    main()
