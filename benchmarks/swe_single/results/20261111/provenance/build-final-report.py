#!/usr/bin/env python3
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import statistics

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'evidence/campaign'
rows=[r for r in csv.DictReader((C/'runs.csv').open()) if r['smoke']=='False']
summary=json.loads((C/'summary.json').read_text())
accounting=json.loads((C/'validated-accounting.json').read_text())['runs']
provenance=json.loads((ROOT/'provenance.json').read_text())
products=['dsh','openclaw','hermes','codex','claude']
labels=dict(dsh='DSH',openclaw='OpenClaw',hermes='Hermes',codex='Codex',claude='Claude Code')
metrics=['wall_seconds','time_to_first_provider_request_seconds','cpu_seconds','memory_peak_bytes',
 'input_total','input_noncache_billed','cache_read','output_total',
 'home_final_logical_bytes','tmp_final_logical_bytes','home_final_allocated_bytes','tmp_final_allocated_bytes',
 'workspace_delta_logical_bytes','workspace_delta_allocated_bytes','writable_delta_logical_bytes',
 'writable_delta_allocated_bytes','writable_delta_files']
stats={}
for product in products:
 rs=sorted([r for r in rows if r['product']==product],key=lambda r:r['run_id'])
 vs=[accounting[r['run_id']]['summary'] for r in rs]
 walls=[float(r['wall_seconds']) for r in rs]
 med={k:statistics.median(float(r[k]) for r in rs) for k in metrics}
 stats[product]=dict(label=labels[product],runs=[r['run_id'] for r in rs],resolved=sum(r['resolved']=='True' for r in rs),
  wall_seconds=walls,wall_mean=statistics.mean(walls),wall_median=statistics.median(walls),medians=med,
  provider_attempts=sum(v['provider_attempts'] for v in vs),usage_complete_runs=sum(v['usage_complete'] for v in vs),
  input_total=sum(v['input_total'] for v in vs),cache_read=sum(v['cache_read'] for v in vs),output_total=sum(v['output_total'] for v in vs),
  peak_reference_usd_median=str(statistics.median(Decimal(v['reference_cost_usd']['peak']['complete_estimate']) for v in vs)),
  peak_reference_usd_total=str(sum(Decimal(v['reference_cost_usd']['peak']['complete_estimate']) for v in vs)))
formal_values=[accounting[r['run_id']]['summary'] for r in rows]
formal_peak=sum(Decimal(v['reference_cost_usd']['peak']['complete_estimate']) for v in formal_values)
formal_off=sum(Decimal(v['reference_cost_usd']['off_peak']['complete_estimate']) for v in formal_values)
all_campaigns=[C]+sorted((ROOT/'preliminary-calibrations').glob('*/campaign'))
all_values=[v['summary'] for c in all_campaigns for v in json.loads((c/'validated-accounting.json').read_text())['runs'].values()]
payload=dict(products=stats,formal_runs=15,formal_successes=15,formal_provider_attempts=394,formal_known_attempts=394,
 formal_input_total=sum(v['input_total'] for v in formal_values),formal_output_total=sum(v['output_total'] for v in formal_values),
 formal_reasoning_known_attempts=sum(v['reasoning_subset_coverage']['known'] for v in formal_values),
 formal_peak_reference_usd=str(formal_peak),formal_off_peak_reference_usd=str(formal_off),
 experiment_provider_attempts=sum(v['provider_attempts'] for v in all_values),
 experiment_known_attempts=sum(v['usage_known_attempts'] for v in all_values),
 experiment_unknown_attempts=sum(v['usage_unknown_attempts'] for v in all_values),
 experiment_peak_known_subtotal_usd=str(sum(Decimal(v['reference_cost_usd']['peak']['known_subtotal']) for v in all_values)),
 statistics_semantics='Each column is independently aggregated; medians of token partitions need not sum to the median inclusive input. Three runs of one fixed public task, no population inference.',
 report_generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(ROOT/'summary-statistics.json').write_text(json.dumps(payload,indent=2)+'\n')
lines=['# 五个 harness 同模型单题实测：结果与计量复核','',
 '已完成 1 题 × 5 家 × 3 次正式运行。五家都是 **3/3 通过**，本题没有拉开完成率；耗时、资源和存储出现差别，但三次观测的波动较大。','',
 '题目为 SWE-bench Verified `pytest-dev__pytest-7490`，人工难度 15 分钟至 1 小时。模型统一为 `deepseek-flash`、high reasoning；同一镜像、2 CPU 配额、4 GiB 内存、单次 600 秒。每次 home、工作区、临时目录均重新创建。',
 '固定版本：DSH 0.2.2-rc.1；OpenClaw 2026.11.3；Hermes 84a0301415edd6d1385207ec96e4d7f2b6c1fcd9；Codex 0.167.1；Claude Code 2.1.322。原生协议分别为 Messages、Chat、Chat、Responses、Messages；提示词、工具描述与编排策略保留各家原生实现。',
 '执行时间为 2026-11-11 北京时间约 12:37–13:35，另有此前构建与接入校验；已在五小时时限内完成。','',
 '## 完成与耗时','',
 '| Harness | 通过 | 第 1 / 2 / 3 次耗时秒 | 中位数秒 | 平均数秒 |',
 '| --- | --- | --- | --- | --- |']
for product in products:
 s=stats[product]
 lines.append(f"| {s['label']} | {s['resolved']}/3 | {' / '.join(f'{v:.2f}' for v in s['wall_seconds'])} | {s['wall_median']:.2f} | {s['wall_mean']:.2f} |")
lines += ['',
 '15 份补丁均只修改 `src/_pytest/skipping.py`，新增 2–13 行、删除 0–1 行，符合源码策略。每次独立评分均为 F2P **2/2**、P2P **78/78**，整个受影响文件 **81 passed**；无超时、异常退出或 OOM kill。Base 为 79 passed、2 failed，两个独立 gold 副本均为 81 passed。',
 '',
 'Hermes 中位数为 71.27 秒，但第三次为 536.01 秒；平均耗时为 225.48 秒，超过 Codex 的 168.55 秒和 DSH 的 182.30 秒。该次原始工具记录包含对更广泛测试目录的反复验证。不能从中位数推导“稳定最快”，也不能把这些 CPU/内存全部归因于框架本身的空闲开销。','',
 '## 核心 token 与统一价格估算','',
 '| Harness | 输入总量中位数 | 未缓存输入中位数 | 缓存读取中位数 | 输出中位数 | 峰时参考费用中位数 USD |',
 '| --- | --- | --- | --- | --- | --- |']
for product in products:
 s=stats[product];m=s['medians']
 lines.append(f"| {s['label']} | {m['input_total']:,.0f} | {m['input_noncache_billed']:,.0f} | {m['cache_read']:,.0f} | {m['output_total']:,.0f} | {Decimal(s['peak_reference_usd_median']):.6f} |")
lines += ['',
 '**各列分别取中位数，分桶中位数不一定相加等于输入总量中位数。** 输入总量是每次物理请求的 inclusive 输入之和，含重复发送的上下文与缓存读，并非单轮上下文长度。各家的三次合计缓存命中占输入比例约 96%–98%；本地状态全新不能保证服务端缓存冷态。',
 '',
 f"正式运行共 **394/394 次**转发取得终结、已结算且有效的最终核心 usage，总输入 **{payload['formal_input_total']:,}**、总输出 **{payload['formal_output_total']:,}**。按冻结统一价估算，正式运行合计为峰时 **${formal_peak:.6f}** / 谷时 **${formal_off:.6f}**，不是实际账单。",
 '',
 '本批次另有 5 次接入校验、24 次模型请求，核心 usage 同样完整。本批次合计 418/418；原始响应的 model 均为 deepseek-flash。记录的 17 次 `/api/show` 本地能力探测全部被拦截，未转发模型。',
 '',
 f"包含此前三轮接入校验，整个实验保留 **{payload['experiment_provider_attempts']} 次**模型转发，其中 **{payload['experiment_known_attempts']} 次**有完整核心 usage；早期有 1 次 HTTP 400 未返回 usage，仍标未知。所有这些调用的峰时参考已知小计为 **${Decimal(payload['experiment_peak_known_subtotal_usd']):.6f}**，不能声称是完整账单。两次更早的构建失败未进入模型调用步骤。",
 '',
 'Reasoning 细分只在正式运行的 Chat/Responses 共 **227/394 次**中返回；DSH、Claude Code 的 Messages 未返回，不能填零或作为五家共同排名维度。Reasoning 已包含在输出中，不重复相加；本提供方无独立缓存写入计费桶。',
 '',
 '原生计数另作对账。Hermes 的辅助标题输入字段不含缓存，而主会话字段含缓存，已分别换算；第三次运行还有一笔 CLI 退出回执前到达代理、回执后完成的后台通知后续请求，输入 49,668、输出 96。共同账本保留了它，原生 usage 文件没有包含它。详见 [校验审计](calibration-audit.zh-CN.md)。','',
 '## 资源与存储','',
 '| Harness | CPU 秒中位数 | 内存峰值 MiB 中位数 | 三处逻辑增长 MiB 中位数 | 三处分配增长 MiB 中位数 | 首个模型请求秒中位数 |',
 '| --- | --- | --- | --- | --- | --- |']
for product in products:
 s=stats[product];m=s['medians']
 lines.append(f"| {s['label']} | {m['cpu_seconds']:.2f} | {m['memory_peak_bytes']/1024**2:.2f} | {m['writable_delta_logical_bytes']/1024**2:.2f} | {m['writable_delta_allocated_bytes']/1024**2:.2f} | {m['time_to_first_provider_request_seconds']:.2f} |")
lines += ['',
 '三处指工作区、home、/tmp，先对每次运行求最终减初始值的合计，再取中位数。Hermes 的 home 内还包含测试临时目录，不能把 home 大小直接称作会话日志大小。分配空间按普通文件 st_blocks×512 计算，不含目录/inode 元数据；小文件的分配空间可能远大于逻辑大小，因此两者分别报告。共同安装镜像为约 4.24 GB，未计入运行新增占用；产品包目录仅作诊断，不作为独立安装体积排名。',
 '',
 'CPU、内存、设备 I/O 来自容器 cgroup，包含其测试与其他后代进程。内存峰值取内核 memory.peak。存储最终扫描在容器暂停后进行，全部无扫描错误；逐次文件数、目录数、分配块、工作区/home/tmp 分项、日志/数据库/缓存分类与设备 I/O 均保留在 CSV 和 resources.json 中。',
 '',
 '运行中的目录扫描不是原子快照，采样最大值仅是近似观测，不能宣称精确峰值或严格下界。旧 sampled_peak 对象里未更新的 categories/scan_errors 等字段不是峰值证据；本报告未使用它们。存储主表与图使用暂停后的最终减初始值，旧产物保持原样。','',
 '## 可复核材料','',
 '- [逐次完整指标 runs.csv](runs.csv)、[逐请求 requests.csv](requests.csv)、[统计 JSON](summary-statistics.json)。',
 '- [全部运行图 PNG](comparison.png) / [SVG](comparison.svg)、[详细自动报告](run-report.md)。',
 '- [原生与上游对账](native-provider-reconciliation.json)、[最终 usage 回放](validated-accounting.json)、[独立证据核验](evidence-audit.json)。',
 '- [计量协议](measurement-contract.zh-CN.md)、[接入与计量审计](calibration-audit.zh-CN.md)、[来源与文件完整性](provenance.json)。',
 '- [Actions 原始运行](https://github.com/zyw02/agent-arch/actions/runs/42959922129)；本地 original-artifact.zip 的 SHA-256 与 GitHub 摘要一致，1,974 个原始成员在初次解包时全部逐一匹配。除三份重新生成的派生报告外，其余原始文件未改动。',
 '',
 f"执行源码：`{provenance['execution_commit']}`；后处理源码：`{provenance['analysis_commit']}`。原始压缩包、分离的执行/分析源码归档、全部请求/响应、原生日志和状态、资源样本、15 份补丁、JUnit 与评分结果保存在本地完整归档 `/root/Documents/bench/swe-single-20261111/` 的 evidence/、provenance/ 和 preliminary-calibrations/ 中。仓库仅提交精简结果与分析脚本；完整原始文件也可从上述 Actions 产物取得。",
 '',
 '**结论边界：** 这道公开历史题上，五家完成率相同；资源和耗时的观测差异已留下完整证据。n=3、单题、服务端缓存及验证策略差异限制了推断，不能据此给五个 harness 下总体排名。题目和执行条件未根据结果更换。','']
(ROOT/'report.md').write_text('\n'.join(lines))
for name in ('runs.csv','requests.csv','comparison.png','comparison.svg','plot-environment.json','validated-accounting.json','native-provider-reconciliation.json'):
 shutil.copyfile(C/name,ROOT/name)
shutil.copyfile(C/'report.md',ROOT/'run-report.md')
print(json.dumps({k:v for k,v in payload.items() if k!='products'},indent=2))
