#!/usr/bin/env python3
"""Additional descriptive PA recovery timing; never changes window outcomes."""
import argparse
import gzip
import json
from pathlib import Path
import re
from platform_fault_probe import history_facts


def describe(report):
    rows=[]
    for arm in report['results']:
        if arm['condition']!='owner_exit':continue
        cut=arm['followup_started_ns'];ready=arm['restart_ready_ns']
        native_logs=''.join(arm['cycles'][1]['sanitized_native_log']);native_logs=re.sub(r'\x1b\[[0-9;]*m','',native_logs)
        for role,task in arm['tasks'].items():
            arrivals=[e['received_ns'] for e in arm['boundary_ledger'] if not e['title'] and e['marker']==task['marker'] and e['received_ns']>=arm['restart_requested_ns']]
            facts=history_facts(arm['product'],arm['final_histories'][role]['native'],task['marker'])
            rows.append(dict(product=arm['product'],block=arm['block'],role=role,session_id=task['session_id'],
                before_followup_ack=arm['after_passive_window_histories'][role]['facts']['assistant_ack'],
                first_original_request_seconds_after_restart_ready=(min(arrivals)-ready)/1e9 if arrivals else None,
                first_original_request_seconds_after_new_followup_phase=(min(arrivals)-cut)/1e9 if arrivals else None,
                original_requests_after_restart=len(arrivals),final_original_ack=facts['assistant_ack'],
                native_recovery_lines=[line for line in native_logs.splitlines() if 'main-session-restart-recovery' in line and (task['session_id'] in line or 'marked ' in line or 'startup complete' in line)]))
    return dict(study='PA-HTTP-01',role='Additional descriptive post-cut timing from original raw records; not formal-window success or an extra repetition',rows=rows,
        interpretation='Model request arrival is independently observed. Native startup scheduling/dispatch can precede that arrival. Requests after the new-followup phase begins cannot earn pre-followup recovery credit. Source/native recovery labels corroborate autonomous ownership, but no no-followup counterfactual was executed beyond the frozen window.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes();raw=gzip.decompress(raw) if args.report.suffix=='.gz' else raw
    args.output.write_text(json.dumps(describe(json.loads(raw)),indent=2)+'\n')

if __name__=='__main__':main()
