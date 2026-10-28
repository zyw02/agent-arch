#!/usr/bin/env python3
"""Freeze HD native-only packets and independently reconstructed answer keys."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import random
import re
import time
import uuid
from review_platform_native import digest
from summarize_tool_lifecycle import summarize
from tool_lifecycle_probe import terminal_text

PROTOCOL=Path(__file__).with_name('tool-lifecycle-native-review-protocol.json')
TASK_PROTOCOL=Path(__file__).with_name('tool-lifecycle-protocol.json')
CONDITIONS=('mcp_four_batch','mcp_batch_failure')


def make_packet(arm,case_id):
    history=copy.deepcopy(arm.get('native_history',{}));history.pop('observer_cli',None)
    packet=dict(case_id=case_id,task_identifiers=dict(task_marker=arm['task_marker'],session_id=arm['task']['session_id'],offered_indexes=[0,1,2,3]),
        native_history=history,native_carrier_logs=[arm['sanitized_native_log']],
        capture_scope='Public native history plus stdout tail (at most 150 lines, 2400 characters per line). Native file logs are not inventoried. External condition labels, provider requests, MCP receipts, timing, process/resources and answer keys are withheld. Missing events do not establish absence from all native surfaces.')
    # Paths encode the experimental condition; preserve native events and values.
    raw=json.dumps(packet)
    raw=re.sub(r'/[^\s"\\]*tool-lifecycle-[^/\s"\\]+/[0-9]+-(?:DSH|OpenClaw)-(?:mcp_four_batch|mcp_batch_failure)', '<owned-root>',raw)
    return json.loads(raw)


def expected_answers(arm,row):
    failures={e['index'] for e in arm['fixture_events'] if e['kind']=='failure_injected'}
    if len(failures)>1:raise ValueError('Single-failure review protocol cannot score multiple failed indexes')
    final=terminal_text(arm['product'],arm['task'].get('native_result',{}))
    read_indexes={e['index'] for e in arm['fixture_events'] if e['kind']=='file_read'}
    delivered=sum(i in read_indexes and value in final for i,value in enumerate(arm['input_values']))
    return dict(failed_read_index=str(next(iter(failures))) if failures else 'none',repeat_owner=row['repeat_owner'],delivered_value_count=str(delivered))


def prepare(report,output):
    summary=summarize(report,TASK_PROTOCOL)
    if report['phase']!='formal' or not summary['complete_comparison_blocks'] or not summary['healthy_controls_passed']:raise ValueError('Complete formal HD blocks and usable controls required')
    output.mkdir(parents=True,exist_ok=True);(output/'packets').mkdir(exist_ok=True)
    pairs=[(a,r) for a,r in zip(report['results'],summary['rows']) if a['condition'] in CONDITIONS]
    random.SystemRandom().shuffle(pairs);keys={};manifest=[]
    for arm,row in pairs:
        case_id=uuid.uuid4().hex;raw=(json.dumps(make_packet(arm,case_id),indent=2)+'\n').encode()
        (output/'packets'/(case_id+'.json')).write_bytes(raw);manifest.append(dict(case_id=case_id,packet_sha256=digest(raw)))
        keys[case_id]=dict(product=row['product'],condition=row['condition'],block=row['block'],answers=expected_answers(arm,row))
    key_raw=(json.dumps(keys,indent=2)+'\n').encode();(output/'withheld-answer-key.json').write_bytes(key_raw)
    result=dict(protocol_sha256=digest(PROTOCOL.read_bytes()),withheld_key_sha256=digest(key_raw),prepared_ns=time.monotonic_ns(),packets=manifest,source_run_id=report['run_id'],source_controller_commit=report['controller_commit'])
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes()
    prepare(json.loads(gzip.decompress(raw) if args.report.suffix=='.gz' else raw),args.output)

if __name__=='__main__':main()
