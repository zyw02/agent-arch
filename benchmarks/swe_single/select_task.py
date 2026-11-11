#!/usr/bin/env python3
"""Freeze one human-verified task before observing any candidate harness outcomes."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
REVISION = 'c104f840cc67f8b6eec6f759ebc8b2693d585d4a'
INSTANCE = 'pytest-dev__pytest-7490'


def main():
    # The immutable parquet, rather than a moving datasets-server row, is the source.
    import pyarrow.parquet as pq
    import io
    url = f'https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/{REVISION}/data/test-00000-of-00001.parquet'
    raw = urllib.request.urlopen(url, timeout=90).read()
    rows = pq.read_table(io.BytesIO(raw)).to_pylist()
    row = next(r for r in rows if r['instance_id'] == INSTANCE)
    keep = ('repo', 'instance_id', 'base_commit', 'patch', 'test_patch',
            'problem_statement', 'FAIL_TO_PASS', 'PASS_TO_PASS', 'version',
            'difficulty', 'environment_setup_commit', 'created_at')
    task = {k: row[k] for k in keep}
    for k in ('FAIL_TO_PASS', 'PASS_TO_PASS'):
        if isinstance(task[k], str):
            task[k] = json.loads(task[k])
    task['provenance'] = dict(dataset='princeton-nlp/SWE-bench_Verified',
                             revision=REVISION, parquet_url=url,
                             parquet_sha256=hashlib.sha256(raw).hexdigest(),
                             source_row_sha256=hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest())
    (ROOT / 'task.json').write_text(json.dumps(task, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(instance=INSTANCE, difficulty=task['difficulty'],
                         fail_to_pass=len(task['FAIL_TO_PASS']),
                         pass_to_pass=len(task['PASS_TO_PASS']))))


if __name__ == '__main__':
    main()
