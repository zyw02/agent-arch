#!/usr/bin/env python3
"""Join only the task-owned experiment cgroup; drop launcher privilege before exec."""
import os
from pathlib import Path
import pwd
import sys

group=Path(sys.argv[1])
base=Path(os.environ.get('AGENT_ARCH_CGROUP_ROOT','/sys/fs/cgroup/system.slice'))
if group.parent!=base or not group.name.startswith('agent-arch-probe-'):
    raise SystemExit('Expected a task-owned experiment cgroup')
(group/'cgroup.procs').write_text(str(os.getpid()))
uid,gid=int(sys.argv[2]),int(sys.argv[3])
if os.geteuid()==0:
    os.initgroups(pwd.getpwuid(uid).pw_name,gid)
    os.setgid(gid);os.setuid(uid)
if os.getuid()!=uid or os.getgid()!=gid:raise SystemExit('Launcher identity mismatch')
os.execvpe(sys.argv[4],sys.argv[4:],os.environ)
