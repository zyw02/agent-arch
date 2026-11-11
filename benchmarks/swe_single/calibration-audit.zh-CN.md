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

## 正式批次的闭环核验

[Actions 42959922129](https://github.com/zyw02/agent-arch/actions/runs/42959922129)
已完成，执行提交为 `9b281ab`。五家各 3 次均通过，全部 15 次都满足 2 个 F2P、78 个
P2P，以及整个受影响测试文件的 81 个用例。正式运行共 394 次转发，严格重放后的最终核心
usage 覆盖率为 394/394；本批次另有 5 次工具校验、24 次转发，同样全部完整。
Messages 未返回 reasoning 细分；正式运行仅 Chat/Responses 的 227/394 次有该字段，
因此不能把 reasoning 细分作为五家共同排名维度。

Hermes 的原生字段需要进一步区分：当前固定版本的 DeepSeek 主会话 `input_tokens`
是 inclusive 输入，但辅助标题的同名字段是未缓存输入。例如 block-1 的主会话为
185,933、辅助未缓存为 183、辅助缓存读为 256；三者合计 186,372，与上游账本一致。
该语义已加入原生对账投影和基于真实计数的回归测试，原始数据与共同账本没有修改。

block-3 Hermes 还出现了一笔尾部调用：原生 usage 文件记录主调用 37 次、辅助 1 次；
账本实际有 39 次转发。`provider/0043/request.original.json` 最后一条消息是后台命令
完成通知。该请求于 CLI 退出回执之前约 1 毫秒被接纳，最终响应在退出后约 1.6 秒结算。
其输入为 49,668（其中缓存读 48,768）、输出为 96，恰好解释修正辅助输入口径后剩余的
对账差值。代理继续读取上游响应，最终完整记下了这笔消耗；未将它算作零。

本批次 DSH 工具校验中的标题调用另有 227 输入、86 输出；主步骤汇总未包含这笔，
共同账本已包含。15 次正式运行的对账中，除上述 Hermes 尾部请求外，其他投影与账本
核心计数一致。对账一致只说明本次记录相符，不代替最终 usage、终结状态与结算状态校验。

正式批次的存储峰值结构还有一处投影限制：`sampled_peak` 仅更新了 logical_bytes、
allocated_bytes、files、directories 四个标量；其中的 categories、scan_errors 等其他字段
沿用了初始快照，不能解释成峰值时的分类或完整性证据。本报告和 CSV 只读取这四个更新过的
标量；目录分类与扫描错误取自暂停后的 final 快照。后续采集器已移除峰值对象中的这些
未更新字段，原始产物保持原样。

同时将“存储采样峰值是下界”的措辞收紧为“非原子扫描的近似最大观测”：运行中并发移动、
创建和删除文件可能产生扫描竞态，不能给出严格数学边界。报告的存储主表与图采用暂停后的
最终减初始快照，内存峰值采用内核 cgroup memory.peak，不受这项采样表述修正影响。
原始执行协议与其哈希保留在产物中；这些是事后精度澄清，未改变题目、评分或运行设置。
