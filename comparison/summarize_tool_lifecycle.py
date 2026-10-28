#!/usr/bin/env python3
"""Recompute HD read results, MCP receipts and native resources without execution."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from context_skill_probe import request_text
from platform_resource_probe import integrate_memory
from tool_lifecycle_probe import CONDITIONS,fixture_receipts_complete,native_cancelled,terminal_text,tool_results


def title(request):return 'Generate the session title from this JSON array' in request_text(request['request'])


def expected_text(marker,values,condition,failure_marker):
    indexes=[0] if condition in ('native_single','mcp_single') else range(4)
    output={str(i):'error:'+failure_marker if condition=='mcp_batch_failure' and i==2 else values[i] for i in indexes}
    return 'TOOL_DONE:'+marker+':'+json.dumps(output,sort_keys=True,separators=(',',':'))


def active_peak(events):
    changes=[(e['monotonic_ns'],1) for e in events if e['kind']=='call_received']+[(e['monotonic_ns'],-1) for e in events if e['kind']=='call_stopped']
    active=peak=0
    for _,delta in sorted(changes):active+=delta;peak=max(peak,active)
    return peak


def summarize(report,protocol_path):
    protocol_raw=protocol_path.read_bytes()
    if hashlib.sha256(protocol_raw).hexdigest()!=report['protocol_sha256']:raise ValueError('Frozen HD protocol identity changed')
    rows=[];requests=[]
    for arm in report['results']:
        product=arm['product'];condition=arm['condition'];block=arm['block'];base=dict(product=product,condition=condition,block=block,validity=arm['validity'])
        if 'resources' not in arm:
            rows.append(dict(**base,complete_record=False,handling_acceptance_met=False,product_outcome=None));continue
        values=arm['input_values'];resources=arm['resources'];task=arm.get('task',{});marker=arm['task_marker'];failure_marker=arm['fixture_config']['failure_marker']
        if {str(i):hashlib.sha256(v.encode()).hexdigest() for i,v in enumerate(values)}!=arm['file_hashes']:raise ValueError('Owned input value/hash identity changed')
        exact=terminal_text(product,task.get('native_result',{}))==expected_text(marker,values,condition,failure_marker)
        if 'exact_final' in task and exact!=task['exact_final']:raise ValueError('Original native terminal-field judgment changed')
        raw_ledger=[json.loads(line) for line in arm.get('fixture_ledger_raw','').splitlines()]
        if raw_ledger!=arm['fixture_events']:raise ValueError('Retained MCP event projection differs from raw ledger')
        receipt_complete=fixture_receipts_complete(arm)
        if receipt_complete!=arm['independent_fixture_receipts_complete']:raise ValueError('Original independent receipt judgment changed')
        primary=[r for r in arm['provider_requests'] if not title(r) and marker in request_text(r['request'])]
        initial_absent=not any(value in json.dumps(primary[0]['request']) for value in values) if primary else None
        if initial_absent!=arm['initial_input_values_absent']:raise ValueError('Initial answer-leak judgment changed')
        native_identity=task.get('session_key') if product=='OpenClaw' else task.get('create_receipt',{}).get('sessionId')
        binding=bool(primary) and bool(native_identity) and (native_identity==task.get('session_id') and task.get('prompt_receipt',{}).get('accepted') is True if product=='DSH' else all('session='+native_identity+' |' in request_text(r['request']) for r in primary))
        health=arm.get('health_task',{});health_exact=terminal_text(product,health.get('native_result',{}))==expected_text(health.get('marker'),values,'mcp_single',failure_marker) if health else None
        if health and health_exact!=health.get('exact_final'):raise ValueError('Health terminal-field judgment changed')
        cancel_ack=cancelled=quiescent=None;old_after=[]
        if condition=='mcp_batch_cancel' and 'cancel' in arm:
            receipt=arm['cancel'].get('receipt') or {};cancel_ack=receipt.get('accepted') is True if product=='DSH' else receipt.get('aborted') is True;cancelled=native_cancelled(product,arm.get('cancel_history',{}))
            epoch=arm['cancel']['received_ns'];observations=arm['cancel_observations'];last=observations[-1]
            if [o['offset_seconds'] for o in observations]!=[.5,2,10] or any(o['observed_ns']<epoch+int(o['offset_seconds']*1e9) for o in observations):raise ValueError('Incomplete or early cancellation observation')
            active={e['mcp_call_id']:e for e in raw_ledger if e['kind']=='call_received' and e['monotonic_ns']<=last['observed_ns']}
            for e in raw_ledger:
                if e['kind']=='call_stopped' and e['monotonic_ns']<=last['observed_ns']:active.pop(e['mcp_call_id'],None)
            live_ids={p['pid'] for p in last['processes']};active_live=[e for e in active.values() if e['pid'] in live_ids]
            if active_live!=last['active_live_fixture_calls']:raise ValueError('Cancel fixture/process witness changed')
            old_after=[i for i,r in enumerate(arm['provider_requests']) if r['arrived_ns']>epoch and not title(r) and marker in request_text(r['request'])]
            # The original quiescence cut excludes later native history/cleanup and health.
            old_at_cut=[r for r in primary if epoch<r['arrived_ns']<=last['observed_ns']]
            quiescent=not active_live and not last['native_task_consumer_alive'] and not old_at_cut
            if quiescent!=arm['quiescent_at_10s'] or cancel_ack!=arm['cancel_acknowledged'] or cancelled!=arm['native_cancelled_terminal'] or old_after!=arm['old_task_requests_after_cancel']:raise ValueError('Frozen cancellation judgments changed')
            handling=cancel_ack and cancelled and quiescent and not arm['native_task_consumer_still_alive_after_cleanup_release'] and health_exact and receipt_complete and not old_after
        else:handling=exact and receipt_complete
        if handling!=arm['handling_acceptance_met']:raise ValueError('Original handling judgment changed')
        start=arm.get('task_phase_started_ns');end=arm.get('task_phase_finished_ns');samples=resources.get('samples',[])
        phase_samples=[s for s in samples if start is not None and end is not None and start<=s['monotonic_ns']<=end]
        rss=integrate_memory(samples,start,end,'sampled_rss_sum_bytes') if start is not None and end is not None else None
        cpu=(arm['phase_end']['cpu']['usage_usec']-arm['phase_start']['cpu']['usage_usec'])/1e6 if 'phase_start' in arm and 'phase_end' in arm else None
        times=[s['monotonic_ns'] for s in phase_samples if 'sampled_rss_sum_bytes' in s];gaps=[(b-a)/1e6 for a,b in zip(times,times[1:])]
        primary_events=[e for e in raw_ledger if e['monotonic_ns']<arm.get('health_started_ns',float('inf'))]
        attempts=Counter(e['index'] for e in primary_events if e['kind']=='call_received');offered=Counter(c['arguments'].get('index') for r in primary for c in r.get('decision',{}).get('calls',[]) if c['name']!='read')
        model_repeated=any(n>1 for n in offered.values());native_repeated=any(n>offered[i] for i,n in attempts.items());repeat_owner='both' if model_repeated and native_repeated else 'model' if model_repeated else 'native' if native_repeated else 'no_repeat'
        check=arm.get('independent_delivery_check',{});independent_latency=(check['checked_ns']-task['started_ns'])/1e9 if condition!='mcp_batch_cancel' and check.get('native_exact') and check.get('fixture_receipts_complete') and check.get('input_unchanged') else None
        row=dict(**base,complete_record=arm['complete_record'],handling_acceptance_met=handling,product_outcome=arm.get('product_outcome'),native_binding=binding,input_values_absent_initial=initial_absent,
            full_arm_seconds=(arm['finished_ns']-arm['started_ns'])/1e9,startup_seconds=(arm['carrier_ready_ns']-arm['started_ns'])/1e9 if 'carrier_ready_ns' in arm else None,
            native_terminal_seconds=(task['finished_ns']-task['started_ns'])/1e9 if 'finished_ns' in task else None,independent_delivery_check_seconds=independent_latency,
            case_phase_seconds=(end-start)/1e9 if start is not None and end is not None else None,native_case_phase_cpu_seconds=cpu,native_case_phase_rss_mib_seconds=rss/2**20 if rss is not None else None,
            native_lifecycle_cpu_seconds=resources.get('cgroup',{}).get('cpu',{}).get('usage_usec')/1e6 if 'usage_usec' in resources.get('cgroup',{}).get('cpu',{}) else None,
            sampled_lifecycle_peak_pss_mib=resources['sampled_peak_pss_bytes']/2**20 if resources.get('sampled_peak_pss_bytes') is not None else None,
            owned_disk_peak_mib=resources['disk_peak_allocated_bytes']/2**20 if resources.get('disk_peak_allocated_bytes') is not None else None,
            resources_complete=resources['complete'],model_task_roundtrips=len(primary),model_calls_offered=sum(len(r.get('decision',{}).get('calls',[])) for r in primary),
            auxiliary_model_requests=sum(title(r) for r in arm['provider_requests']),mcp_attempts=len([e for e in primary_events if e['kind']=='call_received']),mcp_active_peak=active_peak(primary_events),
            successful_read_receipts=len([e for e in primary_events if e['kind']=='file_read']),controlled_failures=len([e for e in primary_events if e['kind']=='failure_injected']),repeat_owner=repeat_owner if condition!='native_single' else None,
            cancelled=cancelled,cancel_acknowledged=cancel_ack,quiescent_at_10s=quiescent,health_exact=health_exact,
            observer_parent_cpu_seconds=arm['observer_parent_cpu_seconds'],memory_reader_cpu_seconds=resources.get('memory_reader_cpu_seconds'),
            inspector_cli_cpu_seconds=sum(h.get('observer_cli',{}).get('cpu_seconds',0) for h in (arm.get('native_history',{}),arm.get('cancel_history',{}),arm.get('cancel',{})) if h.get('observer_cli')),
            median_observed_sample_gap_ms=statistics.median(gaps) if gaps else None,max_observed_sample_gap_ms=max(gaps,default=None),actual_provider_tokens=None,invoice_charge=None)
        row['observer_total_cpu_seconds']=sum(row[k] for k in ('observer_parent_cpu_seconds','memory_reader_cpu_seconds','inspector_cli_cpu_seconds')) if row['memory_reader_cpu_seconds'] is not None else None
        rows.append(row)
        for index,r in enumerate(arm['provider_requests']):
            body=r['request'];requests.append(dict(product=product,condition=condition,block=block,request_index=index,stage='auxiliary_title' if title(r) else 'primary' if marker in request_text(body) else 'health_or_other',endpoint=r['endpoint'],
                request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),request_json_bytes=len(json.dumps(body).encode()),messages_json_bytes=len(json.dumps(body.get('messages',[])).encode()),tools_json_bytes=len(json.dumps(body.get('tools',[])).encode()),
                synthetic_usage=r.get('response',{}).get('usage'),actual_usage=None,invoice_charge=None))
    blocks=1 if report['phase']=='pilot' else 2;expected={(p,c,b) for p in ('DSH','OpenClaw') for c in CONDITIONS for b in range(1,blocks+1)}
    complete=len(rows)==len(expected) and {(r['product'],r['condition'],r['block']) for r in rows}==expected and all(r['complete_record'] and r.get('native_binding') for r in rows)
    controls=all(r['handling_acceptance_met'] for r in rows if r['condition'] in CONDITIONS[:4]) and sum(r['condition'] in CONDITIONS[:4] for r in rows)==8*blocks
    return dict(study=report['study'],phase=report['phase'],run_id=report['run_id'],controller_commit=report['controller_commit'],protocol_sha256=report['protocol_sha256'],complete_comparison_blocks=complete,healthy_controls_passed=controls,rows=rows,request_payloads=requests,
        paid_model_calls=0,limits='Scripted protocol counters are not actual tokens. Cold native services retain installation/OS caches. Normal phase covers workload and check; cancel case phase additionally includes observation, native inspection and health. MCP code/trace cost is included with native children; model/controller and inspector CLI are separate. Two formal blocks are descriptive, not a general ranking or pure transport/scheduler causal decomposition.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes();raw=gzip.decompress(raw) if args.report.suffix=='.gz' else raw
    summary=summarize(json.loads(raw),args.protocol);summary['original_report_sha256']=hashlib.sha256(raw).hexdigest();args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(args.output/'request-payloads.json').write_text(json.dumps(summary['request_payloads'],indent=2)+'\n')
    fields=list(dict.fromkeys(k for row in summary['rows'] for k in row))
    with (args.output/'metrics.csv').open('w') as file:
        writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(summary['rows'])
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','request_payloads')}))


if __name__=='__main__':main()
