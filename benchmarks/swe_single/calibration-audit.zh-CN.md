# 计量校验的实测记录

下列均为独立工具冒烟任务，**不属于正式解题成绩**。它们用于核查同名字段的语义、
主会话之外的调用覆盖，以及环境错误是否会被误判为解题失败。

## 原生计数不能直接混加

首轮完整校验产物来自 [Actions 42957434671](https://github.com/zyw02/agent-arch/actions/runs/42957434671)，
控制器提交为 `eff2acf`。以下数字均可在该产物的 `campaign/runs/smoke-*/` 中复核。

| Harness | 原生计数 | 独立上游账本 | 结论 |
| --- | --- | --- | --- |
| DSH | stdout 中 4 个 step-end；输入合计 22,538，输出 492 | 5 个真实请求；输入 22,750，输出 596 | 多出的标题调用为 212 输入、104 输出，不能漏计 |
| OpenClaw | CLI meta.agentMeta.usage：input=9,713，cacheRead=28,032，output=688 | 输入总量 37,745，输出 688 | 原生 input 不含缓存，须加 cacheRead；不能拿 input 直接与 Codex 的 inclusive input 相比 |
| Codex | turn.completed：input_tokens=37,496，cached_input_tokens=28,288，output_tokens=1,325 | 同样是 37,496、28,288、1,325 | 这次普通工具循环的核心计数一致；不代表中断等其他状态自动完备 |
| Hermes | 主任务 3 次调用，输入 21,276、输出 470；成功辅助调用 1 次，输入 311、输出 132 | 5 个真实请求，其中 4 个有核心 usage、1 个 HTTP 400 没有 usage | 主任务之外确实有费用相关调用，且失败尝试不能从原生成功调用数推断出来 |

DSH 的 `provider/0000/request.original.json` 明确是生成会话标题的请求；其主模型工具循环
没有包含这笔消耗。其余 4 笔请求与原生 step-end 的输入、输出及缓存计数能够对齐。

Hermes 的无 usage 请求是标题生成的 `response_format=json_schema` 能力拒绝，之后回退成功。
账本保留已知小计：输入 21,587、输出 602，同时标注 `usage_complete=false`。
没有账单证据时，不能把无 usage 的失败尝试推断成测得的零消耗。

## 接入修正属于环境校验

- Hermes 使用通用 custom provider 时，标题调用未提前识别 DeepSeek 的 JSON Schema 能力限制。
  改用原生 DeepSeek provider 身份与其正式 base-URL 覆盖后，
  [Actions 42958224927](https://github.com/zyw02/agent-arch/actions/runs/42958224927) 中已通过工具与核心 usage 校验。
  保留了辅助调用，未通过关闭标题生成功能来掩盖消耗。
- Claude 的 variadic `--disallowedTools` 最初吞掉了 prompt，修复参数边界后实际开始请求。
  随后 CLI 显示的 model_not_found 原因是记账代理没有接受原生
  `/anthropic/v1/messages?beta=true` 路径；这是代理返回的 404，不是 DeepSeek 模型不存在。
  [Actions 42959085438](https://github.com/zyw02/agent-arch/actions/runs/42959085438)
  保留了这两个被拒请求。路由修正增加了真实 HTTP 前端回归测试，保留并转发原始 beta 查询参数。
- 当前 OpenClaw 状态使用 SQLite；不能假定每个版本都存在 JSONL transcript。
  该轮已归档 agent/state 数据库，CLI 结果同时包含 usage 和 toolSummary。

上述失败均被校验门禁拦截，未计为正式解题失败。题目、隐藏测试、三个区组顺序和正式资源
上限没有根据这些校验结果变更。后续正式结果以独立运行产物为准。

## 存储与资源的实测来源

首轮 DSH、OpenClaw、Hermes、Codex 校验均取得真实 cgroup 与文件扫描数据。
例如 DSH 的 cgroup `memory.peak` 为 291,131,392 字节、设备写入计数为 114,688 字节；
home 的逻辑字节增长为 22,444，分配块增长为 53,248。这些数字说明计量链路已经工作，
并非正式任务的资源排名。

同一轮某些设备读取计数为零，并不表示没有读取文件：Linux 页缓存命中时可以不产生新的
设备读取。逻辑文件大小、分配块、设备 I/O、内存峰值的范围必须分别解释。
