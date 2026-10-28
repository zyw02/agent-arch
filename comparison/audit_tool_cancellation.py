#!/usr/bin/env python3
"""Secondary HD cessation audit; preserve the frozen original judgments."""
import argparse
import gzip
import json
from pathlib import Path
from context_skill_probe import request_text


def audit(report):
    rows=[]
    for arm in report['results']:
        if arm['condition']!='mcp_batch_cancel' or 'cancel' not in arm:continue
        epoch=arm['cancel']['received_ns'];health=arm['health_started_ns'];cut=arm['cancel_observations'][-1]['observed_ns'];events=arm['fixture_events']
        calls=[e for e in events if e['kind']=='call_received'];post=[e for e in calls if epoch<e['monotonic_ns']<health];health_calls=[e for e in calls if e['monotonic_ns']>=health]
        release=[e['monotonic_ns'] for e in events if e['kind']=='cleanup_released'];release_ns=min(release) if release else None
        old=[r['arrived_ns'] for r in arm['provider_requests'] if r['arrived_ns']>epoch and arm['task_marker'] in request_text(r['request']) and 'Generate the session title' not in request_text(r['request'])]
        rows.append(dict(product=arm['product'],block=arm['block'],original_handling_acceptance=arm['handling_acceptance_met'],
            new_mcp_calls_after_cancel_before_health=[dict(index=e['index'],mcp_call_id=e['mcp_call_id'],seconds_after_receipt=(e['monotonic_ns']-epoch)/1e9) for e in post],
            health_period_call_indexes=[e['index'] for e in health_calls],health_period_exactly_one_index_zero_call=len(health_calls)==1 and health_calls[0]['index']==0,
            held_index_ever_read=any(e['kind']=='file_read' and e['index']==2 for e in events),
            old_model_requests_within_observation=sum(t<=cut for t in old),old_model_requests_after_observation=sum(t>cut for t in old),
            old_model_requests_after_fixture_cleanup_release=sum(t>=release_ns for t in old) if release_ns is not None else None,
            accepted_original_has_no_extra_tool_dispatch=(not post and len(health_calls)==1 and health_calls[0]['index']==0 and not any(e['kind']=='file_read' and e['index']==2 for e in events)) if arm['handling_acceptance_met'] else None))
    expected={(p,b) for p in ('DSH','OpenClaw') for b in range(1,3 if report['phase']=='formal' else 2)}
    return dict(study=report['study'],source_run_id=report['run_id'],complete_cancel_arm_coverage=len(rows)==len(expected) and {(r['product'],r['block']) for r in rows}==expected,
        analysis_scope='Secondary consistency audit prepared after formal execution started, before formal outcomes were inspected. Does not replace original acceptance judgments. Health starts after original observation/cleanup; the independent ledger must contain exactly its one index-0 call, and the held index must never be read.',rows=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes()
    args.output.write_text(json.dumps(audit(json.loads(gzip.decompress(raw) if args.report.suffix=='.gz' else raw)),indent=2)+'\n')

if __name__=='__main__':main()
