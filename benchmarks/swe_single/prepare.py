#!/usr/bin/env python3
"""Create a gold-free Docker context and record its source provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    task = json.loads((HERE / 'task.json').read_text())
    checkout = out / 'checkout'
    subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
    subprocess.run(['git', '-C', str(checkout), 'fetch', '--depth', '1',
                    'https://github.com/' + task['repo'] + '.git', task['base_commit']], check=True)
    archive = out / 'source.tar'
    subprocess.run(['git', '-C', str(checkout), 'archive', '--format=tar',
                    '-o', str(archive), task['base_commit']], check=True)
    context = out / 'context'
    source = context / 'task-source'
    source.mkdir(parents=True)
    with tarfile.open(archive) as tf:
        tf.extractall(source, filter='data')
    for name in ('Dockerfile', 'agent_entry.py'):
        shutil.copyfile(HERE / name, context / name)
    (out / 'preparation.json').write_text(json.dumps(dict(
        instance_id=task['instance_id'], base_commit=task['base_commit'],
        source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        dataset=task['provenance'], hidden_test_patch_exposed=False,
        gold_patch_exposed=False, git_history_exposed=False), indent=2) + '\n')
    shutil.rmtree(checkout)
    archive.unlink()


if __name__ == '__main__':
    main()
