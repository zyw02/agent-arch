"""Provider-side counters and intervals; no tokenization or guessed missing values."""
from copy import deepcopy
from decimal import Decimal

REFERENCE_RATES = {
    'off_peak': {'input_noncache_billed': '0.15', 'cache_read': '0.003', 'output_total': '0.6'},
    'peak': {'input_noncache_billed': '0.3', 'cache_read': '0.006', 'output_total': '1.2'},
}


def merge_counters(previous, update):
    result = deepcopy(previous)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_counters(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def integer(value):
    return value if type(value) is int and value >= 0 else None


def normalize_usage(api, usage):
    """Input/output are inclusive; reasoning is a subset, never added again.

    DeepSeek has automatic caching with cache-hit/miss prices, no separate cache
    creation charge. Preserve any creation count, but don't invent one on other
    wires. input_noncache_billed is the common pricing/efficiency dimension.
    """
    if not isinstance(usage, dict):
        return dict(input_total=None, input_noncache_billed=None, cache_read=None,
                    cache_write=None, output_total=None, reasoning_subset=None,
                    core_complete=False, missing_reason='provider_usage_not_received')
    if api == 'messages':
        uncached = integer(usage.get('input_tokens'))
        read = integer(usage.get('cache_read_input_tokens'))
        write = integer(usage.get('cache_creation_input_tokens'))
        # A missing cache-creation field is not a measured zero. For DeepSeek's
        # non-creation-billed route it does not add a separate pricing bucket.
        noncache = None if uncached is None else uncached + (write if write is not None else 0)
        inp = None if noncache is None or read is None else noncache + read
        out = integer(usage.get('output_tokens'))
        reasoning = integer(usage.get('output_tokens_details', {}).get('reasoning_tokens'))
    elif api == 'chat':
        inp = integer(usage.get('prompt_tokens'))
        out = integer(usage.get('completion_tokens'))
        read = integer(usage.get('prompt_cache_hit_tokens'))
        if read is None:
            read = integer(usage.get('prompt_tokens_details', {}).get('cached_tokens'))
        write = integer(usage.get('cache_creation_input_tokens'))
        noncache = None if inp is None or read is None else inp - read
        reasoning = integer(usage.get('completion_tokens_details', {}).get('reasoning_tokens'))
    elif api == 'responses':
        inp = integer(usage.get('input_tokens'))
        out = integer(usage.get('output_tokens'))
        read = integer(usage.get('input_tokens_details', {}).get('cached_tokens'))
        write = integer(usage.get('input_tokens_details', {}).get('cache_write_tokens'))
        noncache = None if inp is None or read is None else inp - read
        reasoning = integer(usage.get('output_tokens_details', {}).get('reasoning_tokens'))
    else:
        raise ValueError(api)
    valid = all(v is not None and v >= 0 for v in (inp, noncache, read, out))
    if reasoning is not None and out is not None and reasoning > out:
        valid = False
    return dict(input_total=inp, input_noncache_billed=noncache, cache_read=read,
                cache_write=write, cache_write_billing='not_applicable',
                output_total=out, reasoning_subset=reasoning, core_complete=valid,
                missing_reason=None if valid else 'required_provider_counter_missing_or_inconsistent')


def union_seconds(intervals):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged) / 1e9


def summarize_requests(records):
    forwarded = [r for r in records if r.get('forwarded')]
    known = [r for r in forwarded if r.get('normalized_usage', {}).get('core_complete')]
    result = dict(provider_attempts=len(forwarded), blocked_requests=len(records) - len(forwarded),
                  usage_known_attempts=len(known), usage_unknown_attempts=len(forwarded) - len(known),
                  usage_complete=bool(forwarded) and len(known) == len(forwarded)
                  and all(r.get('terminal') and r.get('settled') for r in forwarded),
                  terminal_responses=sum(bool(r.get('terminal')) for r in forwarded),
                  http_error_attempts=sum((r.get('http_status') or 0) >= 400 for r in forwarded),
                  request_bytes=sum(r.get('upstream_request_bytes', 0) for r in forwarded),
                  response_bytes=sum(r.get('response_bytes', 0) for r in forwarded),
                  provider_duration_union_seconds=union_seconds([
                      (r['started_ns'], r['ended_ns']) for r in forwarded if r.get('ended_ns')]),
                  actual_cost_usd=None)
    for key in ('input_total', 'input_noncache_billed', 'cache_read', 'output_total'):
        result['known_' + key] = sum(r['normalized_usage'][key] for r in known)
        result[key] = result['known_' + key] if result['usage_complete'] else None
    # No zero-filled reasoning or cache-write aggregates: expose coverage.
    for key in ('reasoning_subset', 'cache_write'):
        values = [r.get('normalized_usage', {}).get(key) for r in forwarded]
        available = [v for v in values if v is not None]
        result['known_' + key] = sum(available)
        result[key + '_coverage'] = dict(known=len(available), total=len(values))
        result[key] = sum(available) if values and len(available) == len(values) else None
    result['reference_cost_usd'] = {}
    for tier, rates in REFERENCE_RATES.items():
        subtotal = sum(Decimal(result['known_' + key]) * Decimal(rate) / 1000000
                       for key, rate in rates.items())
        result['reference_cost_usd'][tier] = dict(known_subtotal=str(subtotal),
            complete_estimate=str(subtotal) if result['usage_complete'] else None)
    result['cost_semantics'] = 'Frozen 2026-11-11 DeepSeek tariffs, standardized peak/off-peak references, not actual time-window billing or invoice'
    return result
