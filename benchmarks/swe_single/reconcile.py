#!/usr/bin/env python3
"""Compare explicitly scoped native counters with the independent provider ledger."""
import argparse
import json
from pathlib import Path


def sum_fields(values, keys):
    counts = [v.get(k) for v in values for k in keys]
    return sum(counts) if counts and all(type(v) is int and v >= 0 for v in counts) else None


def project(product, native):
    usage = native.get('native_usage')
    if product == 'dsh' and isinstance(usage, list):
        return dict(input_total=sum_fields(usage, ('inputTokens', 'cacheReadTokens', 'cacheWriteTokens')),
                    cache_read=sum_fields(usage, ('cacheReadTokens',)),
                    output_total=sum_fields(usage, ('outputTokens',)), native_api_calls=len(usage),
                    scope='stdout step-end counters; auxiliary title calls may be outside this scope')
    if product == 'claude' and isinstance(usage, dict):
        return dict(input_total=sum_fields([usage], ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')),
                    cache_read=usage.get('cache_read_input_tokens'), output_total=usage.get('output_tokens'),
                    native_api_calls=None,
                    scope='CLI final result usage; retain modelUsage and subagent traces to assess aggregation scope')
    if product == 'codex' and isinstance(usage, dict):
        return dict(input_total=usage.get('input_tokens'), cache_read=usage.get('cached_input_tokens'),
                    output_total=usage.get('output_tokens'), native_api_calls=None,
                    scope='CLI turn.completed usage; raw persisted rollouts retained')
    if product in ('openclaw', 'openclaw57_patched'):
        meta = (native.get('native_result') or {}).get('meta', {})
        usage = (meta.get('agentMeta') or {}).get('usage')
        if isinstance(usage, dict):
            return dict(input_total=sum_fields([usage], ('input', 'cacheRead', 'cacheWrite')),
                        cache_read=usage.get('cacheRead'), output_total=usage.get('output'),
                        native_api_calls=None,
                        scope='CLI meta.agentMeta.usage; input is uncached and cache counters are separate')
    if product == 'hermes' and isinstance(usage, dict):
        auxiliary = usage.get('auxiliary')
        values = [usage] + ([auxiliary] if isinstance(auxiliary, dict) else [])
        # In the pinned DeepSeek adapter, main input is inclusive, while the
        # auxiliary title counter stores uncached input separately from caches.
        main_input = sum_fields([usage], ('input_tokens',))
        auxiliary_input = (sum_fields([auxiliary], ('input_tokens', 'cache_read_tokens', 'cache_write_tokens'))
                           if isinstance(auxiliary, dict) else 0)
        total_input = main_input + auxiliary_input if main_input is not None and auxiliary_input is not None else None
        return dict(input_total=total_input,
                    cache_read=sum_fields(values, ('cache_read_tokens',)),
                    output_total=sum_fields(values, ('output_tokens',)),
                    native_api_calls=sum_fields(values, ('api_calls',)),
                    scope='Pinned DeepSeek usage file: inclusive main input plus cache-exclusive auxiliary input and explicit auxiliary caches; late or failed attempts may be outside the snapshot')
    return dict(input_total=None, cache_read=None, output_total=None, native_api_calls=None,
                scope='Native projection unavailable; raw evidence retained')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    summary = json.loads((args.campaign / 'summary.json').read_text())
    verified_path = args.campaign / 'validated-accounting.json'
    if verified_path.exists():
        summary.setdefault('latest_accounting', {}).update({
            k: v['summary'] for k, v in json.loads(verified_path.read_text())['runs'].items()})
    rows = []
    for result in summary['results']:
        provider = summary.get('latest_accounting', {}).get(result['run_id'], result['provider'])
        native = project(result['product'], result['native'])
        row = dict(run_id=result['run_id'], product=result['product'], smoke=result['smoke'], native=native,
                   provider_usage_complete=provider['usage_complete'],
                   provider_attempts=provider['provider_attempts'],
                   provider_usage_known_attempts=provider['usage_known_attempts'],
                   counters={})
        for field in ('input_total', 'cache_read', 'output_total'):
            source, target = native[field], provider[field]
            row['counters'][field] = dict(native=source, provider=target,
                provider_known_subtotal=provider['known_' + field],
                provider_minus_native=target - source if type(source) is int and type(target) is int else None)
        rows.append(row)
    payload = dict(rows=rows,
        interpretation='A nonzero difference identifies a scope/accounting discrepancy for investigation, not automatic proof of a harness defect. Never replace provider counters with native totals or use agreement alone as completeness proof.')
    (args.campaign / 'native-provider-reconciliation.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
