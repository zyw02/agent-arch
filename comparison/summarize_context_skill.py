#!/usr/bin/env python3
"""Offline retained-evidence checks and descriptive CTX summaries; no new judgments."""
import argparse
import hashlib
import json
from pathlib import Path
from context_skill_probe import encoded,parse_delivery
from export_context_skill import metrics


def native_task_tokens(result):
    if result['product']=='OpenClaw':return result.get('native_metadata',{}).get('agentMeta',{}).get('usage',{}).get('total')
    events=[]
    for line in result['stdout'].splitlines():
        try:events.append(json.loads(line))
        except ValueError:continue
    steps=[e['usage'] for e in events if e.get('type')=='status' and e.get('phase')=='step_end' and 'usage' in e]
    if not steps or any('totalTokens' not in u for u in steps):return None
    return sum(u['totalTokens'] for u in steps)


def summarize(report,calibration,protocol,protocol_bytes):
    digest=hashlib.sha256(protocol_bytes).hexdigest()
    if report['protocol_sha256']!=digest or calibration['protocol_sha256']!=digest:raise ValueError('Protocol digest differs')
    if report['study_id']!=protocol['study_id'] or report['live_model'] is not True or calibration['live_model'] is not False:raise ValueError('Study identity differs')
    conditions={c['id'] for c in protocol['conditions']};products=set(protocol['products']);blocks=protocol['real_model_blocks']
    expected={(p,b,c) for p in products for b in range(1,blocks+1) for c in conditions}
    actual=[(r['product'],r['block'],r['condition']['id']) for r in report['results']]
    if set(actual)!=expected or len(actual)!=len(expected):raise ValueError('Incomplete or repeated study arms')
    controls=[(r['product'],r['block'],r['condition']['id']) for r in calibration['results']]
    expected_controls={(p,b,c) for p in products for b in range(1,protocol['calibration_blocks']+1) for c in conditions}
    if set(controls)!=expected_controls or len(controls)!=len(expected_controls) or not all(r['calibration_valid'] for r in calibration['results']):raise ValueError('Complete calibration gate required')
    for result in report['results']:
        delivery=parse_delivery(result['product'],result['stdout'])
        correct=delivery is not None and delivery['encoded']==encoded(result['rule'],result['task_values'])
        if delivery!=result['delivery'] or correct!=result['quality_correct']:raise ValueError('Original terminal judgment differs')
    rows,requests=metrics(report);accounting=[];grouped=[]
    for result in report['results']:
        part=[r for r in requests if (r['product'],r['block'],r['condition'])==(result['product'],result['block'],result['condition']['id'])]
        task=[r for r in part if r['stage']!='auxiliary_session_title'];aux=[r for r in part if r['stage']=='auxiliary_session_title']
        complete=all(r['complete'] and r['normalized_usage'] is not None for r in task) and bool(task)
        provider=sum(r['normalized_usage']['input_tokens']+r['normalized_usage']['output_tokens'] for r in task) if complete else None
        native=native_task_tokens(result)
        accounting.append(dict(product=result['product'],block=result['block'],condition=result['condition']['id'],native_task_tokens=native,
            provider_task_tokens=provider,totals_agree=native==provider if native is not None and provider is not None else None,
            auxiliary_requests=len(aux),auxiliary_tokens=sum(r['normalized_usage']['input_tokens']+r['normalized_usage']['output_tokens'] for r in aux) if all(r['complete'] and r['normalized_usage'] is not None for r in aux) else None))
    for product in protocol['products']:
        for condition in protocol['conditions']:
            part=[r for r in rows if r['product']==product and r['condition']==condition['id']]
            grouped.append(dict(product=product,condition=condition['id'],independent_blocks=len(part),
                delivered=sum(r['delivered'] for r in part),exact=sum(r['quality_correct'] for r in part),
                constraints_satisfied=sum(r['constraints_satisfied'] is True for r in part),constraints_unobserved=sum(r['constraints_satisfied'] is None for r in part),
                full_success=sum(r['delivered'] and r['quality_correct'] and r['constraints_satisfied'] is True for r in part),
                initial_rule_visible=sum(r['input_rule_visible'] for r in part),skill_load_attempts=sum(r['native_skill_load'] for r in part),
                rule_in_tool_followup=sum(r['rule_adopted_from_tool'] for r in part),
                **{key:[r[key] for r in sorted(part,key=lambda r:r['block'])] for key in ('known_real_provider_tokens','independent_delivery_seconds','cpu_core_seconds','sampled_peak_pss_bytes','sampled_peak_disk_increment_bytes','observer_total_cpu_seconds')}))
    return dict(study_id=report['study_id'],protocol_sha256=digest,run_id=report['run_id'],controller_commit=report['controller_commit'],
        blocks=blocks,arms=len(rows),calibration_controls=len(controls),provider_calls=len(requests),provider_errors=sum(len(r.get('provider_errors',[])) for r in report['results']),
        adapter_errors=sum(r['adapter_error'] is not None for r in report['results']),resources_complete=sum(r['resources_complete'] for r in rows),usage_complete=sum(r['usage_complete'] for r in rows),
        delivered=sum(r['delivered'] for r in rows),exact=sum(r['quality_correct'] for r in rows),
        full_success=sum(r['delivered'] and r['quality_correct'] and r['constraints_satisfied'] is True for r in rows),rows=grouped,native_provider_accounting=accounting,
        interpretation='Every original judgment retained and terminal oracle independently recomputed. Two constructed matched blocks support bounded mechanism observations. Null is a delivered incomplete answer, including expected missing-parameter controls. Full acceptance additionally requires task constraints. No broad product ranking, hard task-tree quota, full compaction, independent component token count or invoice-cost claim.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    raw=args.protocol.read_bytes();result=summarize(json.loads(args.report.read_bytes()),json.loads(args.calibration.read_bytes()),json.loads(raw),raw)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','native_provider_accounting')}))

if __name__=='__main__':main()
