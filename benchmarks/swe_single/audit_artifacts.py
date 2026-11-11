#!/usr/bin/env python3
"""Refuse publication if the provider credential occurs in any retained bytes."""
import argparse
import json
import os
from pathlib import Path
import tarfile


def contains(stream, needle):
    tail = b''
    while block := stream.read(1024**2):
        value = tail + block
        if needle in value:
            return True
        tail = value[-len(needle):]
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    args = p.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    needle = os.environ.get('DEEPSEEK_API_KEY', '').encode()
    if len(needle) < 12:
        raise ValueError('Credential audit requires the configured secret')
    count = archive_members = 0
    for path in args.root.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as stream:
            if contains(stream, needle):
                raise ValueError('Credential found in retained artifact; publication refused')
        count += 1
        if path.name.endswith('.tar.gz'):
            with tarfile.open(path) as tf:
                for member in tf:
                    if member.isfile():
                        archive_members += 1
                        with tf.extractfile(member) as stream:
                            if contains(stream, needle):
                                raise ValueError('Credential found in native archive; publication refused')
    (args.root / 'artifact-audit.json').write_text(json.dumps(dict(passed=True, files=count,
        archive_members=archive_members, real_credential_present=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
