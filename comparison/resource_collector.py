#!/usr/bin/env python3
"""Owned cgroup + process-memory + task-path collector for hosted native arms."""
import os
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
        self.stop_event=threading.Event();self.observer_cpu=0
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
        self.thread=threading.Thread(target=self.sample_loop,daemon=True);self.thread.start()

    def command(self,command):
        if self.group is None:return command
        import sys
        return [sys.executable,str(Path(__file__).with_name('resource_launcher.py')),str(self.group),*command]

    def sample(self):
        row=dict(monotonic_ns=time.monotonic_ns(),disk=disk_inventory(self.paths))
        if self.group:
            try:
                pids=(self.group/'cgroup.procs').read_text().split();pss=rss=0;visible=0
                for pid in pids:
                    try:
                        values=counters((Path('/proc')/pid/'smaps_rollup').read_text().replace(' kB',''))
                        pss+=values.get('Pss',0)*1024;rss+=values.get('Rss',0)*1024;visible+=1
                    except FileNotFoundError:continue
                    except OSError:self.errors.append(dict(stage='smaps',error='unobservable'))
                row.update(processes=len(pids),memory_processes_observed=visible,sampled_pss_bytes=pss,sampled_rss_sum_bytes=rss,
                    cgroup_memory_current_bytes=int((self.group/'memory.current').read_text()),cpu=counters((self.group/'cpu.stat').read_text()))
            except OSError as e:self.errors.append(dict(stage='sample',error=type(e).__name__))
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
        disk=[s['disk'] for s in self.samples]
        if any(d['errors'] for d in disk):self.errors.append(dict(stage='disk_inventory',error='incomplete'))
        return dict(started_ns=self.started_ns,ended_ns=ended,cgroup=final,
            sampled_peak_pss_bytes=max((s.get('sampled_pss_bytes',0) for s in self.samples),default=0) if self.group else None,
            sampled_peak_rss_sum_bytes=max((s.get('sampled_rss_sum_bytes',0) for s in self.samples),default=0) if self.group else None,
            memory_method='sampled PSS/RSS sum and kernel cgroup peak are distinct; cgroup includes accounted file cache',
            disk_initial=self.initial_disk,disk_peak_allocated_bytes=max((s['allocated_bytes'] for s in disk),default=None),
            disk_at_terminal=disk[-1] if disk else None,
            retained_incremental_allocated_bytes=(disk[-1]['allocated_bytes']-self.initial_disk['allocated_bytes']) if disk else None,
            sample_interval_ms=self.interval*1000,observer_thread_cpu_seconds=self.observer_cpu,samples=self.samples,errors=self.errors,
            complete=bool(self.group) and not self.errors,
            limitation='Sub-interval process-memory/disk peaks may be missed. No COW shared-block or cross-host service attribution. Post-native-cleanup measurement is a separate stage.')
