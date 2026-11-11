#!/usr/bin/env python3
"""Render retained evidence without combining smoke and formal observations."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics


def number(value, digits=2):
    return '未知' if value is None else f'{value:.{digits}f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    summary = json.loads((args.campaign / 'summary.json').read_text())
    latest = summary.get('latest_accounting', {})
    verified_path = args.campaign / 'validated-accounting.json'
    if verified_path.exists():
        latest.update({k: v['summary'] for k, v in json.loads(verified_path.read_text())['runs'].items()})
    rows = []
    for result in summary['results']:
        provider = latest.get(result['run_id'], result['provider'])
        storage = result['storage']
        cg = storage.get('cgroup', {})
        row = dict(run_id=result['run_id'], product=result['product'], smoke=result['smoke'],
                   resolved=result['resolved'], patch_resolved=result.get('patch_resolved'),
                   calibration_passed=result.get('calibration_passed'),
                   native_execution_ok=result['native_execution_ok'],
                   termination=result.get('termination'), wall_seconds=result['wall_seconds'],
                   time_to_first_provider_request_seconds=result['time_to_first_provider_request_seconds'],
                   provider_attempts=provider['provider_attempts'],
                   usage_known_attempts=provider['usage_known_attempts'],
                   usage_unknown_attempts=provider['usage_unknown_attempts'],
                   usage_complete=provider['usage_complete'],
                   input_total=provider['input_total'],
                   input_noncache_billed=provider['input_noncache_billed'],
                   cache_read=provider['cache_read'], output_total=provider['output_total'],
                   reasoning_subset=provider['reasoning_subset'],
                   memory_peak_bytes=cg.get('memory_peak'),
                   cpu_seconds=(cg.get('cpu') or {}).get('usage_usec'),
                   native_tool_calls=result['native'].get('native_tool_calls'))
        if row['cpu_seconds'] is not None:
            row['cpu_seconds'] /= 1e6
        for scope in ('workspace', 'home', 'tmp'):
            for metric in ('logical_bytes', 'allocated_bytes', 'files', 'directories'):
                row[f'{scope}_final_{metric}'] = storage['final'][scope][metric]
                row[f'{scope}_delta_{metric}'] = storage['delta'][scope][metric]
                row[f'{scope}_sampled_peak_{metric}'] = storage['sampled_peak'][scope][metric]
        for tier in ('off_peak', 'peak'):
            value = provider['reference_cost_usd'][tier]
            row[f'{tier}_estimated_usd'] = value['complete_estimate']
            row[f'{tier}_known_subtotal_usd'] = value['known_subtotal']
        for group in ('FAIL_TO_PASS', 'PASS_TO_PASS'):
            value = result.get('grade', {}).get(group, {})
            row[group + '_passed'] = value.get('passed')
            row[group + '_total'] = value.get('total')
        rows.append(row)
    if rows:
        with (args.campaign / 'runs.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    lines = ['# 五个 harness 的同模型单题实测', '',
             f"题目：`{summary['instance_id']}`；实验：`{summary['experiment_id']}`。", '',
             '此表只描述固定题目、版本、模型及资源条件下的观测，不能推导总体排名。', '',
             '## 接入与计量校验', '',
             '| Harness | 工具与计量校验通过 | usage 已知/请求 | 耗时秒 |',
             '| --- | --- | --- | --- |']
    for row in rows:
        if row['smoke']:
            lines.append(f"| {row['product']} | {row['calibration_passed']} | "
                         f"{row['usage_known_attempts']}/{row['provider_attempts']} | {number(row['wall_seconds'])} |")
    grouped = defaultdict(list)
    for row in rows:
        if not row['smoke']:
            grouped[row['product']].append(row)
    lines += ['', '## 正式观测', '']
    if not grouped:
        lines += ['尚无正式解题结果。接入或采集失败不作为解题失败计入成功率。']
    else:
        lines += ['| Harness | 成功/次数 | 耗时中位数秒 | usage 完整次数 | 输入 token 中位数 | 输出 token 中位数 | 会话目录最终 MiB 中位数 |',
                  '| --- | --- | --- | --- | --- | --- | --- |']
        for product, values in grouped.items():
            complete = [v for v in values if v['usage_complete']]
            inp = statistics.median(v['input_total'] for v in complete) if complete else None
            out = statistics.median(v['output_total'] for v in complete) if complete else None
            lines.append(f"| {product} | {sum(v['resolved'] for v in values)}/{len(values)} | "
                         f"{number(statistics.median(v['wall_seconds'] for v in values))} | {len(complete)}/{len(values)} | "
                         f"{number(inp, 0)} | {number(out, 0)} | "
                         f"{number(statistics.median(v['home_final_logical_bytes'] for v in values) / 1024**2)} |")
        lines += ['', 'Token 中位数只使用 usage 完整的运行；各家完整次数不同时，不能直接解读为效率排名。', '',
                  '| 运行 | 完成 | F2P | P2P | 秒 | 请求 | usage 完整 |',
                  '| --- | --- | --- | --- | --- | --- | --- |']
        for row in rows:
            if not row['smoke']:
                lines.append(f"| {row['run_id']} | {row['resolved']} | {row['FAIL_TO_PASS_passed']}/{row['FAIL_TO_PASS_total']} | "
                             f"{row['PASS_TO_PASS_passed']}/{row['PASS_TO_PASS_total']} | {number(row['wall_seconds'])} | "
                             f"{row['provider_attempts']} | {row['usage_complete']} |")
    error = args.campaign / 'campaign-error.json'
    if error.exists():
        lines += ['', '## 执行状态', '', json.loads(error.read_text())['message']]
    lines += ['', '## 数据边界', '',
              '- 原始证据在各运行目录的 provider、native-state、resources、patch 和 grading 文件中；逐次指标见 runs.csv。',
              '- 输入总数包含缓存读取；reasoning 若返回则属于输出子集，不重复相加。缺失字段为未知。',
              '- 存储区分工作区、会话目录、临时目录；逻辑大小、分配块和设备 I/O 分别记录。采样峰值只是下界。',
              '- 费用使用冻结价格估算，不能视为账单金额；不完整运行只保留已知小计。',
              '- 原生工具数、步数、压缩和重试的语义不同，仅用于诊断。', '']
    (args.campaign / 'report.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
