#!/usr/bin/env python3
"""Recompute fixed-load platform resource rows from retained native evidence."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from context_skill_probe import request_text
from platform_api_probe import MARKER
from platform_fault_probe import history_facts
from platform_resource_probe import integrate_memory


def task_ack(product,task):
    result=task.get('native_result',{});marker=task['marker']
    if product=='DSH':
        return task.get('prompt_receipt',{}).get('accepted') is True and result.get('reason')=='idle' and history_facts(product,dict(events=result.get('output',{})),marker)['assistant_ack']
    choices=result.get('choices',[])
    return task.get('status')==200 and len(choices)==1 and choices[0].get('message',{}).get('role')=='assistant' and choices[0]['message'].get('content')=='PLATFORM_ACK:'+marker


def peak_active(events):
    changes=sorted([(e['received_ns'],1) for e in events]+[(e['released_ns'],-1) for e in events],key=lambda e:(e[0],e[1]));active=peak=0
    for _,delta in changes:active+=delta;peak=max(peak,active)
    return peak


def summarize(report):
    rows=[]
    for arm in report['results']:
        p=arm['product'];phase=arm.get('phase_metrics',{});resources=arm.get('resources',{});tasks=arm['tasks']
        exact=[task_ack(p,t) for t in tasks]
        if exact!=[t['accepted'] for t in tasks]:raise ValueError('Original native ACK judgment does not equal exact assistant field')
        expected_tasks=0 if arm['condition']=='idle' else (4 if arm['condition'].startswith('four_') else 1)
        if len(tasks)!=expected_tasks:raise ValueError('Native task cardinality incomplete')
        identities=[t.get('session_key') if p=='OpenClaw' else t['session_id'] for t in tasks]
        if len(set(identities))!=len(tasks):raise ValueError('Distinct native sessions were not retained')
        for task,identity in zip(tasks,identities):
            reached=[e for e in arm['fixture_ledger'] if not e['title'] and task['marker'] in request_text(e['request'])]
            if len(reached)!=1 or any(other['marker'] in request_text(e['request']) for e in reached for other in tasks if other is not task) or (p=='OpenClaw' and not any('session='+str(identity)+' |' in request_text(e['request']) for e in reached)):
                raise ValueError('Actual provider/native session binding failed')
        if 'priming_task' in arm and not task_ack(p,arm['priming_task']):raise ValueError('Native priming control failed')
        start=arm.get('phase_start',{}).get('after_read_ns');end=arm.get('phase_end',{}).get('before_read_ns')
        if start is not None and end is not None:
            integral=integrate_memory(resources['samples'],start,end,'sampled_rss_sum_bytes')
            if integral!=phase.get('integrated_rss_byte_seconds'):raise ValueError('Retained resident-memory integral changed')
            cpu=(arm['phase_end']['cpu']['usage_usec']-arm['phase_start']['cpu']['usage_usec'])/1e6
            if cpu!=phase['cpu_seconds']:raise ValueError('Retained phase CPU changed')
        markers={t['marker'] for t in tasks}
        events=[e for e in arm['fixture_ledger'] if not e['title'] and MARKER.findall(request_text(e['request']))[-1:] and MARKER.findall(request_text(e['request']))[-1] in markers]
        elapsed=phase.get('elapsed_ms',0)/1000
        sample_times=[s['monotonic_ns'] for s in resources.get('samples',[]) if start is not None and end is not None and start<=s['monotonic_ns']<=end and 'sampled_rss_sum_bytes' in s]
        gaps=[(b-a)/1e6 for a,b in zip(sample_times,sample_times[1:])]
        row=dict(product=p,condition=arm['condition'],block=arm['block'],phase=report['phase'],accepted_tasks=sum(exact),offered_tasks=len(tasks),valid=arm['valid'],
            startup_seconds=arm.get('startup_ms',0)/1000,full_arm_seconds=arm['elapsed_ms']/1000,task_phase_seconds=elapsed,
            native_phase_cpu_seconds=phase.get('cpu_seconds'),native_lifecycle_cpu_seconds=resources.get('cgroup',{}).get('cpu',{}).get('usage_usec',0)/1e6,
            native_phase_rss_mib_seconds=phase.get('integrated_rss_byte_seconds')/2**20 if phase.get('integrated_rss_byte_seconds') is not None else None,
            native_phase_mean_rss_mib=phase['integrated_rss_byte_seconds']/2**20/elapsed if elapsed and phase.get('integrated_rss_byte_seconds') is not None else None,
            native_phase_peak_pss_mib=phase['sampled_peak_pss_bytes']/2**20 if phase.get('sampled_peak_pss_bytes') is not None else None,
            native_lifecycle_peak_pss_mib=resources['sampled_peak_pss_bytes']/2**20 if resources.get('sampled_peak_pss_bytes') is not None else None,
            phase_memory_samples=phase.get('memory_samples_within_phase'),native_processes_at_ready=len(arm.get('startup_process_map',[])),native_processes_at_task_end=len(arm.get('phase_end',{}).get('process_map',[])),
            median_observed_sample_gap_ms=statistics.median(gaps) if gaps else None,max_observed_sample_gap_ms=max(gaps,default=None),
            task_model_requests=len(events),max_simultaneous_task_model_requests=peak_active(events),
            provider_task_requests_including_priming=sum(not e['title'] for e in arm['fixture_ledger']),auxiliary_title_requests=sum(e['title'] for e in arm['fixture_ledger']),
            observer_parent_cpu_seconds=arm.get('observer_parent_cpu_seconds'),memory_reader_cpu_seconds=resources.get('memory_reader_cpu_seconds'),resources_complete=resources.get('complete',False),
            owned_disk_peak_mib=resources.get('disk_peak_allocated_bytes',0)/2**20,owned_disk_at_terminal_mib=resources.get('disk_at_terminal',{}).get('allocated_bytes',0)/2**20)
        row['observer_total_cpu_seconds']=sum(row[k] for k in ('observer_parent_cpu_seconds','memory_reader_cpu_seconds')) if all(row[k] is not None for k in ('observer_parent_cpu_seconds','memory_reader_cpu_seconds')) else None
        rows.append(row)
    conditions=report['protocol']['conditions'];expected={(p,c,b) for p in ('DSH','OpenClaw') for c in conditions for b in range(1,report['blocks']+1)}
    complete={(r['product'],r['condition'],r['block']) for r in rows}==expected and len(rows)==len(expected) and all(r['valid'] and r['resources_complete'] for r in rows) and report['fixture_capacity']['valid']
    pairs=[]
    for product in ('DSH','OpenClaw'):
        for block in range(1,report['blocks']+1):
            by={r['condition']:r for r in rows if r['product']==product and r['block']==block}
            if 'four_sequential' in by and 'four_concurrent' in by:
                seq=by['four_sequential'];conc=by['four_concurrent']
                pairs.append(dict(product=product,block=block,sequential_to_concurrent_wall_ratio=seq['task_phase_seconds']/conc['task_phase_seconds'],
                    concurrent_minus_sequential_cpu_seconds=conc['native_phase_cpu_seconds']-seq['native_phase_cpu_seconds'],
                    concurrent_minus_sequential_rss_mib_seconds=conc['native_phase_rss_mib_seconds']-seq['native_phase_rss_mib_seconds'],
                    accepted_work=[seq['accepted_tasks'],conc['accepted_tasks']]))
    return dict(study='PC-HTTP-01',phase=report['phase'],run_id=report['run_id'],controller_commit=report['controller_commit'],protocol_sha256=report['protocol_sha256'],complete_comparison_blocks=complete,
        paid_model_calls=0,fixture_capacity=report['fixture_capacity'],rows=rows,paired_four_task_effects=pairs,
        limits='Fixed four-task scripted load, two native single-user service configurations. Fresh process/state is not cold OS cache. Phase resources are whole-service values; priming excluded from phase but included in lifecycle. Auxiliary titles may overlap native work. Observer cost is separate and can contend on the host; no disabled-observer causal contrast, sustainable throughput, p99 or product ranking.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes();raw=gzip.decompress(raw) if args.report.suffix=='.gz' else raw
    summary=summarize(json.loads(raw));summary['original_report_sha256']=hashlib.sha256(raw).hexdigest();args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (args.output/'metrics.csv').open('w') as file:
        writer=csv.DictWriter(file,fieldnames=list(summary['rows'][0]),lineterminator='\n');writer.writeheader();writer.writerows(summary['rows'])
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','fixture_capacity','paired_four_task_effects')}))

if __name__=='__main__':main()
