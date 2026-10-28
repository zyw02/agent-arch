#!/usr/bin/env python3
"""Show every paired HD normal-route value and independent cancellation witness."""
import argparse
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from summarize_tool_lifecycle import summarize

COLORS={1:'#235A91',2:'#C87924'}


def save(fig,output,name):
    fig.savefig(output/(name+'.png'),dpi=180);fig.savefig(output/(name+'.svg'));plt.close(fig)


def plot(report,protocol,output):
    summary=summarize(report,protocol)
    if not summary['complete_comparison_blocks'] or not summary['healthy_controls_passed']:raise ValueError('Complete HD blocks and healthy controls required for paired plots')
    output.mkdir(parents=True,exist_ok=True);rows=summary['rows'];blocks=sorted({r['block'] for r in rows});plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    conditions=['native_single','mcp_single','mcp_four_serial','mcp_four_batch'];labels=['Native\nsingle','MCP\nsingle','MCP four\nserial','MCP four\nbatch']
    metrics=[('independent_delivery_check_seconds','Ready-task to verified delivery (s)'),('native_case_phase_cpu_seconds','Native case CPU (core-s)'),('native_case_phase_rss_mib_seconds','Sampled RSS integral (MiB·s)')]
    fig,axes=plt.subplots(2,3,figsize=(14,8))
    for pi,product in enumerate(('DSH','OpenClaw')):
        for mi,(metric,title) in enumerate(metrics):
            ax=axes[pi,mi]
            for block in blocks:
                by={r['condition']:r for r in rows if r['product']==product and r['block']==block};x=[i+(-.04 if block==1 else .04) for i in range(4)];y=[by[c][metric] for c in conditions]
                ax.scatter(x,y,color=COLORS[block],s=35,label='Block '+str(block),zorder=4);ax.plot(x[2:],y[2:],color=COLORS[block],alpha=.6)
                for index in (2,3):ax.annotate(f'{y[index]:.3f}' if y[index]<10 else f'{y[index]:.0f}',(x[index],y[index]),xytext=(4,5 if block==1 else -12),textcoords='offset points',fontsize=8,color=COLORS[block])
            ax.set_xticks(range(4),labels,fontsize=9);ax.set_ylim(bottom=0,top=ax.get_ylim()[1]*1.13);ax.grid(axis='y',alpha=.2);ax.set_title(product+' · '+title,loc='left',fontsize=10,fontweight='bold')
            if mi==0:ax.legend(frameon=False,fontsize=9)
    fig.suptitle('Native tool routes and equal four-read work: '+report['phase']+' observations',x=.04,ha='left',fontsize=14,fontweight='bold')
    fig.text(.025,.015,'Independent random files; single reads have no intentional delay. Each serial/batch read has the same 250 ms fixture delay. Lines pair equal four-read work.\nFresh service/state per point; shared installation and OS caches retained. Row scales differ. Native context, provider protocol and route responsibilities differ.\nMCP fixture is inside product cgroup; model/controller and memory reader are outside. Scripted counters are not real tokens or invoice cost.',fontsize=9)
    fig.tight_layout(rect=(0,.11,1,.95));save(fig,output,'read-routes')

    cancel_arms=[a for a in report['results'] if a['condition']=='mcp_batch_cancel'];fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    for pi,product in enumerate(('DSH','OpenClaw')):
        ax=axes[pi]
        for arm in cancel_arms:
            if arm['product']!=product:continue
            block=arm['block'];observations=arm['cancel_observations'];x=[o['offset_seconds'] for o in observations];active=[len(o['active_live_fixture_calls']) for o in observations];consumer=[int(o['native_task_consumer_alive']) for o in observations]
            ax.plot(x,active,'o-',color=COLORS[block],label=f'B{block}: live fixture calls');ax.plot(x,consumer,'x--',color=COLORS[block],label=f'B{block}: native result consumer')
        ax.set_xticks([.5,2,10]);ax.set_ylim(-.15,4.3);ax.set_yticks(range(5));ax.set_xlabel('Seconds after cancel API receipt');ax.set_title(product,loc='left',fontweight='bold');ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,fontsize=8)
    axes[0].set_ylabel('Count (consumer is 0/1)');fig.suptitle('Cancellation: actual held-work and result-consumer witnesses',x=.05,ha='left',fontsize=14,fontweight='bold')
    fig.text(.025,.02,'Index 2 is held before reading. Acknowledgment, native aborted terminal, effective cessation and fresh-session health are separately reported.\nCleanup release occurs after observation and returns an error without performing the held read. Counts combine call/stop receipts and live PID checks.',fontsize=9)
    fig.tight_layout(rect=(0,.14,1,.92));save(fig,output,'cancel-witnesses')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes()
    plot(json.loads(gzip.decompress(raw) if args.report.suffix=='.gz' else raw),args.protocol,args.output)

if __name__=='__main__':main()
