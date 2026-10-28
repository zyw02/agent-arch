#!/usr/bin/env python3
"""Export native read pilot data; missing counters stay null, samples stay distinct."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def request_stage(request):
    body=request['request'];messages=body.get('messages',[])
    if not body.get('tools') and 'Generate the session title from this JSON array' in json.dumps(messages):return 'auxiliary_session_title'
    has_result=any(m.get('role')=='tool' or (isinstance(m.get('content'),list) and any(b.get('type')=='tool_result' for b in m['content'] if isinstance(b,dict))) for m in messages)
    return 'task_tool_followup' if has_result else 'task_initial'


def normalized_usage(endpoint,usage):
    if endpoint.endswith('/messages'):
        required=('input_tokens','cache_creation_input_tokens','cache_read_input_tokens','output_tokens')
        if not all(isinstance(usage.get(k),int) for k in required):return None
        # Anthropic input_tokens excludes the separately reported cache reads/writes.
        return dict(input_tokens=sum(usage[k] for k in required[:3]),output_tokens=usage['output_tokens'],
            cache_hit_input_tokens=usage['cache_read_input_tokens'],cache_created_input_tokens=usage['cache_creation_input_tokens'])
    if not all(isinstance(usage.get(k),int) for k in ('prompt_tokens','completion_tokens')):return None
    inclusive=usage['prompt_tokens'];output=usage['completion_tokens']
    if 'total_tokens' in usage and usage['total_tokens']!=inclusive+output:raise ValueError('Inclusive provider total disagrees')
    cached=usage.get('prompt_cache_hit_tokens',usage.get('prompt_tokens_details',{}).get('cached_tokens'))
    if 'prompt_cache_miss_tokens' in usage and cached is not None and cached+usage['prompt_cache_miss_tokens']!=inclusive:raise ValueError('Cache partition disagrees')
    return dict(input_tokens=inclusive,output_tokens=output,cache_hit_input_tokens=cached,cache_created_input_tokens=None)


def export(report):
    arms=[];requests=[]
    for result in report['results']:
        resources=result['resources'];group=resources['cgroup'];cpu=group.get('cpu',{})
        peak=resources.get('disk_peak_allocated_bytes');initial=resources['disk_initial']['allocated_bytes']
        arms.append(dict(product=result['product'],route=result['route'],phase=result['phase'],
            accepted=result.get('revalidated_valid',result['valid']),original_acceptance=result['valid'],resources_complete=result['resource_collection_valid'],
            invocation_wall_seconds=result['invocation_wall_ms']/1000,cpu_core_seconds=cpu.get('usage_usec',0)/1e6 if 'usage_usec' in cpu else None,
            cpu_user_seconds=cpu.get('user_usec',0)/1e6 if 'user_usec' in cpu else None,
            cpu_system_seconds=cpu.get('system_usec',0)/1e6 if 'system_usec' in cpu else None,
            sampled_peak_pss_bytes=resources.get('sampled_peak_pss_bytes'),sampled_peak_rss_sum_bytes=resources.get('sampled_peak_rss_sum_bytes'),
            kernel_cgroup_memory_peak_bytes=group.get('memory_peak_bytes'),
            sampled_peak_disk_increment_bytes=peak-initial if peak is not None else None,
            retained_disk_increment_bytes=resources.get('retained_incremental_allocated_bytes'),
            provider_requests=result['provider_request_count'],paid_model_calls=result['paid_model_calls'],
            known_real_provider_tokens=None,invoice_charge=None,run_id=report['run_id']))
        usage=result['token_usage'];indexed={v['request_index']:v for v in usage.get('requests',[])}
        normalized=[normalized_usage(v['endpoint'],v['usage']) for v in indexed.values() if v.get('complete')]
        if not usage['synthetic']:
            arms[-1]['known_real_provider_tokens']=sum(v['input_tokens']+v['output_tokens'] for v in normalized if v is not None)
            arms[-1]['usage_complete']=bool(indexed) and len(indexed)==result['provider_request_count'] and len(normalized)==len(indexed) and all(v is not None for v in normalized)
        else:arms[-1]['usage_complete']=False
        for index,request in enumerate(result.get('provider_requests',[])):
            body=request['request'];row=indexed.get(index,{})
            requests.append(dict(product=result['product'],route=result['route'],request_index=index,
                stage=request_stage(request),endpoint=request['endpoint'],model=body.get('model'),
                synthetic=usage['synthetic'],raw_usage=row.get('usage'),normalized_usage=normalized_usage(request['endpoint'],row['usage']) if row.get('usage') else None,usage_complete=row.get('complete'),
                http_status=request.get('http_status'),request_json_bytes=len(json.dumps(body).encode()),
                native_request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
                elapsed_seconds=(request['settled_ns']-request['monotonic_ns'])/1e9 if 'settled_ns' in request else None,
                tool_names=request.get('tool_names'),thinking=body.get('thinking'),output_config=body.get('output_config')))
    return arms,requests


def plot(report,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for row,product in enumerate(('DSH','OpenClaw')):
        for result in (r for r in report['results'] if r['product']==product):
            resource=result['resources'];samples=resource['samples'];start=resource['started_ns'];initial=resource['disk_initial']['allocated_bytes']
            for col,key,scale in [(0,'cpu',1e6),(1,'sampled_pss_bytes',1024**2),(2,'disk',1024**2)]:
                values=[s.get('cpu',{}).get('usage_usec') if col==0 else s.get(key) if col==1 else s['disk']['allocated_bytes']-initial for s in samples]
                valid=[(s['monotonic_ns'],value) for s,value in zip(samples,values) if value is not None]
                axes[row,col].plot([(t-start)/1e9 for t,v in valid],[v/scale for t,v in valid],label=result['route'])
                axes[row,col].set_xlabel('Seconds since observation started');axes[row,col].grid(alpha=.2)
        for col,label in enumerate(('Cumulative product CPU (core-seconds)','Sampled process PSS (MiB)','Task-path allocated increment (MiB)')):
            axes[row,col].set_title(product+' / '+label);axes[row,col].legend()
    kind='Live DeepSeek read pilot' if report.get('live_model_pilot') else 'Synthetic-provider read calibration'
    fig.suptitle(kind+' — one observation per route; run '+report['run_id']+'\nProfiles/protocols/thinking differ; fixed order; no product ranking or significance claim',fontsize=11)
    fig.savefig(output/'read-resource-timeline.svg');fig.savefig(output/'read-resource-timeline.png',dpi=140);plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');a=p.parse_args()
    raw=a.report.read_bytes();report=json.loads(raw);arms,requests=export(report);a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'read-resource-metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(arms[0]),lineterminator='\n');writer.writeheader();writer.writerows(arms)
    (a.output/'read-request-usage.json').write_text(json.dumps(dict(report_sha256=hashlib.sha256(raw).hexdigest(),run_id=report['run_id'],requests=requests,
        counter_rule='Raw request counters, including auxiliary work and failures. Inclusive/cache/reasoning fields not blindly summed across protocols.',
        component_token_attribution='Unobserved; source payload bytes must not be labeled tokens.'),indent=2)+'\n')
    if a.plot:plot(report,a.output)
    print(json.dumps(arms))

if __name__=='__main__':main()
