#!/usr/bin/env python3
"""Plot all formal observations; optional analysis dependency: matplotlib."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    rows = [r for r in csv.DictReader((args.campaign / 'runs.csv').open()) if r['smoke'] == 'False']
    if not rows:
        raise ValueError('No formal observations to plot')
    products = ['dsh', 'openclaw', 'hermes', 'codex', 'claude']
    labels = ['DSH', 'OpenClaw', 'Hermes', 'Codex', 'Claude Code']
    colors = ['#176B61', '#C46C30', '#7060A2', '#2874A6', '#AD4C70']
    panels = [
        ('Native run duration', 'Seconds', lambda r: float(r['wall_seconds']), False),
        ('Provider input + output', 'Million tokens',
         lambda r: (float(r['input_total']) + float(r['output_total'])) / 1e6 if r['usage_complete'] == 'True' else None, False),
        ('Writable storage growth: all three paths', 'MiB, logical regular-file growth',
         lambda r: float(r['writable_delta_logical_bytes']) / 1024**2, True),
        ('Container memory peak', 'MiB, kernel cgroup peak',
         lambda r: float(r['memory_peak_bytes']) / 1024**2 if r['memory_peak_bytes'] else None, True),
    ]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.fonttype': 'none'})
    figure, axes = plt.subplots(2, 2, figsize=(12.8, 8.2))
    for ax, (title, unit, value, logarithmic) in zip(axes.flat, panels):
        for index, product in enumerate(products):
            observed = [r for r in rows if r['product'] == product]
            values = []
            for run in observed:
                v = value(run)
                if v is None:
                    continue
                values.append(v)
                block = int(run['run_id'].split('-')[1])
                x = index + (block - 2) * 0.13
                resolved = run['resolved'] == 'True'
                ax.scatter(x, v, s=58, color=colors[index], marker='o' if resolved else 'x',
                           linewidths=1.8, zorder=3, alpha=.9)
            if values:
                median = statistics.median(values)
                ax.plot([index-.24, index+.24], [median, median], color='#26323B', linewidth=1.5, zorder=2)
            ax.text(index, 1.02, f"{sum(r['resolved'] == 'True' for r in observed)}/{len(observed)} resolved",
                    transform=ax.get_xaxis_transform(), ha='center', va='bottom', fontsize=8, color='#54616C')
        ax.set_title(title, loc='left', pad=30, fontweight='bold', fontsize=12)
        ax.set_ylabel(unit)
        ax.set_xticks(range(len(products)), labels)
        ax.set_xlim(-.55, 4.55)
        ax.grid(axis='y', color='#D9DEE3', linewidth=.6, zorder=0)
        if logarithmic:
            ax.set_yscale('log')
        else:
            ax.set_ylim(bottom=0)
    figure.suptitle('Five native harnesses | same DeepSeek model | pytest-7490',
                    x=.055, ha='left', y=.98, fontsize=17, fontweight='bold')
    figure.legend(handles=[Line2D([], [], color='#53626B', marker='o', linestyle='None', label='Resolved'),
                           Line2D([], [], color='#53626B', marker='x', linestyle='None', label='Unresolved'),
                           Line2D([], [], color='#26323B', label='All-run median')],
                  loc='upper left', bbox_to_anchor=(.047, .935), frameon=False, ncol=3)
    figure.text(.055, .025,
        'Each dot is one formal run; left-to-right offsets identify blocks 1, 2, 3. Storage and memory axes are logarithmic.\n'
        'Storage is file growth across workspace, home and /tmp; installation and controller trace storage are excluded.\n'
        'Missing usage is excluded only from the token panel. Unresolved runs can consume less by failing early.\n'
        'One public historical task, three runs per harness: these observations do not establish a general ranking.',
        fontsize=9, color='#54616C', va='bottom')
    figure.tight_layout(rect=[.035, .125, .98, .86], h_pad=3)
    figure.savefig(args.campaign / 'comparison.png', dpi=170, facecolor='white')
    figure.savefig(args.campaign / 'comparison.svg', facecolor='white')
    (args.campaign / 'plot-environment.json').write_text(json.dumps(dict(matplotlib=matplotlib.__version__,
        formal_runs=len(rows), script='benchmarks/swe_single/plot.py',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        csv_sha256=hashlib.sha256((args.campaign / 'runs.csv').read_bytes()).hexdigest()), indent=2) + '\n')


if __name__ == '__main__':
    main()
