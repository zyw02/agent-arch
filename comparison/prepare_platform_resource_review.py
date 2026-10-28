#!/usr/bin/env python3
"""Freeze PC native-only packets and separate externally observed answer key."""
import argparse
import gzip
import json
from pathlib import Path
import random
import time
import uuid
from review_platform_native import digest,sanitize_native
from summarize_platform_resource import summarize

PROTOCOL=Path(__file__).with_name('platform-resource-native-review-protocol.json')


def make_packet(arm,case_id):
    return sanitize_native(dict(case_id=case_id,task_identifiers=dict(workload_markers=[t['marker'] for t in arm['tasks']],priming_marker=arm.get('priming_task',{}).get('marker')),
        native_carrier_logs=[arm['sanitized_native_log']],native_api_responses=[dict(task_marker=t['marker'],response=t.get('native_result')) for t in arm['tasks']],
        capture_scope='Public native terminal response JSON for workload tasks; stdout capture at most last 150 lines/2400 characters per line. Native file logs and histories beyond these responses were not inventoried. Condition, external timing and measured process/resource/fixture data are withheld. Missing facts do not establish absence from all native surfaces.'))


def prepare(report,output):
    summary=summarize(report)
    if not summary['complete_comparison_blocks']:raise ValueError('Native-only PC review requires complete blocks')
    output.mkdir(parents=True,exist_ok=True);(output/'packets').mkdir(exist_ok=True);pairs=list(zip(report['results'],summary['rows']));random.SystemRandom().shuffle(pairs);keys={};manifest=[]
    for arm,row in pairs:
        case_id=uuid.uuid4().hex
        packet=make_packet(arm,case_id)
        raw=(json.dumps(packet,indent=2)+'\n').encode();(output/'packets'/(case_id+'.json')).write_bytes(raw);manifest.append(dict(case_id=case_id,packet_sha256=digest(raw)))
        keys[case_id]=dict(product=row['product'],condition=row['condition'],block=row['block'],answers=dict(accepted_workload_tasks=str(row['accepted_tasks']),ownership='service' if row['offered_tasks'] else None,simultaneous_model_requests=str(row['max_simultaneous_task_model_requests'])))
    key_raw=(json.dumps(keys,indent=2)+'\n').encode();(output/'withheld-answer-key.json').write_bytes(key_raw)
    manifest_obj=dict(protocol_sha256=digest(PROTOCOL.read_bytes()),withheld_key_sha256=digest(key_raw),prepared_ns=time.monotonic_ns(),packets=manifest,source_run_id=report['run_id'],source_controller_commit=report['controller_commit'])
    (output/'manifest.json').write_text(json.dumps(manifest_obj,indent=2)+'\n');return manifest_obj


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes();raw=gzip.decompress(raw) if args.report.suffix=='.gz' else raw;prepare(json.loads(raw),args.output)

if __name__=='__main__':main()
