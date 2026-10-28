#!/usr/bin/env python3
"""PA descriptive formal outcomes and native lifecycle timeline, no execution."""
import argparse
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
from summarize_platform_fault import summarize


def plot(report,output):
    summary=summarize(report)
    if not summary['complete_comparison_blocks']:raise ValueError('Refusing paired plots for incomplete blocks')
    output.mkdir(parents=True,exist_ok=True);rows=summary['rows'];groups=[(p,c) for p in ('DSH','OpenClaw') for c in ('healthy','client_exit','owner_exit')]
    metrics=[('primary_client_received_ack','Primary client\nreceived ACK'),('companion_client_received_ack','Companion client\nreceived ACK'),
        ('primary_restart_later_user_retained','Primary input\nretained'),('companion_restart_later_user_retained','Companion input\nretained'),
        ('primary_restart_later_ack','Primary old ACK\nafter restart'),('companion_restart_later_ack','Companion old ACK\nafter restart'),
        ('primary_original_requests_after_restart_before_followup','Primary original\nrequest reissued\nbefore new prompt'),('primary_new_followup_ack','New primary\nprompt ACK')]
    grid=np.full((len(groups),len(metrics)),np.nan);labels={}
    for i,(p,c) in enumerate(groups):
        group=[r for r in rows if (r['product'],r['condition'])==(p,c)]
        for j,(key,label) in enumerate(metrics):
            known=[r[key] for r in group if r[key] is not None];count=sum(bool(v) for v in known)
            grid[i,j]=count/len(known) if known else np.nan;labels[i,j]=str(count)+'/'+str(len(group))+(' *' if len(known)!=len(group) else '')
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(14,5.3));ax.imshow(grid,vmin=0,vmax=1,cmap='Blues',aspect='auto')
    for (i,j),label in labels.items():ax.text(j,i,label,ha='center',va='center',color='white' if grid[i,j]>.5 else '#152332',fontsize=12)
    ax.set_xticks(range(len(metrics)),[m[1] for m in metrics]);ax.set_yticks(range(len(groups)),[p+' · '+c.replace('_',' ') for p,c in groups]);ax.tick_params(length=0)
    ax.set_title('Public HTTP fault domains: observed event counts per complete condition',loc='left',pad=18,fontweight='bold');ax.axhline(2.5,color='white',lw=3)
    fig.text(.02,.02,'Counts are occurrences, not pass/fail scores. Client loss can prevent receipt while work persists. Old ACK/reissue cut: before new prompts.\nTwo formal blocks per product/condition; scripted provider. Pilot excluded. * marks an unavailable native-history observation.',fontsize=9)
    fig.tight_layout(rect=(0,.12,1,1));fig.savefig(output/'fault-outcomes.png',dpi=180);fig.savefig(output/'fault-outcomes.svg');plt.close(fig)

    arms=sorted(report['results'],key=lambda r:(('DSH','OpenClaw').index(r['product']),('healthy','client_exit','owner_exit').index(r['condition']),r['block']))
    fig,ax=plt.subplots(figsize=(13,7));left=0;right=0
    for index,arm in enumerate(arms):
        origin=arm['boundary_ns'];t=lambda value:(value-origin)/1e9
        for n,cycle in enumerate(arm['cycles']):
            a=t(cycle['resources']['started_ns']);b=t(cycle['resources']['ended_ns']);left=min(left,a);right=max(right,b)
            live_end=t(arm['intervention']['delivered_ns']) if n==0 and arm['condition']=='owner_exit' else b
            ax.broken_barh([(a,live_end-a)],(index-.28,.56),facecolors=('#B6C4D4' if n==0 else '#6B91B5'),alpha=.8)
            if live_end<b:ax.broken_barh([(live_end,b-live_end)],(index-.28,.56),facecolors='white',edgecolors='#B6C4D4',hatch='///')
        for role,offset in [('primary',-.1),('companion',.1)]:
            for event in arm['clients'][role]['events']:
                if event.get('kind')=='terminal' and event['result'].get('accepted'):ax.scatter(t(event['ns']),index+offset,marker='o',s=30,color='#208456',edgecolors='white',zorder=5)
        original_markers={task['marker'] for task in arm['tasks'].values()}
        for event in arm['boundary_ledger']:
            if not event['title'] and event['marker'] in original_markers and arm.get('restart_requested_ns',float('inf'))<=event['received_ns']:
                after_cut=event['received_ns']>=arm.get('followup_started_ns',float('inf'))
                ax.scatter(t(event['received_ns']),index,marker='^',s=46,facecolors='none' if after_cut else '#7A41B4',edgecolors='#7A41B4',zorder=6)
        ax.scatter(t(arm['followup_started_ns']),index,marker='x',s=40,color='#002E54',zorder=6)
    ax.axvline(0,color='#A32936',lw=1.3);ax.set_xlim(left-1,right+1);ax.set_yticks(range(len(arms)),[r['product']+' · '+r['condition'].replace('_',' ')+' · B'+str(r['block']) for r in arms]);ax.invert_yaxis();ax.grid(axis='x',alpha=.2);ax.set_xlabel('Seconds relative to matched admitted-request boundary / intervention')
    ax.set_title('Native collection intervals, response receipt and restart work',loc='left',fontweight='bold',pad=15)
    ax.legend(handles=[Patch(color='#B6C4D4',label='First native service collection'),Patch(color='#6B91B5',label='New carrier, same native state'),Patch(facecolor='white',edgecolor='#B6C4D4',hatch='///',label='Post-owner-exit observation until cleanup'),
        Line2D([],[],marker='o',color='none',markerfacecolor='#208456',label='Client accepted original ACK'),Line2D([],[],marker='^',color='none',markerfacecolor='#7A41B4',label='Original request: before new followup'),Line2D([],[],marker='^',color='none',markerfacecolor='none',markeredgecolor='#7A41B4',label='Original request: after new followup begins'),Line2D([],[],marker='x',color='#002E54',linestyle='none',label='New followups begin')],loc='upper center',bbox_to_anchor=(.5,-.11),ncol=3,frameon=False,fontsize=9)
    fig.tight_layout(rect=(0,.07,1,1));fig.savefig(output/'fault-lifecycle.png',dpi=180);fig.savefig(output/'fault-lifecycle.svg');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();raw=args.report.read_bytes()
    plot(json.loads(gzip.decompress(raw) if args.report.suffix=='.gz' else raw),args.output)

if __name__=='__main__':main()
