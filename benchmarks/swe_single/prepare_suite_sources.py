#!/usr/bin/env python3
"""Prepare only frozen base snapshots; no Git history, gold or hidden patch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    selection = json.loads((HERE/'suite-selection.json').read_text())
    records = []
    for entry in selection['tasks']:
        path = HERE/entry['task_file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['task_sha256']:
            raise ValueError('Task checksum mismatch')
        task = json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp)/'checkout'
            subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
            subprocess.run(['git', '-C', str(checkout), 'fetch', '--depth', '1',
                            'https://github.com/'+task['repo']+'.git', task['base_commit']], check=True)
            archive = Path(temp)/'base.tar'
            subprocess.run(['git', '-C', str(checkout), 'archive', '-o', str(archive), task['base_commit']], check=True)
            target = args.output/task['instance_id']; target.mkdir()
            with tarfile.open(archive) as tf:
                tf.extractall(target, filter='data')
            records.append(dict(instance_id=task['instance_id'], base_commit=task['base_commit'],
                                archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                hidden_patch_exposed=False, gold_patch_exposed=False, git_history_exposed=False))
    (args.output/'source-provenance.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__ == '__main__':
    main()
