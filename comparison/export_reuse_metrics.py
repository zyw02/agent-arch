#!/usr/bin/env python3
"""Recompute historical COST-03 paired metrics without inventing missing resource data."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evaluation/tools'))
from campaign import load_plan, records_from, audit

HORIZONS={'COST-03-S01':1,'COST-03-S02':5,'COST-03-S03':20,'COST-03-S04':5}


def row_from(record,arm):
    accounting=record['reuse_accounting']
    if accounting['usage_synthetic'] is not False:raise ValueError('Real provider usage required')
    names=['baseline'] if arm=='baseline' else ['learning','reuse']
    groups=[accounting['groups'][k] for k in names]
    observed={k:sum(g['known_usage'].get(k,0) for g in groups) for k in ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
    for g in groups:
        u=g['known_usage']
        complete=not any(g.get('missing_counters',{}).get(k,0) for k in ('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'))
        if complete and u.get('prompt_cache_hit_tokens',0)+u.get('prompt_cache_miss_tokens',0)!=u.get('prompt_tokens',0):
            raise ValueError('Cache counters do not partition inclusive input')
    missing=sum(sum(g.get('missing_counters',{}).values()) for g in groups)
    normalized=accounting['normalization'][arm];accepted=normalized['accepted_deliveries']
    total=observed['prompt_tokens']+observed['completion_tokens']
    # Verify against the retained independent host accounting, including learning cost.
    if accepted:
        for category,value in observed.items():
            actual=normalized['known_tokens_per_accepted_delivery'][category]
            if not math.isclose(actual,value/accepted,rel_tol=1e-9):raise ValueError('Retained normalization disagrees with raw group totals')
    return dict(scenario_id=record['scenario_id'],unit=record['unit'],arm=arm,historical_state=record['state'],
        planned_deliveries=HORIZONS[record['scenario_id']],accepted_deliveries=accepted,
        accepted_fraction=accepted/HORIZONS[record['scenario_id']],
        known_input_tokens=observed['prompt_tokens'],known_output_tokens=observed['completion_tokens'],
        known_cache_hit_input=observed['prompt_cache_hit_tokens'],known_cache_miss_input=observed['prompt_cache_miss_tokens'],
        known_total_tokens=total,known_tokens_per_accepted_delivery=total/accepted if accepted else None,
        missing_counter_fields=missing,measurement_status='observed' if not missing else 'partial_known_usage',
        learning_charged_to_reuse=arm=='reuse',provider_requests=sum(g['requests'] for g in groups),
        run_id=record['run_id'],native_summary_sha256=record['native_summary_sha256'],
        source_evidence=record['evidence'][0],actual_charge_usd=None,
        scope='Historical OpenClaw 2026.10.7 agent-written AGENTS guide reuse; not native Workshop self-improvement or DSH comparison')


def plot(rows,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,4,figsize=(13,6),layout='constrained')
    for col,sid in enumerate(HORIZONS):
        selected=[r for r in rows if r['scenario_id']==sid]
        for unit in sorted({r['unit'] for r in selected}):
            pair=sorted((r for r in selected if r['unit']==unit),key=lambda r:r['arm'])
            if len(pair)!=2:raise ValueError('Incomplete paired figure')
            y=[r['known_tokens_per_accepted_delivery'] for r in pair]
            if all(v is not None for v in y):axes[0,col].plot([0,1],y,marker='o',alpha=.65,linewidth=1)
            axes[1,col].plot([0,1],[r['accepted_fraction'] for r in pair],marker='o',alpha=.65,linewidth=1)
        axes[0,col].set_title(sid+'\n'+str(HORIZONS[sid])+' deliveries'+(' / rule update' if sid.endswith('04') else ''))
        for ax in axes[:,col]:ax.set_xticks([0,1],['Baseline','Guide reuse']);ax.grid(axis='y',alpha=.2)
        axes[0,col].set_ylim(bottom=0);axes[1,col].set_ylim(-.05,1.05)
    axes[0,0].set_ylabel('Known input + output tokens\nper accepted delivery')
    axes[1,0].set_ylabel('Accepted / planned deliveries')
    fig.suptitle('Historical OpenClaw 2026.10.7: paired guide-reuse observations (6 units/scenario)\nLearning and failed calls included; cache input counted once; no invoice or cross-product claim',fontsize=11)
    fig.savefig(path,metadata={'Description':'Source: accepted COST-03 provider accounting. Each line is one paired independent unit. Failures retained. This is guide reuse, not native Workshop evaluation.'})
    fig.savefig(path.with_suffix('.png'),dpi=140)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');args=p.parse_args()
    directory=ROOT/'evaluation/campaigns/full-20261026-batched';plan=load_plan(directory/'plan.json');records=records_from(directory/'results')
    audit(plan,records)
    rows=[row_from(r,arm) for r in records if r['scenario_id'] in HORIZONS and r['state'] in {'pass','fail'} for arm in ('baseline','reuse')]
    if len(rows)!=48:raise ValueError('Expected 24 independent paired historical units')
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'guide-reuse-metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=[]
    for sid in HORIZONS:
        for arm in ('baseline','reuse'):
            part=[r for r in rows if r['scenario_id']==sid and r['arm']==arm]
            accepted=sum(r['accepted_deliveries'] for r in part);tokens=sum(r['known_total_tokens'] for r in part)
            summary.append(dict(scenario_id=sid,arm=arm,independent_units=len(part),accepted=accepted,
                planned=sum(r['planned_deliveries'] for r in part),known_tokens=tokens,
                pooled_known_tokens_per_accepted=tokens/accepted if accepted else None,
                missing_counter_fields=sum(r['missing_counter_fields'] for r in part)))
    (args.output/'guide-reuse-metrics-summary.json').write_text(json.dumps(dict(formal_new_experiments=False,source_version='2026.10.7',rows=summary,rule='Pooled cost includes failed work and learning; zero accepted is N/A. S03 incomplete reuse remains visible. No native Workshop or cross-product conclusion.'),indent=2)+'\n')
    if args.plot:plot(rows,args.output/'guide-reuse-paired.svg')
    print(json.dumps(summary))

if __name__=='__main__':main()
