#!/usr/bin/env python3
"""Fixed-load PC resource figures, per-block values without significance claims."""
import argparse
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from summarize_platform_resource import summarize

COLORS={1:'#235A91',2:'#C87924'}


def plot(report,output):
    summary=summarize(report)
    if not summary['complete_comparison_blocks']:raise ValueError('Complete PC blocks required for paired resource plots')
    output.mkdir(parents=True,exist_ok=True);rows=summary['rows'];plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    conditions=['idle','cold_single','warm_single','four_sequential','four_concurrent'];labels=['Post-ready\nno task (5s)','First\ntask','After one\npriming task','Four tasks\nsequential','Four tasks\nconcurrent']
    metrics=[('task_phase_seconds','Phase wall time (s)'),('native_phase_cpu_seconds','Native phase CPU (core-s)'),('native_phase_peak_pss_mib','Native phase sampled peak PSS (MiB)')]
    fig,axes=plt.subplots(2,3,figsize=(15,8))
    for pi,product in enumerate(('DSH','OpenClaw')):
        for mi,(metric,title) in enumerate(metrics):
            ax=axes[pi,mi]
            for block in (1,2):
                by={r['condition']:r for r in rows if r['product']==product and r['block']==block};x=[i+(-.06 if block==1 else .06) for i in range(5)];y=[by[c][metric] for c in conditions]
                ax.scatter(x,y,color=COLORS[block],s=36,label='Block '+str(block),zorder=4)
                ax.plot(x[3:],y[3:],color=COLORS[block],alpha=.7,lw=1)
            ax.set_xticks(range(5),labels,fontsize=8);ax.set_ylim(bottom=0,top=ax.get_ylim()[1]*1.12);ax.grid(axis='y',alpha=.2);ax.set_title(product+' · '+title,loc='left',fontsize=10,fontweight='bold')
            if mi==0:ax.legend(frameon=False,fontsize=9)
    fig.suptitle('Native service lifecycle/resource phases: two complete formal blocks',x=.05,ha='left',fontsize=15,fontweight='bold')
    fig.text(.03,.015,'Scripted provider, fixed 250 ms response delay; OS caches retained. Row axes are independently scaled. Post-ready no-task window includes native background initialization.\nWarm phases exclude accepted priming work; full lifecycle totals retain it. PSS and integrated RSS are separate measures. Observer/model fixture are outside native cgroups.',fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.95));fig.savefig(output/'resource-phases.png',dpi=180);fig.savefig(output/'resource-phases.svg');plt.close(fig)

    metrics=[('task_phase_seconds','Four-task wall (s)'),('native_phase_cpu_seconds','Native CPU (core-s)'),('native_phase_rss_mib_seconds','Sampled RSS integral (MiB·s)')]
    fig,axes=plt.subplots(2,3,figsize=(13,7))
    for pi,product in enumerate(('DSH','OpenClaw')):
        for mi,(metric,title) in enumerate(metrics):
            ax=axes[pi,mi]
            for block in (1,2):
                by={r['condition']:r for r in rows if r['product']==product and r['block']==block};values=[by[c][metric] for c in ('four_sequential','four_concurrent')]
                ax.plot([0,1],values,'o-',color=COLORS[block],label='B'+str(block),lw=1.5,markersize=5)
                for x,y in enumerate(values):ax.annotate(f'{y:.3f}' if y<10 else f'{y:.0f}',(x,y),xytext=(7,5 if block==1 else -12),textcoords='offset points',fontsize=8,color=COLORS[block])
            ax.set_xticks([0,1],['Sequential','Concurrent']);ax.set_xlim(-.17,1.3);ax.set_ylim(bottom=0,top=ax.get_ylim()[1]*1.15);ax.grid(axis='y',alpha=.2);ax.set_title(product+' · '+title,loc='left',fontsize=10,fontweight='bold')
            if mi==0:ax.legend(frameon=False,fontsize=9)
    fig.suptitle('Equal accepted work: four native sessions on one primed service',x=.05,ha='left',fontsize=15,fontweight='bold')
    fig.text(.03,.015,'Every point is 4/4 accepted tasks; lines pair independent formal blocks. Both products reached four overlapping task-model requests in concurrent arms.\nOpenClaw block 1 is a valid slower/higher-CPU concurrent result. No repeat was used to remove it. RSS integral is whole-service residency, not exact per-agent memory.',fontsize=9)
    fig.tight_layout(rect=(0,.10,1,.95));fig.savefig(output/'four-task-pairs.png',dpi=180);fig.savefig(output/'four-task-pairs.svg');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes();plot(json.loads(gzip.decompress(raw) if args.report.suffix=='.gz' else raw),args.output)

if __name__=='__main__':main()
