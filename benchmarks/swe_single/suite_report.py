#!/usr/bin/env python3
"""Collect 72 attempt records and six independent idle-memory summaries."""
import argparse
import csv
import json
import os
from pathlib import Path
import statistics


def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); args = p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    rows = []
    shards = []
    for path in sorted(args.input.rglob('shard/shard-summary.json')):
        shard = json.loads(path.read_text()); shards.append(shard)
        for file in sorted(path.parent.glob('segments/block-*/runs.csv')):
            for row in csv.DictReader(file.open(encoding='utf-8-sig')):
                if row['smoke']=='False':
                    rows.append(dict(task_id=shard['task_id'], **row))
    identities = {(r['task_id'],r['product'],r['run_id']) for r in rows}
    if len(identities)!=len(rows):
        raise ValueError('Duplicate attempt artifacts; refusing to double count')
    idle = [json.loads(p.read_text()) for p in sorted(args.input.rglob('idle/summary.json'))]
    with (args.output/'all-formal-runs.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        if rows:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    complete = len(rows)==72 and len(shards)==24 and all(s['complete'] for s in shards)
    idle_complete = len(idle)==6 and len({s['product'] for s in idle})==6 and all(s['all_valid'] for s in idle)
    status=dict(formal_expected=72,formal_completed=len(rows),formal_complete=complete,
                idle_products_expected=6,idle_products_received=len(idle),idle_complete=idle_complete,
                shards=shards,idle=idle,
                aggregation='All three attempts per task; timeouts retained; no trimming; tasks equally weighted',
                task_memory='process-tree samples during execution, not idle; container peak retained as diagnostics only')
    (args.output/'suite-status.json').write_text(json.dumps(status,indent=2)+'\n')
    lines=['# Six harnesses / four tasks / three repeats','',
           f'Formal records: {len(rows)}/72. Complete: {complete}. Initial idle complete: {idle_complete}.','',
           'Task timeout 1800 seconds; 2 CPU / 8 GiB; fresh state every attempt. AIOS uses verified AgentLoop.','',
           '| Product | Attempts | Success | Mean latency s | Mean fee USD | Mean total tokens |',
           '|---|---:|---:|---:|---:|---:|']
    for product in ['openclaw57_patched','codex','dsh','claude','hermes','openclaw']:
        group=[r for r in rows if r['product']==product]
        def mean(k):
            return statistics.mean(float(r[k]) for r in group) if group and all(r.get(k) not in ('',None) for r in group) else None
        latency,fee=mean('wall_seconds'),mean('peak_estimated_usd')
        inp,out=mean('input_total'),mean('output_total')
        fmt=lambda v:'unknown' if v is None else f'{v:.6f}'
        lines.append(f"| {product} | {len(group)}/12 | {sum(r['resolved']=='True' for r in group)} | {fmt(latency)} | {fmt(fee)} | {fmt(inp+out if inp is not None and out is not None else None)} |")
    lines+=['','## Initial idle; no task or inference','',
            '| Product | Valid repeats | Mean RSS MiB | Mean PSS MiB |','|---|---:|---:|---:|']
    for summary in idle:
        lines.append('| '+summary['product']+' | '+str(sum(r['valid'] for r in summary['results']))+
                     ' | '+str(summary.get('mean_idle_rss_mib','unknown'))+
                     ' | '+str(summary.get('mean_idle_pss_mib','unknown'))+' |')
    lines+=['','Missing measurements remain unknown. Incomplete task coverage is not an overall ranking.',
            'Idle uses native UIs/servers; AIOS uses deployment Node memory flags. Shared-library PSS and startup shape differ from prior co-resident local measurements.','']
    report='\n'.join(lines); (args.output/'report.md').write_text(report)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:stream.write(report)
    print(json.dumps({k:v for k,v in status.items() if k not in ('shards','idle')}),flush=True)
    if not complete or not idle_complete:
        raise ValueError('Incomplete campaign; retained partial evidence, no complete ranking admitted')


if __name__=='__main__':main()
