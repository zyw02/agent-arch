#!/usr/bin/env python3
"""Verify original review archive, actual native-only input and immutable scores."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from review_platform_native import digest,score,make_packet as pa_packet
from prepare_platform_resource_review import make_packet as pc_packet
from summarize_platform_fault import summarize as pa_summary
from summarize_platform_resource import summarize as pc_summary


def expected_answers(row,study):
    if study=='PC':
        return dict(accepted_workload_tasks=str(row['accepted_tasks']),ownership='service' if row['offered_tasks'] else None,simultaneous_model_requests=str(row['max_simultaneous_task_model_requests']))
    return dict(ownership='service',interruption={'healthy':'none','client_exit':'client_exit','owner_exit':'owner_exit'}[row['condition']],
        primary_retained_ack=('yes' if row['primary_restart_later_ack'] else 'no') if row['primary_restart_later_ack'] is not None else None,
        companion_retained_ack=('yes' if row['companion_restart_later_ack'] else 'no') if row['companion_restart_later_ack'] is not None else None,
        repeated_original_request='yes' if row['primary_original_requests_after_restart_before_followup'] else 'no',
        new_followup_completed='yes' if row['primary_new_followup_ack'] else 'no')


def export(archive,expected_digest,source_report,protocol,study,output):
    if digest(archive.read_bytes())!=expected_digest:raise ValueError('Original review artifact digest mismatch')
    source_raw=source_report.read_bytes();source_raw=gzip.decompress(source_raw) if source_report.suffix=='.gz' else source_raw;source=json.loads(source_raw)
    arms={(r['product'],r['condition'],r['block']):r for r in source['results']};packet_builder=pa_packet if study=='PA' else pc_packet
    source_summary=(pa_summary if study=='PA' else pc_summary)(source)
    if not source_summary['complete_comparison_blocks']:raise ValueError('Complete native source blocks required')
    truth={(r['product'],r['condition'],r['block']):expected_answers(r,study) for r in source_summary['rows']}
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-review-export-') as tmp:
        temp=Path(tmp)
        with zipfile.ZipFile(archive) as zipped:
            if sum(f.file_size for f in zipped.infolist())>128*1024**2:raise ValueError('Review evidence archive bound exceeded')
            for member in zipped.infolist():
                target=(temp/member.filename).resolve()
                if not target.is_relative_to(temp):raise ValueError('Unsafe archive member path')
                zipped.extract(member,temp)
        manifests=list(temp.glob('*/manifest.json'))
        if len(manifests)!=1:raise ValueError('Review manifest identity ambiguous')
        dataset=manifests[0].parent;reviews=temp/('native-review-answers' if study=='PA' else 'native-pc-review-answers');manifest=json.loads(manifests[0].read_bytes());key=json.loads((dataset/'withheld-answer-key.json').read_bytes())
        recomputed=score(dataset,reviews,protocol);original=json.loads((dataset/'score.json').read_bytes())
        if recomputed['rows']!=original['rows'] or recomputed['totals']!=original['totals']:raise ValueError('Frozen review judgments changed')
        if manifest['source_run_id']!=source['run_id'] or manifest['source_controller_commit']!=source['controller_commit']:raise ValueError('Native source run identity mismatch')
        if len(key)!=len(arms) or {(v['product'],v['condition'],v['block']) for v in key.values()}!=set(arms):raise ValueError('Review case coverage differs from native arms')
        if len(manifest['packets'])!=len(key) or {c['case_id'] for c in manifest['packets']}!=set(key):raise ValueError('Review manifest case coverage differs from key')
        if any(v['answers']!=truth[v['product'],v['condition'],v['block']] for v in key.values()):raise ValueError('Withheld answers differ from independently recomputed native experiment truth')
        usage=[]
        for case in manifest['packets']:
            case_id=case['case_id'];identity=key[case_id];arm=arms[identity['product'],identity['condition'],identity['block']];packet=json.loads((dataset/'packets'/(case_id+'.json')).read_bytes())
            if packet!=packet_builder(arm,case_id):raise ValueError('Reviewer packet is not the exact declared native-only projection')
            labels=('client_exit','owner_exit') if study=='PA' else ('cold_single','warm_single','four_sequential','four_concurrent')
            if any(label in json.dumps(packet) for label in labels):raise ValueError('Condition-bearing fixture path leaked into native packet')
            record=json.loads((reviews/(case_id+'.json')).read_bytes());request=record['request'];messages=request.get('messages',[])
            if set(request)!={'model','messages','thinking','temperature','max_tokens','stream'} or len(messages)!=2 or [m['role'] for m in messages]!=['system','user']:raise ValueError('Unexpected isolated reviewer request envelope')
            actual_prompt=json.loads(messages[1]['content']);frozen=json.loads(protocol.read_bytes())
            if set(actual_prompt)!={'questions','answer_format','native_packet'} or actual_prompt['questions']!=frozen['questions'] or actual_prompt['answer_format']!=frozen['answer_format']:raise ValueError('Actual model prompt differs from frozen questions or exposes extra truth')
            if record['started_ns']<manifest['prepared_ns']:raise ValueError('Answer began before native packet/key freeze')
            raw_usage=record.get('response',{}).get('usage',{});hit=raw_usage.get('prompt_cache_hit_tokens');miss=raw_usage.get('prompt_cache_miss_tokens');prompt=raw_usage.get('prompt_tokens')
            if hit is not None and miss is not None and hit+miss!=prompt:raise ValueError('Provider input cache partitions do not reconcile')
            if all(raw_usage.get(k) is not None for k in ('prompt_tokens','completion_tokens','total_tokens')) and raw_usage['prompt_tokens']+raw_usage['completion_tokens']!=raw_usage['total_tokens']:raise ValueError('Provider total tokens do not reconcile')
            choices=record.get('response',{}).get('choices',[])
            usage.append(dict(case_id=case_id,product=identity['product'],condition=identity['condition'],block=identity['block'],http_status=record.get('http_status'),
                finish_reason=choices[0].get('finish_reason') if choices else None,elapsed_ms=record['elapsed_ms'],input_tokens=prompt,output_tokens=raw_usage.get('completion_tokens'),total_tokens=raw_usage.get('total_tokens'),cached_input_subset_tokens=hit,
                complete=record.get('http_status')==200 and bool(choices) and choices[0].get('finish_reason')=='stop' and bool(raw_usage)))
        totals=original['totals'];rows=original['rows'];by_product={p:dict(Counter(r['classification'] for r in rows if r['product']==p)) for p in ('DSH','OpenClaw')}
        summary=dict(study=study+' native-only automated reconstruction',source_run_id=source['run_id'],source_controller_commit=source['controller_commit'],original_artifact_sha256=expected_digest,
            source_report_sha256=digest(source_raw),protocol_sha256=digest(protocol.read_bytes()),case_count=len(key),fact_count=len(rows),original_counts=totals,counts_by_product=by_product,
            by_question={q:{p:dict(Counter(r['classification'] for r in rows if r['product']==p and r['question']==q)) for p in ('DSH','OpenClaw')} for q in dict.fromkeys(r['question'] for r in rows)},
            exact_citation_substring_present=sum(r['citation_substring_present'] for r in rows),correct_value_and_exact_citation=sum(r['classification']=='correct' and r['citation_substring_present'] for r in rows),
            original_judgments_unchanged=True,all_actual_packets_equal_declared_native_projection=True,all_actual_questions_equal_frozen_protocol=True,all_answers_started_after_packet_and_key_freeze=True,
            actual_paid_requests=len(usage),provider_complete=sum(u['complete'] for u in usage),known_input_tokens=sum(u['input_tokens'] or 0 for u in usage),known_output_tokens=sum(u['output_tokens'] or 0 for u in usage),known_total_tokens=sum(u['total_tokens'] or 0 for u in usage),
            known_cached_input_subset_tokens=sum(u['cached_input_subset_tokens'] or 0 for u in usage),usage_coverage=sum(u['input_tokens'] is not None and u['output_tokens'] is not None for u in usage),
            automated_review_elapsed_seconds=sum(u['elapsed_ms'] for u in usage)/1000,actual_invoice_charge=None,
            interpretation='Raw value matches are not proof of evidentiary support. Exact quotation may still concern the wrong phase or cause. Audit reasons/citations separately, preserve unsupported matching guesses and unknowns. One automated investigator of selected native surfaces, not a product-wide observability ranking or human diagnosis time. Review tokens are separate from native task usage; cached input is a subset, not added again.')
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(output/'usage.json').write_text(json.dumps(usage,indent=2)+'\n')
        (output/'score-original.json').write_bytes((dataset/'score.json').read_bytes());(output/'manifest-original.json').write_bytes(manifests[0].read_bytes())
        with (output/'facts.csv').open('w') as file:
            writer=csv.DictWriter(file,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
        shutil.copyfile(archive,output/'original-artifact.zip')
        return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--source-report',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--study',choices=['PA','PC'],required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    summary=export(args.archive,args.sha256,args.source_report,args.protocol,args.study,args.output);print(json.dumps(summary))

if __name__=='__main__':main()
