#!/usr/bin/env python3
"""Read memory accounting only for members of one task-owned cgroup."""
import json
import os
from pathlib import Path
import resource
import sys


def sample(group,proc_root=Path('/proc')):
    pids=(group/'cgroup.procs').read_text().split();pss=rss=0;observed=0;errors=[]
    for pid in pids:
        try:
            lines=(proc_root/pid/'smaps_rollup').read_text().splitlines()
            values={v[0].rstrip(':'):int(v[1]) for line in lines if len(v:=line.split())>=2 and v[1].isdigit()}
            pss+=values.get('Pss',0)*1024;rss+=values.get('Rss',0)*1024;observed+=1
        except (FileNotFoundError,ProcessLookupError):continue
        except OSError as error:errors.append(dict(stage='smaps',error=type(error).__name__,errno=error.errno,pid=int(pid)))
    return dict(processes=len(pids),memory_processes_observed=observed,sampled_pss_bytes=pss,sampled_rss_sum_bytes=rss,errors=errors)


def main():
    group=Path(sys.argv[1]);base=Path(os.environ.get('AGENT_ARCH_CGROUP_ROOT','/sys/fs/cgroup/system.slice'))
    if group.parent!=base or not group.name.startswith('agent-arch-probe-') or base.parent!=Path('/sys/fs/cgroup') and base!=Path('/sys/fs/cgroup/system.slice'):
        raise SystemExit('Expected an explicitly owned experiment cgroup')
    for line in sys.stdin:
        if line.strip()=='sample':
            try:result=sample(group)
            except OSError as error:result=dict(errors=[dict(stage='memory_reader',error=type(error).__name__,errno=error.errno)])
        elif line.strip()=='finish':
            usage=resource.getrusage(resource.RUSAGE_SELF)
            print(json.dumps(dict(cpu_seconds=usage.ru_utime+usage.ru_stime)),flush=True);return
        else:raise SystemExit('Only sample and finish commands are supported')
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
