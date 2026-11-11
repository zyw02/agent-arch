"""Independent Linux cgroup and filesystem measurements, including storage."""
from collections import defaultdict
import json
import os
from pathlib import Path
import stat
import threading
import time


def storage_category(relative):
    name = str(relative).lower()
    if name.endswith(('.db', '.sqlite', '.sqlite3', '-wal', '-shm', '.db-journal')):
        return 'database_and_journal'
    if any(p in ('cache', '.cache', '__pycache__', '.pytest_cache', '.hypothesis') for p in relative.parts):
        return 'cache'
    if any(p in ('logs', 'sessions', 'projects', 'telemetry') for p in relative.parts) or name.endswith(('.log', '.jsonl', '.zstd', '.zst')):
        return 'logs_and_transcripts'
    return 'other'


def disk_tree(root):
    """Do not follow symlinks. Logical bytes count entries, allocation dedups inodes."""
    root = Path(root)
    logical = allocated = files = directories = symlinks = 0
    seen = set()
    categories = defaultdict(lambda: dict(logical_bytes=0, allocated_bytes=0, files=0))
    errors = []
    for parent, dirs, names in os.walk(root, followlinks=False):
        directories += 1
        for name in dirs + names:
            path = Path(parent) / name
            try:
                info = path.lstat()
            except OSError as exc:
                errors.append(dict(path=str(path.relative_to(root)), error=type(exc).__name__))
                continue
            if stat.S_ISLNK(info.st_mode):
                symlinks += 1
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            files += 1
            logical += info.st_size
            identity = (info.st_dev, info.st_ino)
            allocation = 0 if identity in seen else info.st_blocks * 512
            seen.add(identity)
            allocated += allocation
            bucket = categories[storage_category(path.relative_to(root))]
            bucket['logical_bytes'] += info.st_size
            bucket['allocated_bytes'] += allocation
            bucket['files'] += 1
    return dict(logical_bytes=logical, allocated_bytes=allocated, files=files,
                directories=directories, symlinks=symlinks, categories=dict(categories),
                scan_errors=errors, exists=root.exists(),
                byte_scope='regular files; filesystem directory/inode overhead excluded')


def numeric_file(path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def key_values(path):
    try:
        return {parts[0]: int(parts[1]) for line in path.read_text().splitlines()
                if len(parts := line.split()) == 2}
    except (OSError, ValueError):
        return None


def cgroup_snapshot(root):
    if root is None:
        return dict(available=False, reason='container_cgroup_not_resolved')
    io = defaultdict(int)
    try:
        for line in (root / 'io.stat').read_text().splitlines():
            for item in line.split()[1:]:
                key, value = item.split('=')
                io[key] += int(value)
        io = dict(io)
    except (OSError, ValueError):
        io = None
    return dict(available=True, cpu=key_values(root / 'cpu.stat'),
                memory_current=numeric_file(root / 'memory.current'),
                memory_peak=numeric_file(root / 'memory.peak'),
                memory_events=key_values(root / 'memory.events'),
                pids=numeric_file(root / 'pids.current'), io=io)


def resolve_cgroup(pid):
    try:
        for line in Path(f'/proc/{pid}/cgroup').read_text().splitlines():
            if line.startswith('0::'):
                root = Path('/sys/fs/cgroup') / line[3:].lstrip('/')
                if root.is_dir():
                    return root
    except OSError:
        pass
    return None


class Collector:
    def __init__(self, output, workspace, home, scratch, storage_limit):
        self.output = Path(output)
        self.paths = dict(workspace=Path(workspace), home=Path(home), tmp=Path(scratch))
        self.initial = {k: disk_tree(v) for k, v in self.paths.items()}
        self.last_storage = self.initial
        self.peaks = {k: {m: v[m] for m in ('logical_bytes', 'allocated_bytes', 'files', 'directories')}
                      for k, v in self.initial.items()}
        self.storage_limit = storage_limit
        self.storage_limit_exceeded = False
        self.stop_event = threading.Event()
        self.cgroup = None
        self.last_cgroup = None
        self.samples = 0

    def start(self, pid):
        self.cgroup = resolve_cgroup(pid)
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def _sample(self):
        last_disk = 0
        with (self.output / 'resource-samples.jsonl').open('w') as stream:
            while not self.stop_event.is_set():
                now = time.monotonic()
                cgroup = cgroup_snapshot(self.cgroup)
                # Containers deliberately remain alive after agent completion,
                # so final cumulative counters are read before Docker removes it.
                self.last_cgroup = cgroup
                row = dict(monotonic_ns=time.monotonic_ns(), cgroup=cgroup)
                if now - last_disk >= 2:
                    self.last_storage = {k: disk_tree(v) for k, v in self.paths.items()}
                    row['storage'] = self.last_storage
                    for key, measured in self.last_storage.items():
                        for metric in ('logical_bytes', 'allocated_bytes', 'files', 'directories'):
                            self.peaks[key][metric] = max(self.peaks[key][metric], measured[metric])
                    self.storage_limit_exceeded |= sum(v['logical_bytes'] for v in self.last_storage.values()) > self.storage_limit
                    last_disk = now
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                stream.flush()
                self.samples += 1
                self.stop_event.wait(0.5)

    def finish(self):
        self.stop_event.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=3)
        final = {k: disk_tree(v) for k, v in self.paths.items()}
        for key, measured in final.items():
            for metric in ('logical_bytes', 'allocated_bytes', 'files', 'directories'):
                self.peaks[key][metric] = max(self.peaks[key][metric], measured[metric])
        cgroup = cgroup_snapshot(self.cgroup)
        if not cgroup.get('cpu') and self.last_cgroup:
            cgroup = self.last_cgroup
        result = dict(initial=self.initial, final=final, sampled_peak=self.peaks,
                      storage_peak_exact=False, storage_peak_sampling_seconds=2,
                      storage_peak_semantics='Non-atomic scans during execution: approximate maxima, not exact peaks or guaranteed bounds under concurrent mutations. Final scan runs while the container is paused.',
                      cgroup=cgroup, samples=self.samples,
                      sample_interval_seconds=0.5, storage_limit_exceeded=self.storage_limit_exceeded,
                      io_semantics='cgroup device I/O, not logical application reads/writes',
                      delta={k: {m: final[k][m] - self.initial[k][m]
                                 for m in ('logical_bytes', 'allocated_bytes', 'files', 'directories')}
                             for k in self.paths})
        (self.output / 'resources.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
