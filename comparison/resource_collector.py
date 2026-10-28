#!/usr/bin/env python3
"""Owned cgroup + process-memory + task-path collector for hosted native arms."""
import os
import json
import resource
import subprocess
import sys
from pathlib import Path
import threading
import time
import uuid


def counters(text):
    return {key.rstrip(':'):int(value) for line in text.splitlines() if len(parts:=line.split())==2 for key,value in [parts]}


def disk_inventory(paths):
    seen=set();categories={};errors=[]
    for name,root in paths.items():
        logical=allocated=files=0;stack=[Path(root)]
        while stack:
            path=stack.pop()
            try:
                st=path.lstat()
                identity=(st.st_dev,st.st_ino)
                if identity in seen:continue
                seen.add(identity);logical+=st.st_size;allocated+=st.st_blocks*512;files+=1
                if path.is_dir() and not path.is_symlink():stack.extend(path.iterdir())
            except FileNotFoundError:continue
            except OSError as error:errors.append({'category':name,'error':type(error).__name__})
        categories[name]=dict(logical_bytes=logical,allocated_bytes=allocated,objects=files)
    return dict(categories=categories,logical_bytes=sum(v['logical_bytes'] for v in categories.values()),
        allocated_bytes=sum(v['allocated_bytes'] for v in categories.values()),errors=errors,
        method='lstat allocated blocks; unique inode counted once across paths, symlinks not followed; reflink/COW sharing not resolved')


class ResourceCollector:
    def __init__(self,paths,interval=.2):
        self.paths=paths;self.interval=interval;self.samples=[];self.errors=[];self.group=None
        self.started_ns=time.monotonic_ns();self.initial_disk=disk_inventory(paths)
        self.stop_event=threading.Event();self.observer_cpu=0;self.sample_lock=threading.Lock()
        base=Path(os.environ.get('AGENT_ARCH_CGROUP_ROOT','/sys/fs/cgroup/system.slice'))
        try:
            group=base/('agent-arch-probe-'+str(os.getpid())+'-'+uuid.uuid4().hex[:10]);group.mkdir()
            self.group=group
            (group/'memory.max').write_text(str(3*1024**3));(group/'memory.swap.max').write_text('0')
            (group/'pids.max').write_text('128');(group/'cpu.max').write_text('200000 100000')
        except OSError as e:
            self.errors.append(dict(stage='cgroup_setup',error=type(e).__name__))
            if self.group:
                try:self.group.rmdir()
                except OSError:pass
            self.group=None
        self.memory_reader=None;self.memory_reader_cpu_seconds=None;self.memory_reader_self_cpu_seconds=None
        if self.group:
            try:
                prefix=[] if os.geteuid()==0 else ['sudo','-n','--preserve-env=AGENT_ARCH_CGROUP_ROOT']
                self.memory_reader=subprocess.Popen([*prefix,sys.executable,str(Path(__file__).with_name('resource_memory_reader.py')),str(self.group)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            except OSError as error:self.errors.append(dict(stage='memory_reader_start',error=type(error).__name__))
        self.thread=threading.Thread(target=self.sample_loop,daemon=True);self.thread.start()

    def command(self,command):
        if self.group is None:return command
        import sys
        prefix=[] if os.geteuid()==0 else ['sudo','-n','--preserve-env=PATH,HOME,TMPDIR,DSH_HOME,DEEPSEEK_BASE_URL,DEEPSEEK_API_KEY,DSH_PERMISSION_MODE,OPENCLAW_STATE_DIR,OPENCLAW_CONFIG_PATH,AGENT_ARCH_CGROUP_ROOT']
        return [*prefix,sys.executable,str(Path(__file__).with_name('resource_launcher.py')),str(self.group),str(os.getuid()),str(os.getgid()),*command]

    def sample(self):
        with self.sample_lock:self._sample()

    def _sample(self):
        row=dict(monotonic_ns=time.monotonic_ns(),disk=disk_inventory(self.paths))
        if self.group:
            try:
                if self.memory_reader is not None:
                    self.memory_reader.stdin.write('sample\n');self.memory_reader.stdin.flush()
                    memory=json.loads(self.memory_reader.stdout.readline())
                    self.errors.extend(memory.pop('errors',[]));row.update(memory)
                else:self.errors.append(dict(stage='memory_reader',error='unavailable'))
                row.update(cgroup_memory_current_bytes=int((self.group/'memory.current').read_text()),cpu=counters((self.group/'cpu.stat').read_text()))
            except (OSError,ValueError) as e:self.errors.append(dict(stage='sample',error=type(e).__name__))
        self.samples.append(row)

    def sample_loop(self):
        started=time.thread_time()
        try:
            while not self.stop_event.is_set():
                self.sample();self.stop_event.wait(self.interval)
        except Exception as error:
            self.errors.append(dict(stage='sampling_loop',error=type(error).__name__))
        finally:self.observer_cpu+=time.thread_time()-started

    def finish(self):
        self.stop_event.set();self.thread.join();self.sample();ended=time.monotonic_ns()
        final=dict(method='dedicated cgroup v2; product launcher and all inherited tool children; observer/model fixture outside group',available=self.group is not None)
        if self.group:
            try:
                (self.group/'cgroup.kill').write_text('1')
                final.update(cpu=counters((self.group/'cpu.stat').read_text()),memory_peak_bytes=int((self.group/'memory.peak').read_text()),
                    memory_events=counters((self.group/'memory.events').read_text()),pids_events=counters((self.group/'pids.events').read_text()),
                    io_stat=(self.group/'io.stat').read_text(),limits=dict(memory_bytes=3*1024**3,swap_bytes=0,pids=128,cpu_cores=2))
            except OSError as e:self.errors.append(dict(stage='final_cgroup',error=type(e).__name__))
            # Wait for task-owned descendants to settle before removing only our cgroup.
            for attempt in range(100):
                try:
                    self.group.rmdir();break
                except OSError:
                    if attempt==99:self.errors.append(dict(stage='cgroup_cleanup',error='pending_kernel_settlement'))
                    else:time.sleep(.01)
        if self.memory_reader is not None:
            before=resource.getrusage(resource.RUSAGE_CHILDREN)
            try:
                self.memory_reader.stdin.write('finish\n');self.memory_reader.stdin.flush()
                self.memory_reader_self_cpu_seconds=json.loads(self.memory_reader.stdout.readline()).get('cpu_seconds')
                self.memory_reader.stdin.close();self.memory_reader.wait(timeout=5)
                if self.memory_reader.returncode!=0:self.errors.append(dict(stage='memory_reader_exit',error='nonzero'))
            except (OSError,ValueError,subprocess.TimeoutExpired) as error:
                self.errors.append(dict(stage='memory_reader_finish',error=type(error).__name__))
                self.memory_reader.kill();self.memory_reader.wait()
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            self.memory_reader_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
        disk=[s['disk'] for s in self.samples]
        if any(d['errors'] for d in disk):self.errors.append(dict(stage='disk_inventory',error='incomplete'))
        return dict(started_ns=self.started_ns,ended_ns=ended,cgroup=final,
            sampled_peak_pss_bytes=max((s['sampled_pss_bytes'] for s in self.samples if 'sampled_pss_bytes' in s),default=None) if self.group else None,
            sampled_peak_rss_sum_bytes=max((s['sampled_rss_sum_bytes'] for s in self.samples if 'sampled_rss_sum_bytes' in s),default=None) if self.group else None,
            memory_method='sampled PSS/RSS sum and kernel cgroup peak are distinct; cgroup includes accounted file cache',
            disk_initial=self.initial_disk,disk_peak_allocated_bytes=max((s['allocated_bytes'] for s in disk),default=None),
            disk_at_terminal=disk[-1] if disk else None,
            retained_incremental_allocated_bytes=(disk[-1]['allocated_bytes']-self.initial_disk['allocated_bytes']) if disk else None,
            sample_interval_ms=self.interval*1000,observer_thread_cpu_seconds=self.observer_cpu,
            memory_reader_cpu_seconds=self.memory_reader_cpu_seconds,memory_reader_self_cpu_seconds=self.memory_reader_self_cpu_seconds,
            memory_reader_scope='Separate read-only privileged helper outside product cgroup; total child-command CPU includes sudo launcher and reader; reader self CPU overlaps that total',samples=self.samples,errors=self.errors,
            complete=bool(self.group) and not self.errors,
            limitation='Sub-interval process-memory/disk peaks may be missed. No COW shared-block or cross-host service attribution. Post-native-cleanup measurement is a separate stage.')
