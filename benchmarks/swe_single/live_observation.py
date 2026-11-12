"""Common observer: phase events, live CLI logs and process-tree memory."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time

from memory_probe import process_memory
from resources import cgroup_snapshot


def validate_agentloop(home, logs):
    config = json.loads((home / '.openclaw/openclaw.json').read_text())
    debug = home / 'agentloop-debug.log'
    text = logs + (debug.read_text(errors='replace') if debug.exists() else '')
    configured = config['agents']['defaults'].get('agentRuntime', {}).get('id') == 'agentloop'
    entered = '[agentloop] loop.run starting' in text
    return dict(valid=configured and entered, requested='agentloop', configured=configured,
                sdk_loop_entered=entered, fallback_allowed=False,
                trajectory_files=[str(p.relative_to(home)) for p in home.rglob('*.trajectory.jsonl')])


class RunObserver:
    def __init__(self, output, container, collector, relay, started_ns, **identity):
        self.output, self.container = output, container
        self.collector, self.relay, self.started_ns = collector, relay, started_ns
        self.identity = identity
        self.stopped = threading.Event()
        self.lock = threading.Lock()

    def phase(self, phase, **details):
        event = dict(utc=datetime.now(timezone.utc).isoformat(), phase=phase,
                     elapsed_seconds=round((time.monotonic_ns()-self.started_ns)/1e9, 2),
                     **self.identity, **details)
        with self.lock:
            with (self.output / 'timeline.jsonl').open('a') as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def start(self):
        self.stdout = (self.output / 'native-live.stdout.log').open('w')
        self.stderr = (self.output / 'native-live.stderr.log').open('w')
        self.logs = subprocess.Popen(['docker', 'logs', '--follow', '--timestamps', self.container],
                                     stdout=self.stdout, stderr=self.stderr)
        self.phase('native_started')
        self.thread = threading.Thread(target=self.observe, daemon=True)
        self.thread.start()

    def observe(self):
        with (self.output / 'process-memory.jsonl').open('w') as stream:
            while not self.stopped.is_set():
                try:
                    memory = process_memory(self.collector.cgroup) if self.collector.cgroup else None
                    stream.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
                                     elapsed_seconds=(time.monotonic_ns()-self.started_ns)/1e9,
                                     memory=memory)) + '\n')
                    stream.flush()
                    records = list(self.relay.records)
                    forwarded = [r for r in records if r['forwarded']]
                    tools = Counter(t.get('name', 'unknown') for r in forwarded
                                    for t in r.get('model_emitted_tool_calls', []))
                    self.phase('running', model_requests=len(forwarded),
                               pending_requests=sum(not r['settled'] for r in forwarded),
                               completed_requests=sum(r.get('terminal', False) for r in forwarded),
                               observed_tool_calls=sum(tools.values()), observed_tool_names=dict(tools),
                               process_rss_mib=memory['rss_kib']/1024 if memory and memory['complete'] else None,
                               process_pss_mib=memory['pss_kib']/1024 if memory and memory['complete'] else None,
                               container_memory_bytes=cgroup_snapshot(self.collector.cgroup).get('memory_current'))
                except Exception as exc:
                    self.phase('observer_error', error=type(exc).__name__)
                self.stopped.wait(15)

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=5)
        self.logs.terminate()
        try:
            self.logs.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.logs.kill()
            self.logs.wait()
        self.stdout.close()
        self.stderr.close()
