#!/usr/bin/env python3
"""Inspect accepted native summaries in permanent ZIPs on disposable hosted runners."""
import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evaluation/tools'))
from campaign import records_from


def numeric_fields(value, path='', depth=0):
    if depth>14:return []
    if isinstance(value,bool) or value is None:return []
    if isinstance(value,(int,float)):return [(path,value)]
    if isinstance(value,dict):
        return [r for k,v in value.items() for r in numeric_fields(v,f'{path}.{k}',depth+1)]
    if isinstance(value,list):
        # Inventory bounded native metadata, never unbounded message trajectories.
        return [r for i,v in enumerate(value[:100]) for r in numeric_fields(v,f'{path}[{i}]',depth+1)]
    return []


def inspect(archive, accepted):
    if hashlib.sha256(archive).hexdigest()!=accepted['source_zip_sha256']:
        raise ValueError('Permanent ZIP digest mismatch')
    expected=accepted['summary_digests']; found=[]
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        members=z.infolist()
        if sum(m.file_size for m in members)>64*1024**2:raise ValueError('Expanded archive bound exceeded')
        for member in members:
            if not member.filename.endswith('summary.json'):continue
            if member.file_size>8*1024**2:raise ValueError('Native summary exceeds retained bound')
            raw=z.read(member);digest=hashlib.sha256(raw).hexdigest()
            if digest not in expected:continue
            d=json.loads(raw)
            found.append(dict(path=member.filename,sha256=digest,
                accepted_units=expected[digest],
                root_type=type(d).__name__,root_keys=sorted(d) if isinstance(d,dict) else [],
                # This is an availability inventory, not a reconstructed metric ledger.
                numeric_fields=numeric_fields(d)[:1500],
                native_json_shape=[{k:type(v).__name__ for k,v in item.items()} for item in d[:2]] if isinstance(d,list) else {}))
    if set(expected)-{v['sha256'] for v in found}:raise ValueError('Accepted native summary not found in archive')
    return found


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Raw archives are read only on disposable hosted workers')
    base=ROOT/'evaluation/campaigns/full-20261026-batched';records=records_from(base/'results')
    assets=json.loads((base/'permanent-evidence.json').read_text())['assets']
    # Small first slice: once summary schemas are verified, expand only needed fields/families.
    families={'COST-03','COST-07','OBS-02','REL-10'};chosen={}
    for r in records:
        family=r['scenario_id'].rsplit('-S',1)[0]
        if family not in families or r['state'] not in {'pass','fail'}:continue
        key=f"{r['run_id']}/{r['hosted_artifact_id']}"
        if family not in chosen:chosen[family]=key
    output=[]
    for family,key in chosen.items():
        asset=assets[key];expected={}
        for r in records:
            if f"{r['run_id']}/{r['hosted_artifact_id']}"!=key or r['state'] not in {'pass','fail'}:continue
            digest=r.get('native_summary_sha256')
            if digest:expected.setdefault(digest,[]).append({'scenario':r['scenario_id'],'unit':r['unit'],'state':r['state']})
        req=urllib.request.Request(asset['download_url'],headers={'User-Agent':'agent-arch-evidence-reuse'})
        with urllib.request.urlopen(req,timeout=60) as response:raw=response.read(8*1024**2+1)
        if len(raw)>8*1024**2 or len(raw)!=asset['zip_bytes']:raise ValueError('Archive size mismatch')
        output.append(dict(family=family,archive_key=key,archive_sha256=asset['source_zip_sha256'],
            source_url=asset['download_url'],summaries=inspect(raw,dict(source_zip_sha256=asset['source_zip_sha256'],summary_digests=expected))))
    result=dict(kind='accepted-native-summary-field-inventory',formal_new_experiments=False,
        run_id=os.environ.get('GITHUB_RUN_ID'),controller_commit=os.environ.get('GITHUB_SHA'),
        family_count=len(output),families=output,
        limitation='Fields are availability evidence. Native rows may include other scenarios; quantify only matched accepted scenario/unit IDs. No cross-product or new-study completion credit.')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'native-field-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'families':len(output),'accepted_native_summaries':sum(len(v['summaries']) for v in output)}))

if __name__=='__main__':main()
