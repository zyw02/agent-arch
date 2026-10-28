#!/usr/bin/env python3
"""Render the repository progress ledger into the README; no network or experiments."""
import argparse
import hashlib
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = '<!-- comparison-dashboard:start -->'
END = '<!-- comparison-dashboard:end -->'
LABEL = {'planned': 'Planned', 'in_progress': 'In progress', 'blocked': 'Blocked',
         'done': 'Complete', 'not_applicable': 'Not applicable'}


def render():
    data = json.loads((ROOT / 'comparison/progress.json').read_text(encoding='utf-8'))
    if data['schema_version'] != 1 or data['products'] != ['Codex', 'DSH', 'OpenClaw']:
        raise ValueError('Unsupported ledger schema or products')
    lines = [START, '<details>', '<summary>Full catalogue progress (reference)</summary>', '', '## Research progress', '',
        '| Layer / experiment | Dimensions | Codex | DSH | OpenClaw |', '| --- | --- | --- | --- | --- |']
    seen = set()
    for item in data['items']:
        if item['id'] in seen or item['layer'] not in ('platform', 'harness'):
            raise ValueError('Duplicate ID or invalid layer')
        seen.add(item['id'])
        dimensions = item.get('dimensions', [])
        allowed = {'Reliability', 'Security', 'Performance', 'Resource & cost', 'Extensibility', 'Observability'}
        if not dimensions or len(set(dimensions)) != len(dimensions) or not set(dimensions) <= allowed:
            raise ValueError('Invalid dimension mapping')
        if set(item['products']) != set(data['products']):
            raise ValueError('Each item must cover every product')
        cells = []
        for product in data['products']:
            entry = item['products'][product]
            status = entry['status']
            if status not in LABEL or not isinstance(entry['evidence'], list):
                raise ValueError('Invalid status or evidence')
            if status in ('done', 'not_applicable') and not entry['evidence']:
                raise ValueError('Completed or inapplicable entries require evidence')
            for name in entry['evidence']:
                p = (ROOT / name).resolve()
                if not p.is_relative_to(ROOT) or not p.is_file():
                    raise ValueError(f'Invalid evidence path: {name}')
            cells.append(LABEL[status])
        layer = 'Platform' if item['layer'] == 'platform' else 'Harness'
        lines.append(f"| {layer} · {item['id']} {item['name']} | {', '.join(dimensions)} | " + ' | '.join(cells) + ' |')
    campaign = json.loads((ROOT / 'comparison/campaign.json').read_text(encoding='utf-8'))
    cases = campaign['cases']
    if campaign['schema_version'] != 1 or {case['id'] for case in cases} != seen or len(cases) != len(seen):
        raise ValueError('Campaign cases must match progress items')
    for case in cases:
        item = next(x for x in data['items'] if x['id'] == case['id'])
        if case['layer'] != item['layer'] or not case['conditions'] or case['independent_units_per_condition'] < 3:
            raise ValueError('Invalid campaign case')
    for layer in ('platform', 'harness'):
        coverage = {dim for item in data['items'] if item['layer'] == layer for dim in item['dimensions']}
        if coverage != allowed:
            raise ValueError(f'Missing dimension coverage for {layer}: {allowed - coverage}')
    latest = data.get('latest_ci')
    if latest:
        url = latest['url']
        prefix = 'https://github.com/zyw02/agent-arch/actions/runs/'
        if not url.startswith(prefix) or not url[len(prefix):].isdigit() or latest['result'] not in ('success', 'failure', 'cancelled', 'skipped'):
            raise ValueError('Invalid CI progress record')
        lines += ['', f"**Latest session calibration:** {latest['result']} (three independent calibration units). [View calibration evidence]({url})."]
    lines += ['', '[OpenClaw architecture study](evaluation/reports/full-20261026-architecture.md) · [Experiment details](comparison/README.md)', '', '</details>', END]
    return '\n'.join(lines)


def render_visual():
    data = json.loads((ROOT / 'comparison/progress.json').read_text(encoding='utf-8'))
    statuses = [
        ('done', 'Complete', '#65e7c0'),
        ('in_progress', 'In progress', '#7a9cff'),
        ('planned', 'Planned', '#7383a1'),
        ('blocked', 'Blocked', '#ffbd6a'),
        ('not_applicable', 'Not applicable', '#b79be9'),
    ]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="980" height="365" viewBox="0 0 980 365" role="img" aria-labelledby="title desc">',
        '<title id="title">Experiment progress by product</title>',
        '<desc id="desc">A stacked bar and counts for each status for Codex, DSH, and OpenClaw.</desc>',
        '<rect width="980" height="365" rx="18" fill="#0d1527"/>',
        '<text x="44" y="48" fill="#f0f5ff" font-family="Arial,sans-serif" font-size="24" font-weight="700">Experiment progress</text>']
    for row, product in enumerate(data['products']):
        counts = {key: sum(item['products'][product]['status'] == key for item in data['items']) for key, _, _ in statuses}
        total = len(data['items'])
        y = 82 + row * 76
        out.append(f'<text x="44" y="{y + 14}" fill="#f0f5ff" font-family="Arial,sans-serif" font-size="16" font-weight="700">{product}</text>')
        out.append(f'<text x="936" y="{y + 14}" text-anchor="end" fill="#b9c7e1" font-family="Arial,sans-serif" font-size="13">{total} tasks</text>')
        x = 180.0
        for key, _, color in statuses:
            width = 630 * counts[key] / total if total else 0
            if width:
                if key == 'in_progress':
                    out.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="18" fill="{color}"><animate attributeName="opacity" values="1;0.55;1" dur="2.6s" repeatCount="indefinite"/></rect>')
                else:
                    out.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="18" fill="{color}"/>')
            x += width
        positions = [180, 312, 470, 585, 700]
        for (key, label, color), px in zip(statuses, positions):
            out.append(f'<circle cx="{px}" cy="{y + 39}" r="4" fill="{color}"/>')
            out.append(f'<text x="{px + 9}" y="{y + 43}" fill="#c1cde3" font-family="Arial,sans-serif" font-size="12">{label}: {counts[key]}</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'README.md'
    original = path.read_text(encoding='utf-8')
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError('README dashboard markers missing or duplicated')
    updated = original[:original.index(START)] + render() + original[original.index(END) + len(END):]
    visual_path = ROOT / 'comparison/progress.svg'
    visual = render_visual()
    revision = hashlib.sha256(visual.encode('utf-8')).hexdigest()[:12]
    updated, replacements = re.subn(r'(?:https://raw\.githubusercontent\.com/zyw02/agent-arch/main/)?comparison/progress\.svg(?:\?v=[0-9a-f]{12})?',
                                    'https://raw.githubusercontent.com/zyw02/agent-arch/main/comparison/progress.svg?v=' + revision, updated)
    if replacements != 1:
        raise ValueError('README must contain exactly one progress image')
    if args.check:
        if not visual_path.exists() or visual_path.read_text(encoding='utf-8') != visual:
            raise SystemExit('Progress visual is stale; run python3 comparison/dashboard.py')
        if updated != original:
            raise SystemExit('Dashboard is stale; run python3 comparison/dashboard.py')
        print('Dashboard is current')
    else:
        path.write_text(updated, encoding='utf-8')
        visual_path.write_text(visual, encoding='utf-8')


if __name__ == '__main__':
    main()
