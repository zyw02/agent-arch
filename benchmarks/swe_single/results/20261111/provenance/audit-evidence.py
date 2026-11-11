#!/usr/bin/env python3
import collections
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / 'evidence/campaign'
summary = json.loads((C / 'summary.json').read_text())
validated = json.loads((C / 'validated-accounting.json').read_text())['runs']
image = json.loads((C / 'environment.json').read_text())['image_id']
formal = [r for r in summary['results'] if not r['smoke']]
assert len(formal) == 15
assert collections.Counter(r['product'] for r in formal) == dict(dsh=3,openclaw=3,hermes=3,codex=3,claude=3)
assert json.loads((C / 'controls/acceptance.json').read_text())['passed']
models = collections.Counter()
blocked = collections.Counter()
prompt_hashes = set()
request_count = stream_count = nonstream_count = 0
rows = []
for r in summary['results']:
    folder = C / 'runs' / r['run_id']
    inspection = json.loads((folder / 'container.json').read_text())
    assert inspection['Image'] == image
    assert inspection['HostConfig']['Memory'] == 4294967296
    assert inspection['HostConfig']['NanoCpus'] == 2000000000
    assert inspection['HostConfig']['ReadonlyRootfs']
    assert inspection['State']['Paused'] and inspection['State']['Running']
    st = r['storage']
    assert st['cgroup']['available'] and st['cgroup']['memory_peak'] > 0
    assert st['cgroup']['cpu']['usage_usec'] > 0
    assert st['cgroup']['memory_events']['oom_kill'] == 0
    assert all(v['exists'] and not v['scan_errors'] for v in st['final'].values())
    assert not st['storage_limit_exceeded']
    v = validated[r['run_id']]['summary']
    assert v['usage_complete'] and v['usage_unknown_attempts'] == 0
    if not r['smoke']:
        assert r['resolved'] and r['native_execution_ok'] and not r['termination']
        assert r['patch']['policy_passed'] and not r['patch']['forbidden_paths']
        assert hashlib.sha256((folder/'patch.diff').read_bytes()).hexdigest() == r['patch']['patch_sha256']
        assert all(c['path'].startswith('src/') and c['allowed'] for c in r['patch']['changes'])
        assert r['grade']['FAIL_TO_PASS']['passed'] == 2
        assert r['grade']['PASS_TO_PASS']['passed'] == 78
        assert r['grade']['full_test_file_passed']
        assert len(r['grade']['test_statuses']) == 81
        assert not any(x in ('FAILED','ERROR') for x in r['grade']['test_statuses'].values())
        with tarfile.open(folder/'native-state.tar.gz') as archive:
            prompt_hashes.add(hashlib.sha256(archive.extractfile('prompt.txt').read()).hexdigest())
    else:
        assert r['calibration_passed']
    ledger = json.loads((folder/'provider/ledger.json').read_text())
    for q in ledger['records']:
        if not q['forwarded']:
            blocked[(r['product'],q['path'],q.get('blocked_reason'))] += 1
            continue
        request_count += 1
        directory = folder/'provider'/f"{q['request_index']:04d}"
        original = (directory/'request.original.json').read_bytes()
        effective = (directory/'request.effective.json').read_bytes()
        assert hashlib.sha256(original).hexdigest() == q['original_sha256']
        assert hashlib.sha256(effective).hexdigest() == q['effective_sha256']
        body = json.loads(effective)
        assert body['model'] == 'deepseek-flash'
        models[q.get('response_model')] += 1
        if q['api'] == 'messages':
            assert body['thinking'] == {'type':'enabled'}
            assert body['output_config']['effort'] == 'high' and body['max_tokens'] == 16384
            allowed = {'thinking','output_config','max_tokens'}
        elif q['api'] == 'chat':
            assert body['thinking'] == {'type':'enabled'}
            assert body['reasoning_effort'] == 'high' and body['max_tokens'] == 16384
            allowed = {'thinking','reasoning_effort','max_tokens','max_completion_tokens','stream_options'}
        else:
            assert body['reasoning']['effort'] == 'high' and body['max_output_tokens'] == 16384
            allowed = {'reasoning','max_output_tokens'}
        old = json.loads(original)
        assert {k:x for k,x in old.items() if k not in allowed} == {k:x for k,x in body.items() if k not in allowed}
        raw = (directory/'response.raw').read_bytes()
        assert len(raw) == q['response_bytes']
        if q['stream']:
            stream_count += 1
            parsed=[]
            for line in raw.splitlines():
                if line.startswith(b'data:'):
                    data=line[5:].strip()
                    if data and data != b'[DONE]': parsed.append(json.loads(data))
            retained=[json.loads(line)['event'] for line in (directory/'events.jsonl').read_text().splitlines()]
            assert parsed == retained
        else:
            nonstream_count += 1
            json.loads(raw)
    rows.append(dict(run_id=r['run_id'],formal=not r['smoke'],passed=True,provider_attempts=v['provider_attempts']))
assert len(prompt_hashes) == 1
result=dict(passed=True,formal_runs=15,calibration_runs=5,formal_provider_attempts=sum(validated[r['run_id']]['summary']['provider_attempts'] for r in formal),
    all_provider_attempts=request_count,stream_attempts=stream_count,nonstream_attempts=nonstream_count,
    image_id=image,formal_prompt_sha256=next(iter(prompt_hashes)),response_models=dict(models),
    blocked_requests=[dict(product=k[0],path=k[1],reason=k[2],count=n) for k,n in blocked.items()],runs=rows,
    checks=['artifact request hashes','raw SSE equals retained event sequence','common model/reasoning/output controls','native tools/messages unchanged by relay',
            'same common image and CPU/memory limits','identical formal issue prompts','15 accepted source policies and patch hashes',
            '2 F2P plus 78 P2P and 81-case affected file','all final storage scans without errors','cgroup availability and no OOM kills','complete final provider usage for all admitted attempts'],
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(ROOT/'evidence-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('runs','checks')},indent=2))
