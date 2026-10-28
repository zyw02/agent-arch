#!/usr/bin/env python3
"""Evidence-linked CTX-01 metrics and paired effect plots; preserve null observability."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from export_read_metrics import normalized_usage,request_stage

LABELS={'ample_skill':'Ample + skill','ample_no_skill':'Ample','tight_skill':'Tight + skill','tight_no_skill':'Tight','tight_required_no_skill':'Tight + required'}


def metrics(report):
    rows=[];requests=[]
    for result in report['results']:
        resource=result['resources'];group=resource['cgroup'];cpu=group.get('cpu',{});usage=result['token_usage']
        usage_rows=usage.get('requests',[]);raw_requests=result['provider_requests'];normalized=[]
        for index,request in enumerate(raw_requests):
            accounting=usage_rows[index] if index<len(usage_rows) else {}
            norm=normalized_usage(request['endpoint'],accounting['usage']) if accounting.get('usage') else None
            if norm is not None:normalized.append(norm)
            requests.append(dict(product=result['product'],block=result['block'],condition=result['condition']['id'],index=index,
                stage=request_stage(request),endpoint=request['endpoint'],synthetic=not result['live_model'],
                raw_usage=accounting.get('usage'),normalized_usage=norm,complete=accounting.get('complete'),
                model=request['request'].get('model'),thinking=request['request'].get('thinking'),
                request_sha256=hashlib.sha256(json.dumps(request['request'],sort_keys=True).encode()).hexdigest()))
        all_usage=bool(usage_rows) and len(usage_rows)==len(raw_requests)==len(normalized) and all(u.get('complete') for u in usage_rows)
        total=sum(v['input_tokens']+v['output_tokens'] for v in normalized) if normalized else None
        initial=resource['disk_initial']['allocated_bytes'];peak=resource.get('disk_peak_allocated_bytes');observed=result['observed']
        rows.append(dict(product=result['product'],block=result['block'],condition=result['condition']['id'],sequence=result['sequence'],
            live_model=result['live_model'],delivered=result['delivered'],quality_correct=result['quality_correct'],constraints_satisfied=result['constraints_satisfied'],
            input_rule_visible=observed['rule_visible_initial'],skill_catalog_visible=observed['skill_catalog_visible'],native_skill_load=observed['native_skill_load_attempt'],rule_adopted_from_tool=observed['rule_adopted_from_tool'],
            resources_complete=resource['complete'],calibration_valid=result['calibration_valid'],adapter_error=result['adapter_error'],
            independent_delivery_seconds=result['independent_delivery_check_ms']/1000,process_exit_seconds=result['process_exit_ms']/1000,
            known_real_provider_tokens=total,usage_complete=all_usage,
            known_real_input_tokens=sum(v['input_tokens'] for v in normalized) if normalized else None,
            known_real_output_tokens=sum(v['output_tokens'] for v in normalized) if normalized else None,
            known_cache_hit_input_tokens=sum(v['cache_hit_input_tokens'] for v in normalized) if normalized and all(v['cache_hit_input_tokens'] is not None for v in normalized) else None,
            provider_requests=result['provider_request_count'],cpu_core_seconds=cpu.get('usage_usec')/1e6 if 'usage_usec' in cpu else None,
            observer_cpu_seconds=result['observer_process_cpu_seconds'],
            observer_memory_reader_cpu_seconds=result.get('observer_memory_reader_cpu_seconds'),
            observer_total_cpu_seconds=result['observer_process_cpu_seconds']+result['observer_memory_reader_cpu_seconds'] if result.get('observer_memory_reader_cpu_seconds') is not None else None,sampled_peak_pss_bytes=resource.get('sampled_peak_pss_bytes'),kernel_memory_peak_bytes=group.get('memory_peak_bytes'),
            sampled_peak_disk_increment_bytes=peak-initial if peak is not None else None,retained_disk_increment_bytes=resource.get('retained_incremental_allocated_bytes'),
            initial_context_text_bytes=result['context_payload_bytes']['initial_text_utf8'],invoice_charge=None,run_id=report['run_id']))
    return rows,requests


def contrasts(rows):
    result=[]
    comparisons=[('skill_at_tight','tight_skill','tight_no_skill'),('skill_at_ample','ample_skill','ample_no_skill'),
        ('restore_instruction_budget','ample_no_skill','tight_no_skill'),('required_keyword','tight_required_no_skill','tight_no_skill')]
    for product in ('DSH','OpenClaw'):
        for block in sorted({r['block'] for r in rows if r['product']==product}):
            by_id={r['condition']:r for r in rows if r['product']==product and r['block']==block}
            for name,treated,control in comparisons:
                if treated not in by_id or control not in by_id:raise ValueError('Incomplete native comparison block')
                a,b=by_id[treated],by_id[control]
                row=dict(product=product,block=block,contrast=name,treated=treated,control=control)
                for field in ('quality_correct','input_rule_visible','independent_delivery_seconds','known_real_provider_tokens','cpu_core_seconds','sampled_peak_pss_bytes','sampled_peak_disk_increment_bytes'):
                    row['delta_'+field]=a[field]-b[field] if a[field] is not None and b[field] is not None else None
                result.append(row)
            if len(by_id)!=5:raise ValueError('Expected all five predeclared conditions')
            result.append(dict(product=product,block=block,contrast='quality_skill_by_budget_interaction',
                delta_quality_correct=int(by_id['tight_skill']['quality_correct'])-int(by_id['tight_no_skill']['quality_correct'])-int(by_id['ample_skill']['quality_correct'])+int(by_id['ample_no_skill']['quality_correct'])))
    return result


def plot(rows,report,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    conditions=list(LABELS);products=('DSH','OpenClaw')
    fig,axes=plt.subplots(1,2,figsize=(13,4.7),layout='constrained')
    columns=[('input_rule_visible','Rule in initial\nrequest'),('native_skill_load','Native skill\nload'),('rule_adopted_from_tool','Rule from tool\nin next request'),('quality_correct','Exact task\nresult')]
    for axis,product in zip(axes,products):
        selected=[r for r in rows if r['product']==product];matrix=[];counts=[]
        for condition in conditions:
            part=[r for r in selected if r['condition']==condition]
            matrix.append([sum(bool(r[key]) for r in part)/len(part) if part else float('nan') for key,label in columns]);counts.append(len(part))
        axis.imshow(np.array(matrix),cmap='Blues',vmin=0,vmax=1,aspect='auto')
        for i,line in enumerate(matrix):
            for j,value in enumerate(line):axis.text(j,i,f'{round(value*counts[i])}/{counts[i]}' if counts[i] else 'N/A',ha='center',va='center',color='white' if value>.5 else 'black')
        axis.set_xticks(range(4),[label for key,label in columns]);axis.set_yticks(range(5),[LABELS[c] for c in conditions]);axis.set_title(product)
    fig.suptitle('CTX-01: native context route and exact task result — two held-out paired blocks\nCounts are observed trials, not population estimates; redundant rule supplied by design',fontsize=11)
    fig.savefig(output/'context-skill-mechanism.svg');fig.savefig(output/'context-skill-mechanism.png',dpi=145);plt.close(fig)
    dimensions=[('independent_delivery_seconds','Independent delivery check (s)',1),('known_real_provider_tokens','Actual input + output tokens',1),('cpu_core_seconds','Product CPU (core-seconds)',1),('sampled_peak_pss_bytes','Sampled process PSS peak (MiB)',1024**2),('sampled_peak_disk_increment_bytes','Sampled disk increment peak (MiB)',1024**2),('observer_total_cpu_seconds','Observer + relay CPU (seconds)',1)]
    fig,axes=plt.subplots(2,6,figsize=(19,7.8),layout='constrained')
    for row,product in enumerate(products):
        selected=[r for r in rows if r['product']==product]
        for col,(key,label,scale) in enumerate(dimensions):
            axis=axes[row,col]
            for block in sorted({r['block'] for r in selected}):
                part={r['condition']:r for r in selected if r['block']==block}
                points=[(i,part[c][key]/scale) for i,c in enumerate(conditions) if c in part and part[c][key] is not None]
                axis.plot([p[0] for p in points],[p[1] for p in points],marker='o',linewidth=1,label='block '+str(block),alpha=.8)
            axis.set_xticks(range(5),['A+S','A','T+S','T','T+R'],rotation=35);axis.set_title(product+'\n'+label,fontsize=9);axis.grid(axis='y',alpha=.2);axis.set_ylim(bottom=0)
            if col==0:axis.legend(fontsize=8)
    fig.suptitle('CTX-01: all native task points retained, including missing-rule deliveries\nA=ample; T=tight; S=native skill available; R=Required keyword. Within-product paired observations; cold invocations; no general product ranking.',fontsize=11)
    fig.savefig(output/'context-skill-resources.svg');fig.savefig(output/'context-skill-resources.png',dpi=145);plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');args=p.parse_args()
    raw=args.report.read_bytes();report=json.loads(raw);rows,requests=metrics(report);pairs=contrasts(rows);args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'context-skill-metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    (args.output/'context-skill-request-usage.json').write_text(json.dumps(dict(run_id=report['run_id'],report_sha256=hashlib.sha256(raw).hexdigest(),requests=requests),indent=2)+'\n')
    (args.output/'context-skill-paired-effects.json').write_text(json.dumps(dict(protocol_sha256=report['protocol_sha256'],report_sha256=hashlib.sha256(raw).hexdigest(),contrasts=pairs,
        interpretation='Constructed rule redundancy and explicit catalog loading. No population-level inference from two blocks. Actual invoice cost and context-source token counts remain unknown.'),indent=2)+'\n')
    if args.plot:plot(rows,report,args.output)
    print(json.dumps(dict(rows=len(rows),requests=len(requests),exact=sum(r['quality_correct'] for r in rows),delivered=sum(r['delivered'] for r in rows),usage_complete=all(r['usage_complete'] for r in rows))))

if __name__=='__main__':main()
