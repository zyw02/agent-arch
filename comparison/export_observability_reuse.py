#!/usr/bin/env python3
"""Extract exact accepted OBS-02 counters on hosted workers; execute no product/model."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evaluation/tools'))
from campaign import audit,load_plan,records_from

LABELS={'OBS-02-S01':'Brief collector fault','OBS-02-S02':'Long collector fault',
        'OBS-02-S03':'Publisher killed/restarted','OBS-02-S04':'4096-event burst + fault'}
CHECKS={
    'task_during_fault':'task-effect-independent-of-collector-failure',
    'task_after_restoration':'native-task-recovers-after-collector-restoration',
    'publication_after_restoration':'native-publication-recovers-after-collector-restoration',
    'local_offered_ids_retained':'native-local-offered-event-log-retains-the-offered-workload',
    'all_offered_ids_exported':'all-offered-native-diagnostic-events-eventually-exported',
    'no_duplicate_successful_deliveries':'no-duplicate-successful-collector-deliveries',
}


def normalized_row(observation,record,asset):
    """Require full event partitions and preserve original accepted assertions."""
    if (observation['scenario_id'],observation['unit'])!=(record['scenario_id'],record['unit']):
        raise ValueError('Accepted observation identity mismatch')
    if observation['state']!=record['state'] or observation['assertions']!=record['assertions']:
        raise ValueError('Original accepted judgments differ')
    m=observation['metadata'];offered=m['offered_unique_events'];expected=set(range(offered))
    if m['independent_offered_workload_receipt']['collector_offered_count']!=offered:
        raise ValueError('Independent offered workload differs')
    missing=set(m['missing_event_indices']);local_missing=set(m['native_local_missing_event_indices'])
    local=set(m['native_local_event_indices']);delivered={int(k):v for k,v in m['successful_deliveries_by_index'].items()}
    if (len(missing)!=m['missing_event_count'] or missing & set(delivered) or
        missing | set(delivered)!=expected or local & local_missing or local | local_missing!=expected or
        len(local_missing)!=len(m['native_local_missing_event_indices']) or len(missing)!=len(m['missing_event_indices'])):
        raise ValueError('Full native event partition is inconsistent')
    duplicate=sum(max(0,n-1) for n in delivered.values())
    if duplicate!=m['duplicate_successful_deliveries']:raise ValueError('Duplicate accounting differs')
    verdicts={a['name']:a['verdict'] for a in record['assertions']}
    flags={k:verdicts[name]=='pass' for k,name in CHECKS.items()}
    if flags['all_offered_ids_exported']!=(not missing) or flags['local_offered_ids_retained']!=(not local_missing):
        raise ValueError('Counts contradict accepted retention assertions')
    return dict(scenario_id=record['scenario_id'],unit=record['unit'],mode=m['mode'],historical_state=record['state'],
        offered_unique_events=offered,remote_delivered_unique_events=len(delivered),remote_missing_events=len(missing),
        remote_missing_fraction=len(missing)/offered,local_missing_unique_events=len(local_missing),local_missing_fraction=len(local_missing)/offered,
        duplicate_successful_deliveries=duplicate,**flags,
        sdk_default_queue_capacity=m['sdk_default_queue_capacity'],sdk_default_batch_capacity=m['sdk_default_batch_capacity'],
        native_overflow_log_signal=m['native_overflow_log_signal'],
        run_id=record['run_id'],controller_commit=record['controller_commit'],target_version=record['target_version'],
        native_summary_sha256=record['native_summary_sha256'],source_zip_sha256=asset['source_zip_sha256'],source_url=asset['download_url'],
        count_scope='Exact target ID set, after declared collector recovery wait and native shutdown; successful recovery probes are separate events',
        claim_scope='Historical official diagnostics-otel export with public diagnostic reference producer; no claim of durable-spool contract, internal event-bus loss or cross-product ranking')


def extract(archive,records,asset):
    if hashlib.sha256(archive).hexdigest()!=asset['source_zip_sha256']:raise ValueError('Permanent ZIP digest mismatch')
    expected={r['native_summary_sha256'] for r in records};found={};rows=[]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if sum(m.file_size for m in z.infolist())>64*1024**2:raise ValueError('Expanded archive bound exceeded')
        for info in z.infolist():
            if not info.filename.endswith('summary.json'):continue
            if info.file_size>8*1024**2:raise ValueError('Summary exceeds evidence bound')
            raw=z.read(info);digest=hashlib.sha256(raw).hexdigest()
            if digest not in expected:continue
            if digest in found:raise ValueError('Duplicate accepted summary')
            found[digest]=json.loads(raw)
    if set(found)!=expected:raise ValueError('Accepted native summary missing')
    for record in records:
        candidates=[o for o in found[record['native_summary_sha256']]['observations']
                    if (o.get('scenario_id'),o.get('unit'))==(record['scenario_id'],record['unit'])]
        if len(candidates)!=1:raise ValueError('Ambiguous accepted native observation')
        rows.append(normalized_row(candidates[0],record,asset))
    return rows


def plot(rows,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
    for axis,key,title in zip(axes,['remote_missing_fraction','local_missing_unique_events','publication_after_restoration'],
                              ['Missing remote target IDs / offered','Missing local target IDs (count)','Fresh publication after restoration']):
        for i,sid in enumerate(LABELS):
            part=sorted((r for r in rows if r['scenario_id']==sid),key=lambda r:r['unit'])
            for j,row in enumerate(part):axis.scatter(i+(j-1)*.09,float(row[key]),marker=['o','s','^'][j],s=48,label='unit '+str(row['unit']) if i==0 else None)
        axis.set_xticks(range(4),['Brief','Long','Restart','Burst']);axis.grid(axis='y',alpha=.2);axis.set_title(title,fontsize=10)
        if key=='local_missing_unique_events':
            top=max(r[key] for r in rows);axis.set_ylim(-.08,max(1,top)*1.15);axis.set_yticks(range(max(1,top)+1))
        else:axis.set_ylim(-.08,1.08);axis.set_yticks([0,.5,1])
    axes[0].legend(fontsize=8)
    fig.suptitle('Historical OpenClaw 2026.10.7: accepted OBS-02 fault observations (3 units/condition)\nAll task effects and post-restoration task checks passed; original failed retention assertions retained. No new native execution.',fontsize=11)
    fig.savefig(output/'observability-reuse.svg');fig.savefig(output/'observability-reuse.png',dpi=145);plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Read original native archives only on disposable hosted workers')
    base=ROOT/'evaluation/campaigns/full-20261026-batched';records=records_from(base/'results');audit(load_plan(base/'plan.json'),records)
    records=[r for r in records if r['scenario_id'] in LABELS and r['state'] in {'pass','fail'}]
    if len(records)!=12:raise ValueError('Expected all twelve accepted observations')
    assets=json.loads((base/'permanent-evidence.json').read_text())['assets'];rows=[]
    for key in sorted({str(r['run_id'])+'/'+str(r['hosted_artifact_id']) for r in records}):
        selected=[r for r in records if str(r['run_id'])+'/'+str(r['hosted_artifact_id'])==key];asset=assets[key]
        req=urllib.request.Request(asset['download_url'],headers={'User-Agent':'agent-arch-observability-reuse'})
        with urllib.request.urlopen(req,timeout=60) as response:raw=response.read(8*1024**2+1)
        if len(raw)!=asset['zip_bytes'] or len(raw)>8*1024**2:raise ValueError('Archive size differs')
        rows.extend(extract(raw,selected,asset))
    rows.sort(key=lambda r:(r['scenario_id'],r['unit']));args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'observability-reuse-metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    summary=[]
    for sid in LABELS:
        part=[r for r in rows if r['scenario_id']==sid]
        summary.append(dict(scenario_id=sid,label=LABELS[sid],independent_units=len(part),
            offered=sum(r['offered_unique_events'] for r in part),remote_missing=sum(r['remote_missing_events'] for r in part),
            local_missing=sum(r['local_missing_unique_events'] for r in part),
            **{key+'_passed':sum(r[key] for r in part) for key in CHECKS}))
    (args.output/'observability-reuse-summary.json').write_text(json.dumps(dict(formal_new_experiments=False,run_id=os.environ.get('GITHUB_RUN_ID'),
        controller_commit=os.environ.get('GITHUB_SHA'),source_version='2026.10.7',rows=summary,paid_model_calls=0,
        interpretation='Remote target loss, local offered-ID retention and fresh publication/task recovery have different scopes. The reference producer uses public diagnostic ingestion; no durable-spool guarantee is presumed and no broad native event-bus claim follows.'),indent=2)+'\n')
    if args.plot:plot(rows,args.output)
    print(json.dumps(summary))

if __name__=='__main__':main()
