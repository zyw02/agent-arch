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


def median(values, key):
    known = [v[key] for v in values if v.get(key) is not None]
    return statistics.median(known) if known else None


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
        for key in ('blocked_requests', 'terminal_responses', 'http_error_attempts',
                    'request_bytes', 'response_bytes', 'provider_duration_union_seconds'):
            row[key] = provider.get(key)
        for key in ('input_total', 'input_noncache_billed', 'cache_read', 'output_total'):
            row['known_' + key] = provider.get('known_' + key)
        for key in ('reasoning_subset', 'cache_write'):
            for count in ('known', 'total'):
                row[f'{key}_coverage_{count}'] = provider.get(key + '_coverage', {}).get(count)
        for key in ('rbytes', 'wbytes', 'rios', 'wios'):
            row['device_io_' + key] = (cg.get('io') or {}).get(key)
        for key in ('oom', 'oom_kill'):
            row['memory_events_' + key] = (cg.get('memory_events') or {}).get(key)
        for key in ('files', 'lines_added', 'lines_removed', 'policy_passed'):
            row['patch_' + key] = result.get('patch', {}).get(key)
        if row['cpu_seconds'] is not None:
            row['cpu_seconds'] /= 1e6
        for scope in ('workspace', 'home', 'tmp'):
            for metric in ('logical_bytes', 'allocated_bytes', 'files', 'directories'):
                row[f'{scope}_final_{metric}'] = storage['final'][scope][metric]
                row[f'{scope}_delta_{metric}'] = storage['delta'][scope][metric]
                row[f'{scope}_sampled_peak_{metric}'] = storage['sampled_peak'][scope][metric]
        for stage in ('final', 'delta'):
            for metric in ('logical_bytes', 'allocated_bytes', 'files', 'directories'):
                row[f'writable_{stage}_{metric}'] = sum(storage[stage][scope][metric]
                                                        for scope in ('workspace', 'home', 'tmp'))
        for category in ('logs_and_transcripts', 'database_and_journal', 'cache', 'other'):
            for metric in ('logical_bytes', 'allocated_bytes', 'files'):
                row[f'home_{category}_{metric}'] = storage['final']['home'].get('categories', {}).get(category, {}).get(metric, 0)
        row['final_storage_scan_errors'] = sum(len(storage['final'][scope].get('scan_errors', []))
                                              for scope in ('workspace', 'home', 'tmp'))
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
    product_count = len({r['product'] for r in rows})
    lines = [f'# {product_count} 个 harness 的同模型单题实测', '',
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
        lines += ['', '上表耗时、存储中位数包含成功与失败的全部运行；更早失败可能消耗更少，不能据此解释为效率优势。',
                  'Token 中位数只使用 usage 完整的运行；各家完整次数不同时，不能直接解读为效率排名。', '',
                  '### 成功运行的耗用', '',
                  '| Harness | 成功次数 | 耗时中位数秒 | 完整 usage 次数 | 输入 token 中位数 | 输出 token 中位数 | 峰时参考费用中位数 USD |',
                  '| --- | --- | --- | --- | --- | --- | --- |']
        for product, values in grouped.items():
            successful = [v for v in values if v['resolved']]
            complete = [v for v in successful if v['usage_complete']]
            costs = [float(v['peak_estimated_usd']) for v in complete if v['peak_estimated_usd'] is not None]
            lines.append(f"| {product} | {len(successful)} | {number(median(successful, 'wall_seconds'))} | "
                         f"{len(complete)}/{len(successful)} | {number(median(complete, 'input_total'), 0)} | "
                         f"{number(median(complete, 'output_total'), 0)} | "
                         f"{number(statistics.median(costs) if costs else None, 5)} |")
        lines += ['', '成功子集的难度和次数仍可能不同；没有成功样本时耗用为未知。费用是统一冻结价的估算。', '',
                  '### 全部正式运行的资源', '',
                  '| Harness | CPU 秒中位数 | 内存峰值 MiB 中位数 | home + tmp 最终逻辑 MiB 中位数 | home + tmp 最终分配 MiB 中位数 |',
                  '| --- | --- | --- | --- | --- |']
        for product, values in grouped.items():
            memory = median(values, 'memory_peak_bytes')
            logical = statistics.median(v['home_final_logical_bytes'] + v['tmp_final_logical_bytes'] for v in values)
            allocated = statistics.median(v['home_final_allocated_bytes'] + v['tmp_final_allocated_bytes'] for v in values)
            lines.append(f"| {product} | {number(median(values, 'cpu_seconds'))} | "
                         f"{number(memory / 1024**2 if memory is not None else None)} | "
                         f"{number(logical / 1024**2)} | {number(allocated / 1024**2)} |")
        lines += ['', '每次运行长度不同，资源占用需结合逐次完成状态阅读；以上不含共享安装镜像和评测器归档。', '',
                  '### 三处可写目录的合计增长', '',
                  '| Harness | 逻辑增长 MiB 中位数 | 分配增长 MiB 中位数 | 文件数增长中位数 |',
                  '| --- | --- | --- | --- |']
        for product, values in grouped.items():
            lines.append(f"| {product} | {number(median(values, 'writable_delta_logical_bytes') / 1024**2)} | "
                         f"{number(median(values, 'writable_delta_allocated_bytes') / 1024**2)} | "
                         f"{number(median(values, 'writable_delta_files'), 0)} |")
        lines += ['', '合计先逐次相加工作区、home、/tmp 的最终减初始值，再取中位数。它包含测试产生的缓存和临时文件，',
                  '不能当作框架空闲占用；例如 Hermes 把部分测试临时目录放在 home 内，其他框架更多写到 /tmp。', '',
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
              '- 存储区分工作区、home、临时目录；逻辑大小、分配块和设备 I/O 分别记录。运行中扫描非原子，采样最大值是近似观测；最终值来自暂停后的扫描。',
              '- 费用使用冻结价格估算，不能视为账单金额；不完整运行只保留已知小计。',
              '- 原生工具数、步数、压缩和重试的语义不同，仅用于诊断。', '']
    (args.campaign / 'report.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
