"""Retain native traces and expose supported diagnostics without zero-filling."""
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import subprocess


def json_lines(text):
    rows = []
    for line in text.splitlines():
        line = re.sub(r'^\d{4}-\d\d-\d\dT\S+\s+', '', line)
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def sqlite_inventory(home):
    rows = []
    for path in Path(home).rglob('*'):
        if path.is_symlink() or not path.is_file() or path.suffix not in ('.db', '.sqlite', '.sqlite3'):
            continue
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
                tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                schema = {name: [r[1] for r in db.execute('PRAGMA table_info("' + name.replace('"', '""') + '")')]
                          for name in tables}
                row = dict(path=str(path.relative_to(home)), schema=schema,
                           inspection_scope='immutable main DB only; raw WAL/SHM retained separately')
                for name in ('sessions', 'messages', 'auxiliary_usage'):
                    if name in tables:
                        row[name + '_row_count'] = db.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                rows.append(row)
        except sqlite3.Error as exc:
            rows.append(dict(path=str(path.relative_to(home)), error=str(exc)))
    return rows


def inspect_native(product, home, stdout, output):
    home, output = Path(home), Path(output)
    rows = json_lines(Path(stdout).read_text(errors='replace'))
    counts = Counter(r.get('type', 'unknown') for r in rows)
    result = dict(product=product, stdout_event_types=dict(counts),
                  raw_trace_retained=True, native_tool_calls=None,
                  native_steps=None, native_retries=None, native_compactions=None,
                  native_approvals=None, native_usage=None,
                  missing_reason='not_yet_supported_by_this_native_projection',
                  sqlite_inventory=sqlite_inventory(home))
    tools = []
    if product == 'dsh':
        tools = [dict(id=r.get('callId'), name=r.get('tool')) for r in rows if r.get('type') == 'tool_call']
        result.update(native_tool_calls=len(tools) if rows else None, native_steps=sum(r.get('phase') == 'step_start' for r in rows) if rows else None,
                      native_usage=[r['usage'] for r in rows if r.get('phase') == 'step_end' and 'usage' in r])
        durable_counts = Counter()
        errors = []
        files = list((home / '.dsh').rglob('*.jsonl.zstd')) + list((home / '.dsh').rglob('*.jsonl.zst'))
        for path in files:
            p = subprocess.run(['zstd', '-dc', '--', str(path)], capture_output=True)
            if p.returncode:
                errors.append(str(path.relative_to(home)))
                continue
            for row in json_lines(p.stdout.decode(errors='replace')):
                event = row.get('event', row)
                if isinstance(event, dict):
                    durable_counts[event.get('type', event.get('kind', 'unknown'))] += 1
        result['durable_event_types'] = dict(durable_counts)
        result['durable_log_files'] = len(files)
        result['durable_parse_errors'] = errors
        if files and durable_counts and not errors:
            result.update(native_retries=durable_counts['llm/retry-started'],
                          native_compactions=durable_counts['compaction/start'],
                          native_approvals=durable_counts['approval/asked'])
    elif product == 'claude':
        for row in rows:
            if row.get('type') == 'assistant':
                for block in row.get('message', {}).get('content', []):
                    if block.get('type') == 'tool_use':
                        tools.append(dict(id=block.get('id'), name=block.get('name')))
            if row.get('type') == 'result':
                result['native_usage'] = row.get('usage')
                result['native_model_usage'] = row.get('modelUsage')
                result['native_steps'] = row.get('num_turns')
        tools = list({t['id']: t for t in tools}.values())
        result['native_tool_calls'] = len(tools) if rows else None
        compactions = [r for r in rows if r.get('type') == 'system' and r.get('subtype') == 'compact_boundary']
        result['native_compaction_events_observed'] = len(compactions)
    elif product == 'codex':
        for row in rows:
            if row.get('type') == 'turn.completed':
                result['native_usage'] = row.get('usage')
            if row.get('type') == 'item.completed':
                item = row.get('item', {})
                if item.get('type') in ('command_execution', 'mcp_tool_call', 'file_change'):
                    tools.append(dict(id=item.get('id'), name=item.get('type'), status=item.get('status')))
        result['native_tool_calls'] = len(tools) if rows else None
        result['native_tool_count_scope'] = 'completed command/MCP/file-change items; not a universal function-call count'
    elif product == 'hermes':
        path = home / 'native-usage.json'
        if path.exists():
            result['native_usage'] = json.loads(path.read_text())
    elif product == 'openclaw':
        # The CLI may print one indented object instead of JSONL.
        text = Path(stdout).read_text(errors='replace')
        text = '\n'.join(re.sub(r'^\d{4}-\d\d-\d\dT\S+\s+', '', line) for line in text.splitlines())
        try:
            result['native_result'] = json.loads(text)
        except ValueError:
            result['native_result'] = rows[-1] if rows else None
        transcript_rows = []
        for path in (home / '.openclaw').rglob('*.jsonl'):
            transcript_rows += json_lines(path.read_text(errors='replace'))
        for row in transcript_rows:
            message = row.get('message', {})
            if isinstance(message, dict):
                for block in message.get('content', []):
                    if isinstance(block, dict) and block.get('type') in ('toolCall', 'tool_use'):
                        tools.append(dict(id=block.get('id'), name=block.get('name')))
        tools = list({t['id']: t for t in tools}.values())
        meta = (result.get('native_result') or {}).get('meta', {})
        tool_summary = meta.get('toolSummary', {})
        result['native_tool_calls'] = len(tools) if transcript_rows else tool_summary.get('calls')
        result['native_tool_summary'] = tool_summary or None
        result['native_usage'] = [r['message']['usage'] for r in transcript_rows
                                  if isinstance(r.get('message'), dict) and 'usage' in r['message']]
        if not result['native_usage']:
            result['native_usage'] = meta.get('agentMeta', {}).get('usage')
        result['native_tool_count_scope'] = 'JSONL transcripts when available, otherwise native CLI meta.toolSummary.calls; SQLite state retained'
        result['transcript_event_types'] = dict(Counter(r.get('type', 'unknown') for r in transcript_rows))
    result['native_tools'] = tools
    (output / 'native-summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result
