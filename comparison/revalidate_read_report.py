#!/usr/bin/env python3
"""Recheck retained terminal receipts without repeating native execution or model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
from native_read_probe import final_receipt_matches
from export_read_metrics import normalized_usage,request_stage


def revalidate(raw,source):
    report=json.loads(raw)
    for result in report['results']:
        candidates=set(re.findall(r'OWNED_NATIVE_READ_[0-9a-f]{32}',result.get('stdout','')))
        if len(candidates)!=1:raise ValueError('Expected exactly one retained receipt per arm')
        receipt=candidates.pop()
        if hashlib.sha256((receipt+'\n').encode()).hexdigest()!=result['file_sha256']:raise ValueError('Receipt does not match original input hash')
        observed=final_receipt_matches(result['product'],result['stdout'],receipt)
        result['revalidation']=dict(original_valid=result['valid'],original_final_receipt=result['receipt_observed_in_final_output'],
            final_receipt_verified=observed,validator_revision='terminal-receipt-whitespace-v2',
            change='Read terminal output fields, permit whitespace after evaluator marker; file content must match exactly. Original judgment preserved.')
        if result['product']=='OpenClaw':
            metadata=json.loads(result['stdout'])['meta']
            native=metadata.get('agentMeta',{})
            result['native_metadata']={key:metadata.get(key) for key in ('replayInvalid','requestShaping','completion','toolSummary','durationMs')}
            result['native_metadata'].update(usage=native.get('usage'),context_budget_status=native.get('contextBudgetStatus'))
            native_total=native.get('usage',{}).get('total')
        else:
            steps=[json.loads(line)['usage'] for line in result['stdout'].splitlines() if line.startswith('{') and json.loads(line).get('type')=='status' and json.loads(line).get('phase')=='step_end']
            result['native_metadata']=dict(step_usage=steps)
            native_total=sum(v['totalTokens'] for v in steps)
        provider_task_tokens=auxiliary_tokens=0
        for request,accounting in zip(result['provider_requests'],result['token_usage']['requests']):
            usage=normalized_usage(request['endpoint'],accounting['usage'])
            if usage is None or not accounting['complete']:raise ValueError('Complete real provider counters required for this pilot reanalysis')
            total=usage['input_tokens']+usage['output_tokens']
            if request_stage(request)=='auxiliary_session_title':auxiliary_tokens+=total
            else:provider_task_tokens+=total
        result['native_provider_usage_check']=dict(native_task_tokens=native_total,provider_task_tokens=provider_task_tokens,
            auxiliary_tokens=auxiliary_tokens,total_provider_tokens=provider_task_tokens+auxiliary_tokens,
            consistent=native_total==provider_task_tokens,
            cost_rule='Native configured-provider cost metadata is not an invoice. Real charge remains unknown, even if native cost.total is zero.')
        if native_total!=provider_task_tokens:raise ValueError('Native and independent provider task counters disagree')
        result['revalidated_valid']=result['exit_code']==0 and result['receipt_was_absent_from_initial_prompt'] and result['native_read_requested'] and result['receipt_observed_in_tool_result'] and result['input_unchanged'] and observed and (result['route']=='native' or len(result['mcp_events'])==1)
    report['reanalysis_provenance']=dict(original_report_sha256=hashlib.sha256(raw).hexdigest(),**source,
        validator_controller_commit=os.environ.get('GITHUB_SHA'),
        validator_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        terminal_parser_source_sha256=hashlib.sha256(Path(__file__).with_name('native_read_probe.py').read_bytes()).hexdigest(),
        paid_model_calls_during_reanalysis=0,native_executions_during_reanalysis=0,
        scope='Exploratory pilot receipt revalidation, not retrospective formal comparison credit')
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--artifact-id',type=int,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    archive=args.archive.read_bytes()
    if hashlib.sha256(archive).hexdigest()!=args.sha256:raise ValueError('Source artifact ZIP digest mismatch')
    with zipfile.ZipFile(args.archive) as z:raw=z.read('native-read-calibration.json')
    report=revalidate(raw,dict(artifact_zip_sha256=args.sha256,artifact_id=args.artifact_id))
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'revalidated-read-report.json').write_text(json.dumps(report,indent=2)+'\n')
    compact=json.loads(json.dumps(report))
    for row in compact['results']:
        for key in ('stdout','stderr','provider_requests'):row.pop(key,None)
    (args.output/'read-pilot-summary.json').write_text(json.dumps(compact,indent=2)+'\n')
    print(json.dumps([dict(product=r['product'],route=r['route'],original_valid=r['valid'],revalidated_valid=r['revalidated_valid'],resources_complete=r['resource_collection_valid']) for r in report['results']]))
    if not all(r['revalidated_valid'] and r['resource_collection_valid'] for r in report['results']):raise SystemExit('Retained pilot revalidation incomplete')

if __name__=='__main__':main()
