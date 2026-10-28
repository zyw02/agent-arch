#!/usr/bin/env python3
"""Visualize original answers alongside the separately labeled informed audit."""
import argparse
from collections import Counter
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(pa,pc,output):
    categories=[('native_state','Matching native state/count','#328377'),('inference','Matching component-link inference','#4878aa'),
        ('unsupported','Matching value, support incomplete','#ddad48'),('incorrect','Incorrect value','#c85b5d'),
        ('unknown','Unknown','#aeb7c1'),('inapplicable','Inapplicable','#e2e6eb')]
    mapping={'native_snapshot_or_explicit_state_evidence':'native_state','native_terminal_ACK_count_supported':'native_state',
        'native_service_execution_link_inference':'inference','matching_value_but_actual_model_request_absence_unproven':'unsupported',
        'matching_condition_label_but_OS_client_death_unproven':'unsupported','incorrect_observation_cut':'incorrect',
        'incorrect_fault_attribution':'incorrect','unknown_retained':'unknown','idle_ownership_unscorable':'inapplicable'}
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,1,figsize=(12,6.5))
    for ax,audit,title in zip(axes,(pa,pc),('PA: 6 questions × 6 cases per product','PC: 3 questions × 10 cases per product (secondary analysis)')):
        for y,product in enumerate(('DSH','OpenClaw')):
            counts=Counter(mapping[r['support']] for r in audit['rows'] if r['product']==product);left=0
            for key,label,color in categories:
                count=counts[key]
                if count:
                    ax.barh(y,count,left=left,color=color,height=.48,edgecolor='white',linewidth=1)
                    ax.text(left+count/2,y,str(count),ha='center',va='center',fontsize=11)
                    left+=count
        ax.set_yticks([0,1],['DSH','OpenClaw']);ax.invert_yaxis();ax.set_xlim(0,left);ax.set_xticks(range(0,left+1,6));ax.set_xlabel('Question-level fact count');ax.set_title(title,loc='left',fontweight='bold',fontsize=11)
        ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0)
    handles=[plt.Rectangle((0,0),1,1,color=color) for _,_,color in categories]
    fig.legend(handles,[label for _,label,_ in categories],loc='lower center',bbox_to_anchor=(.51,.07),ncol=3,frameon=False,fontsize=9)
    fig.suptitle('One isolated automated investigator of selected native records',x=.07,ha='left',fontsize=14,fontweight='bold')
    fig.text(.07,.015,'Original answer values remain unchanged. Support categories are an informed post-review audit, not another blind review.\nDifferent questions and native surfaces; no aggregate product ranking. Unknowns and incorrect answers were not retried.',fontsize=9)
    fig.tight_layout(rect=(.02,.19,1,.94));output.mkdir(parents=True,exist_ok=True)
    fig.savefig(output/'native-review-audit.png',dpi=180);fig.savefig(output/'native-review-audit.svg');plt.close(fig)


def main():
    p=argparse.ArgumentParser();p.add_argument('--pa-audit',type=Path,required=True);p.add_argument('--pc-audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    plot(json.loads(args.pa_audit.read_bytes()),json.loads(args.pc_audit.read_bytes()),args.output)


if __name__=='__main__':main()
