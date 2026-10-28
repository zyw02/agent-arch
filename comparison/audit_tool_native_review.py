#!/usr/bin/env python3
"""Informed HD packet/support audit, without repairing or rescoring answers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from review_platform_native import parse_answer,quote_exists,score


def resolve_path(value,path):
    if not isinstance(path,str):return None,None,None
    path=re.sub(r'^\$\.?','',path)
    if path.startswith('native_packet.'):path=path[len('native_packet.'):]
    parent=key=None
    try:
        for name,index in re.findall(r'([^.[\]]+)|\[([0-9]+)\]',path):
            parent=value;key=int(index) if index else name;value=value[key]
        return value,parent,key
    except (KeyError,IndexError,TypeError):return None,None,None


def descendant_quote(value,quote):
    if not isinstance(quote,str) or not quote:return False
    if isinstance(value,str):return quote in value
    if isinstance(value,dict):return any(descendant_quote(v,quote) for v in value.values())
    if isinstance(value,list):return any(descendant_quote(v,quote) for v in value)
    return False


def native_facts(packet,product):
    calls={};results={};final=[]
    if product=='DSH':
        for record in packet['native_history']['events']['records']:
            event=record.get('event',{});data=event.get('data',{})
            if event.get('type')=='tool/call':calls[data['callId']]=json.loads(data['arguments'])['index']
            elif event.get('type')=='tool/result':
                message=data['message'];results[message['toolCallId']]=message
            elif event.get('type')=='assistant/message':final.extend(b['text'] for b in data['message'].get('content',[]) if b.get('type')=='text')
    else:
        for message in packet['native_history']['history']['messages']:
            if message.get('role')=='toolResult':results[message['toolCallId']]=message
            elif message.get('role')=='assistant':
                for block in message.get('content',[]):
                    if block.get('type')=='toolCall':calls[block['id']]=block['arguments']['index']
                    elif block.get('type')=='text':final.append(block['text'])
    indexed={calls[identifier]:value for identifier,value in results.items() if identifier in calls}
    failures=[i for i,m in indexed.items() if m.get('isError') is True]
    failed=str(failures[0]) if len(failures)==1 else 'none' if set(indexed)=={0,1,2,3} and all(m.get('isError') is False for m in indexed.values()) else None
    prefix='TOOL_DONE:'+packet['task_identifiers']['task_marker']+':'
    endings=[text[len(prefix):] for text in final if text.startswith(prefix)];count=None
    if len(endings)==1:
        payload=json.loads(endings[0]);delivered=[]
        for key,value in payload.items():
            if key in ('0','1','2','3') and isinstance(value,str) and re.fullmatch(r'TOOL_VALUE_[a-f0-9]{32}',value) and value in json.dumps(indexed.get(int(key),{})):delivered.append(key)
        count=str(len(set(delivered)))
    return dict(failed_read_index=failed,delivered_value_count=count,visible_result_indexes=sorted(indexed))


def audit(dataset,reviews,protocol):
    original=json.loads((dataset/'score.json').read_bytes());recomputed=score(dataset,reviews,protocol)
    if recomputed!=original:raise ValueError('Original review scores changed')
    rows=[]
    for fact in original['rows']:
        case_id=fact['case_id'];packet=json.loads((dataset/'packets'/(case_id+'.json')).read_bytes());record=json.loads((reviews/(case_id+'.json')).read_bytes());answer=parse_answer(record)
        candidate=answer.get(fact['question'],{}) if isinstance(answer,dict) else {};item=candidate if isinstance(candidate,dict) else {};field=next((k for k in ('quote','exact_quote','exact quote') if k in item),None);quote=item.get(field) if field else None;path=item.get('evidence_path')
        value,parent,key=resolve_path(packet,path);direct=quote_exists(packet,path,quote);leaf=descendant_quote(value,quote)
        member=isinstance(value,bool) and isinstance(parent,dict) and key in parent and isinstance(quote,str) and quote in json.dumps({key:value})[1:-1]
        native=native_facts(packet,fact['product'])
        if fact['classification']=='invalid_answer':support='invalid_answer_preserved'
        elif fact['classification']=='unknown':support='unknown_retained_no_hidden_retry_evidence'
        elif fact['classification']=='correct':support='selected_native_packet_supports_value' if native.get(fact['question'])==fact['answer'] else 'matching_external_value_without_selected_native_support'
        else:support='original_wrong_value_preserved'
        rows.append(dict(**fact,support=support,native_packet_facts=native,original_reason=item.get('reason'),original_evidence_path=path,returned_quote_field=field,returned_quote=quote,
            secondary_alias_quote_at_original_path=direct,secondary_alias_quote_in_descendant_leaf=leaf,secondary_alias_quote_matches_json_member=member,
            citation_scope_note='Cited false flag covers one result; all four native result records are needed for the no-reported-failure answer' if fact['question']=='failed_read_index' and fact['answer']=='none' else None))
    return dict(role='Informed post-review audit, not another blind investigator. Original values, JSON parse failures and strict citation scores remain unchanged; aliases are diagnostics only.',
        evaluator_contract_limit='Frozen natural-language answer format asks for an exact quote but does not fix its literal JSON key. Reviewer uses exact quote/exact_quote; original scorer reads quote only. Container-versus-leaf and key/value-member quotation are additional strict matcher limits. No repaired answer or repeat receives original credit.',
        original_counts=original['totals'],original_strict_citation_matches=sum(r['citation_substring_present'] for r in rows),support_counts=dict(Counter(r['support'] for r in rows)),
        secondary_alias_quote_at_original_path=sum(r['secondary_alias_quote_at_original_path'] for r in rows),secondary_alias_quote_in_descendant_leaf=sum(r['secondary_alias_quote_in_descendant_leaf'] for r in rows),
        secondary_alias_quote_matches_json_member=sum(r['secondary_alias_quote_matches_json_member'] for r in rows),single_result_citation_insufficient_alone=sum(r['citation_scope_note'] is not None for r in rows),rows=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--reviews',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.write_text(json.dumps(audit(args.dataset,args.reviews,args.protocol),indent=2)+'\n')

if __name__=='__main__':main()
