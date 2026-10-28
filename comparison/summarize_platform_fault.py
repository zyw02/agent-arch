#!/usr/bin/env python3
"""Offline PA metrics; retained native facts and independent receipts stay distinct."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from context_skill_probe import request_text
from platform_api_probe import MARKER,fresh_session_bindings
from platform_fault_probe import history_facts


def summarize(report):
    rows=[]
    for arm in report['results']:
        bindings=fresh_session_bindings(arm['product'],[dict(**t,session_key='agent:main:platform:'+t['session_id']) for t in arm['tasks'].values()],
            [e for e in arm['boundary_ledger'] if e['received_ns']<=arm.get('boundary_ns',0)])
        record=dict(product=arm['product'],condition=arm['condition'],block=arm['block'],phase=report['phase'],validity=arm['validity'],
            boundary_native_bindings=bindings['valid'],resources_complete=arm['resource_collection_complete'],elapsed_seconds=arm['elapsed_ms']/1000,
            startup_seconds=arm.get('startup_ms',0)/1000,native_lifecycle_cpu_seconds=sum(c['resources']['cgroup'].get('cpu',{}).get('usage_usec',0)/1e6 for c in arm['cycles']),
            peak_native_pss_mib=max((c['resources'].get('sampled_peak_pss_bytes') or 0)/2**20 for c in arm['cycles']),
            native_processes_at_boundary=len(arm.get('boundary_process_map',[])),
            surviving_processes_at_end_of_fault_window=len(arm.get('observation',[{}])[-1].get('process_map',[])))
        for role,task in arm['tasks'].items():
            terminals=[e for e in arm.get('clients',{}).get(role,{}).get('events',[]) if e.get('kind')=='terminal']
            record[role+'_client_received_ack']=any(e['result'].get('accepted') for e in terminals)
            record[role+'_client_transport_error']=any(e.get('kind')=='transport_error' for e in arm.get('clients',{}).get(role,{}).get('events',[]))
            for stage,prefix in [('before_restart_histories','before_restart'),('passive_histories','restart_initial'),('after_passive_window_histories','restart_later')]:
                h=arm.get(stage,{}).get(role,{})
                facts=history_facts(arm['product'],h.get('native',{}),task['marker']) if 'native' in h else None
                if facts is not None and h.get('facts')!=facts:raise ValueError('Retained native-history judgment changed')
                record[role+'_'+prefix+'_user_retained']=facts['user_retained'] if facts else None
                record[role+'_'+prefix+'_ack']=facts['assistant_ack'] if facts else None
            before=arm.get('followup_started_ns',float('inf'));restart=arm.get('restart_requested_ns',float('inf'))
            original=[e for e in arm['boundary_ledger'] if not e['title'] and MARKER.findall(request_text(e['request']))[-1:]==[task['marker']]]
            record[role+'_original_requests']=len(original)
            record[role+'_original_requests_after_restart_before_followup']=sum(restart<=e['received_ns']<before for e in original)
            follow=arm.get('followups',{}).get(role,{})
            record[role+'_new_followup_ack']=follow.get('result',{}).get('accepted',False)
            record[role+'_followup_prior_user_visible']=bool(follow.get('provider_contexts')) and all(e['prior_user'] for e in follow['provider_contexts'])
            record[role+'_followup_prior_ack_visible']=bool(follow.get('provider_contexts')) and all(e['prior_ack'] for e in follow['provider_contexts'])
        rows.append(record)
    expected=6*(1 if report['phase']=='pilot' else report.get('blocks',len({r['block'] for r in rows})))
    keys={(r['product'],r['condition'],r['block']) for r in rows}
    complete=len(keys)==len(rows)==expected and all(r['validity']=='valid' and r['boundary_native_bindings'] and r['resources_complete'] for r in rows)
    return dict(study='PA-HTTP-01',phase=report['phase'],run_id=report['run_id'],controller_commit=report['controller_commit'],protocol_sha256=report['protocol_sha256'],
        complete_comparison_blocks=complete,paid_model_calls=0,rows=rows,
        limits='Synthetic task; public HTTP client loss and single native owner exit. Cleanup kills descendants only after observation window. Native lifecycle CPU includes both service cycles and history serving; history CLI/client/controller CPU is separate. Formal completion also requires blind native-only reconstruction.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=json.loads(args.report.read_bytes());summary=summarize(report);summary['original_report_sha256']=hashlib.sha256(args.report.read_bytes()).hexdigest();args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (args.output/'metrics.csv').open('w') as file:
        writer=csv.DictWriter(file,fieldnames=list(summary['rows'][0]));writer.writeheader();writer.writerows(summary['rows'])
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))

if __name__=='__main__':main()
