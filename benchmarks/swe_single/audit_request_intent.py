#!/usr/bin/env python3
"""Read-only request-intent audit of an already selected campaign's evidence."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import tarfile

from relay import effective_request


def audit(root, output):
    with (root/'report/all-formal-metrics.csv').open(encoding='utf-8-sig') as stream:
        runs=list(csv.DictReader(stream))
    totals=defaultdict(Counter)
    requests=[]
    checks=[]
    truncations=[]
    for run in runs:
        directory=Path(run['source_result']).parent/'provider'
        ledger=json.loads((directory/'ledger.json').read_text())
        for record in ledger['records']:
            product=run['product']
            if not record.get('forwarded'):
                totals[product]['blocked_'+str(record.get('blocked_reason'))]+=1
                continue
            path=directory/f"{record['request_index']:04d}"
            original=json.loads((path/'request.original.json').read_text())
            old=json.loads((path/'request.effective.json').read_text())
            fixed=effective_request(record['api'],original,65536,'native-aux-v2')
            disabled=((original.get('thinking') or {}).get('type')=='disabled' or
                original.get('reasoning_effort')=='none' or (original.get('reasoning') or {}).get('effort')=='none')
            totals[product]['forwarded']+=1
            totals[product]['native_disabled' if disabled else 'native_not_disabled']+=1
            for field in ('messages','input','instructions','tools','tool_choice'):
                if original.get(field)!=fixed.get(field):
                    checks.append(dict(kind='unexpected_prompt_or_tool_change',product=product,field=field))
            if disabled:
                if fixed.get('thinking',fixed.get('reasoning'))!=original.get('thinking',original.get('reasoning')):
                    checks.append(dict(kind='native_disabled_not_preserved',product=product))
                if (old.get('thinking') or {}).get('type')=='enabled' or (old.get('reasoning') or {}).get('effort')=='high':
                    totals[product]['legacy_forced_disabled_to_high']+=1
            item=dict(product=product,task_id=run['task_id'],repeat=int(run['repeat']),
                request_index=record['request_index'],api=record['api'],
                original_sha256=hashlib.sha256((path/'request.original.json').read_bytes()).hexdigest(),
                native_disabled=disabled,tool_count=len(original.get('tools',[])),
                original_thinking=original.get('thinking'),original_effort=original.get('reasoning_effort',original.get('reasoning')),
                original_output_limit=original.get('max_tokens',original.get('max_output_tokens')),
                v2_output_limit=fixed.get('max_tokens',fixed.get('max_output_tokens')),
                finish_reason=record.get('finish_reason'),terminal=record.get('terminal'),
                final_usage_observed=record.get('final_usage_observed'),source_request=str(path/'request.original.json'))
            requests.append(item)
            if record.get('finish_reason')=='length':
                truncations.append({**item,'observed_usage':record.get('normalized_usage')})
    sdk_errors=[]
    summary=json.loads((root/'report/summary.json').read_text())
    for failed in summary['failed_attempts']:
        if failed['product']!='openclaw57_patched':
            continue
        archive=Path(failed['source_result']).parent/'native-state.tar.gz'
        matches=set()
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if not member.name.startswith('agentloop-debug'):
                    continue
                for line in tf.extractfile(member):
                    if b'raw msg' not in line or b'is_error' not in line:
                        continue
                    try:
                        entry=json.loads(line)
                        text=next(v for v in entry.values() if isinstance(v,str) and '[agentloop] raw msg =' in v)
                        event=json.loads(text.split('[agentloop] raw msg =',1)[1])
                    except (ValueError,StopIteration):
                        continue
                    if event.get('type')=='result' and event.get('is_error') and event.get('result')=='Prompt is too long':
                        matches.add('sdk_local_prompt_too_long')
        sdk_errors.append(dict(product=failed['product'],task_id=failed['task_id'],repeat=failed['repeat'],
            errors=sorted(matches),interpretation='Native SDK terminal diagnosis; compact rewrite may contribute but causal recovery must be verified'))
    with (root/'audit/runner-resources.csv').open(encoding='utf-8-sig') as stream:
        cpu_models=sorted({r['cpu_model'] for r in csv.DictReader(stream)})
    result=dict(formal_attempts=len(runs),forwarded_requests=len(requests),totals=dict(totals),
        v2_replay_failures=checks,v2_replay_passed=not checks,length_terminations=truncations,
        native_sdk_errors=sdk_errors,cpu_models=cpu_models,
        historical_ranking_status='provisional: native auxiliary intent was rewritten, CPU hardware differed, and request/output budgets affected execution',
        causal_limit='Offline replay proves request construction only, not that every framework/task failure is repaired',requests=requests)
    output.mkdir(parents=True,exist_ok=True)
    (output/'request-intent-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['requests','length_terminations']},ensure_ascii=False))
    if checks:
        raise ValueError('Corrected request replay did not preserve native intent')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    audit(args.evidence_root,args.output)
