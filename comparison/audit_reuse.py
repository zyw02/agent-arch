#!/usr/bin/env python3
"""Audit historical OpenClaw observations for scoped reuse; never promote them to new runs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evaluation/tools'))
from campaign import load_plan, records_from, audit, scenario_index

# These are candidates for mechanism evidence, not equivalence claims or coverage credits.
FAMILIES = {
 'PA': ['REL-01', 'REL-03', 'REL-04', 'REL-05'],
 'PB': ['SEC-11', 'EXT-09'],
 'PC': ['PERF-01', 'PERF-02', 'COST-01', 'COST-02', 'COST-04', 'COST-06'],
 'HA': ['PERF-10', 'EXT-04', 'EXT-06', 'COST-03'],
 'HB': ['REL-03', 'REL-05', 'PERF-03', 'PERF-06'],
 'HC': ['SEC-01', 'SEC-03', 'SEC-04', 'SEC-05', 'SEC-06', 'SEC-08', 'SEC-09', 'SEC-10', 'OBS-01'],
 'HD': ['EXT-02', 'EXT-05', 'EXT-07', 'EXT-08', 'PERF-03', 'OBS-02', 'OBS-03', 'OBS-06', 'OBS-07'],
 'HE': ['REL-02', 'REL-06', 'REL-10', 'REL-11'],
 'HF': ['COST-05', 'COST-07', 'PERF-10', 'EXT-06'],
 'HG': ['COST-03', 'EXT-06'],
}
GAPS = {
 'HA': 'Native memory write/update/retrieval provenance and identical next-request controls; old reference context engine is not the default engine.',
 'HB': 'Same-work single/two-child paired acceptance and all parent/child stage resources.',
 'HC': 'Current shared topology and route-specific filesystem/network/process witnesses; preserve original grants and threat model.',
 'HD': 'Matched DSH execution; native event subscriber versus OTLP collector semantics; complete diagnostic overhead ledger.',
 'HE': 'Selectable restore scope, peer agents/sessions/OS witnesses and actual affected footprint; backup creation does not prove restore.',
 'HF': 'Separate context pressure/output limits/goal guardrails. Shared hard task-tree budget already verified absent at this pin; native skill/context ablations still need binding.',
 'HG': 'COST-03 is agent-written guide reuse, not native Workshop feedback/validation/version reversal or sealed transfer/regression.',
 'PA': 'Matched deployment and same confirmed interruption boundary for the other products.',
 'PB': 'Matched public entry, identity contract and integration work for the other products.',
 'PC': 'Resource-matched hosts/deployments and shared task definitions; old bounded hardware measurements are not a cross-product baseline.',
}


def build_report(plan, records, permanent):
    checked = audit(plan, records)  # Reject corrupt, duplicate accepted units and wrong runtime/plan.
    if not checked['experiments_complete']:
        raise ValueError('Historical campaign is incomplete; preserve incomplete state before reuse')
    by_id = scenario_index(plan)
    indexed = {}
    for record in records:
        indexed.setdefault(record['scenario_id'], []).append(record)
    rows = []
    for status in checked['scenario_status']:
        sid = status['id']; case, scenario = by_id[sid]; units = indexed.get(sid, [])
        studies = [study for study, families in FAMILIES.items() if case['id'] in families]
        archive_refs = []
        for record in units:
            key = f"{record['run_id']}/{record['hosted_artifact_id']}"
            asset = permanent.get('assets', {}).get(key)
            if not asset or not asset.get('stored_bytes_readback_verified') or not asset.get('source_zip_sha256'):
                raise ValueError(f'Missing verified permanent evidence for {sid}/{key}')
            ref = {k: asset[k] for k in ('download_url', 'source_zip_sha256', 'zip_bytes')}
            if ref not in archive_refs:
                archive_refs.append(ref)
        rows.append(dict(scenario_id=sid, family=case['id'], name=scenario['name'],
            historical_state=status['state'], accepted_measured_units=status['valid_units'],
            capability_probe_records=sum(r['state'] == 'unsupported' for r in units),
            candidate_studies=studies,
            reuse_disposition=('verified_capability_boundary' if status['state']=='unsupported' else
                               'mechanism_evidence_candidate' if studies else 'reference_only'),
            compact_fields=sorted(set.intersection(*(set(r) for r in units))) if units else [],
            numeric_measurements_in_compact_record=any('acceptance_values' in r or 'reuse_accounting' in r for r in units),
            raw_archives=archive_refs,
            new_matched_comparison_credit=False))
    studies=[]
    for study, families in FAMILIES.items():
        matched=[r for r in rows if study in r['candidate_studies']]
        studies.append(dict(study=study, candidate_families=families,
            candidate_scenarios=len(matched), historical_states=dict(Counter(r['historical_state'] for r in matched)),
            measured_units=sum(r['accepted_measured_units'] for r in matched),
            remaining_gap=GAPS[study], reuse_status='pending_raw_field_and_condition_review',
            new_experiment_complete=False))
    return dict(schema_version=1, kind='historical-evidence-reuse-audit',
        target=plan['target'], historical_plan_sha256=plan['plan_sha256'],
        historical_audit={k:checked[k] for k in ('experiment_families','scenarios','scenario_counts','accepted_observation_count','measured_scenarios','verified_nonapplicable_scenarios','experiments_complete')},
        rules=['Historical failures are retained as evidence.', 'Quarantined results and preparation/calibration are excluded.',
               'Same version is necessary but not sufficient: compare workload, topology, grants, model, fault and observation scope.',
               'Quantitative cross-product comparison requires matched conditions or explicit stratification.',
               'Missing raw metrics are unknown; acceptance pass/fail cannot reconstruct CPU, tokens or latency.',
               'Historical observations keep original IDs and never count as new independent repetitions.'],
        studies=studies, scenarios=rows)


def render_markdown(report):
    a=report['historical_audit']
    lines=['# OpenClaw historical evidence reuse audit', '',
        f"Frozen version: `{report['target']['version']}` / `{report['target']['source_commit']}`.", '',
        f"Revalidated {a['scenarios']} scenarios: {a['measured_scenarios']} measured, {a['verified_nonapplicable_scenarios']} verified capability exclusions, {a['accepted_observation_count']} accepted measured observations.", '',
        'These are historical supporting observations. No new matched comparison is marked complete.', '',
        '| Study | Candidate scenarios | Measured units | Remaining gap |', '| --- | ---: | ---: | --- |']
    for s in report['studies']:
        lines.append(f"| {s['study']} | {s['candidate_scenarios']} | {s['measured_units']} | {s['remaining_gap']} |")
    lines += ['', 'Counts overlap across studies because the same observation can inform several questions; do not sum them as independent evidence.', '',
        'Each scenario in `reuse-audit.json` links permanent raw archives and their original ZIP hashes. Metrics must be recovered from those archives on disposable hosted workers before quantitative reuse. The compact records frequently contain only acceptance assertions.', '',
        'Shared hard budget exclusions apply to the pinned task-tree contract. They do not establish absence of all token accounting, context pressure or per-session goal controls.']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    directory=ROOT/'evaluation/campaigns/full-20261026-batched'
    report=build_report(load_plan(directory/'plan.json'),records_from(directory/'results'),json.loads((directory/'permanent-evidence.json').read_text()))
    report['input_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [directory/'plan.json',directory/'permanent-evidence.json']}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'reuse-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output/'reuse-audit.md').write_text(render_markdown(report))
    print(json.dumps(report['historical_audit']))

if __name__=='__main__':main()
