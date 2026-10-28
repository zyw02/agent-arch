#!/usr/bin/env python3
"""Join only the task-owned experiment cgroup, then replace this process."""
import os
from pathlib import Path
import sys

group=Path(sys.argv[1])
base=Path(os.environ.get('AGENT_ARCH_CGROUP_ROOT','/sys/fs/cgroup/system.slice'))
if group.parent!=base or not group.name.startswith('agent-arch-probe-'):
    raise SystemExit('Expected a task-owned experiment cgroup')
(group/'cgroup.procs').write_text(str(os.getpid()))
os.execvpe(sys.argv[2],sys.argv[2:],os.environ)
