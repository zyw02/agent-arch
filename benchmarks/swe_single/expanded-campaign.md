# Four-task hosted campaign

This campaign retains pytest-7490 and adds pytest-7571, pytest-7236 and pytest-7324 from the same immutable SWE-bench Verified dataset revision. All have the human difficulty label `15 min - 1 hour`; this label does not assert identical difficulty. Selection is frozen before new harness outcomes. Each of six products receives three attempts on each task: 72 formal attempts.

Every attempt starts a new container with pristine task source and empty home, session state and temporary directory. No task, memory, transcript or calibration state is reused. Provider-side cache state cannot be reset. Base-fails/reference-fix-passes controls and native tool/usage calibration precede paid formal tasks. Scorers have no network. Gold and hidden patches stay on the controller, outside agent mounts.

All six products use one common image with the previous frozen dependency locks. The image is built once, encrypted before artifact upload, and verified by ciphertext checksum and exact Docker image ID on every worker. CPU stays at 2 cores; container memory increases from 4 to 8 GiB, with swap disabled and identical settings for all six. AIOS is the delivered OpenClaw 5.7 patch and SDK, configured for AgentLoop; calibration and every formal attempt require the SDK `loop.run starting` marker. A successful PI fallback is not admitted as an AgentLoop result.

Task timeout changes from 600 to 1800 seconds; calibration, grading and provider socket timeouts change from 180 to 540 seconds. Relay settlement changes from 15 to 45 seconds. Controller admission budget changes from 14400 to 43200 seconds. Formal Actions step timeout changes from 40 to 120 minutes, and control/calibration step timeout from 20 to 60 minutes. GitHub-hosted jobs have a hard 360-minute limit, so the previous 270-minute job cannot be tripled to 810 minutes. The workload is split into 24 task/product jobs, each with three formal steps and immediate per-stage evidence uploads; at most six jobs run simultaneously. Missing or timed-out stages remain explicit.

The original-task shard for each product also makes three independent initial idle RSS/PSS observations. Each launches its native server/UI with no task, waits for native readiness, settles for 60 seconds, then samples for 60 seconds. Network is `none`, only a local metadata/no-inference stub exists, and real provider credentials are absent. The native process tree excludes the Python measurement helper and stub. OpenClaw 5.7 enables AgentLoop and uses the delivered deployment Node flags used in the earlier local idle observation. Product startup shapes differ: OpenClaw gateways, DSH web, Codex/Claude/Hermes interactive CLIs. These are recorded observations, not identical product interfaces. Hosted jobs do not reproduce the prior local co-resident shared-memory environment.

Live observations every 15 seconds show phase, elapsed time, pending/completed model requests, observed tool names/counts and task-time RSS/PSS. Full native logs stream to disk. Final evidence includes provider requests/responses, native state, process and cgroup samples, patch and isolated hidden-test scores. Task-time memory and idle memory are kept separate. Container memory peaks remain diagnostics, excluded from the previously agreed cost index. All three measured attempts, including timeouts, remain in statistics. Never merge the historical PI campaign into this AgentLoop campaign.

Dispatch the existing `deepseek-preflight.yml` workflow with `mode=enhanced-suite` on the campaign branch. The reusable workflow is `.github/workflows/swe-expanded.yml`. The final collector reports missing attempts and idle coverage instead of substituting zeros.

Recovery notes: task source replacement preserves the image-generated pytest version module and editable-install metadata. The supplied AgentLoop archive has no bundled Apps; AIOS therefore receives the documented user Apps configuration `default/main`, type `complex`, using the SDK's built-in factory, an empty module entry, and no custom executor or extra prompt. Idle AIOS observations must load this same App configuration. Updated idle launcher files are mounted read-only from the recorded controller commit; the product image and dependency locks stay unchanged. `suite_products` can restrict a recovery run to AIOS while already-valid measurements from the other five products continue. Retain both run IDs and only merge the intended product/task/attempt identities once.

## Corrected controls, opt-in V2 campaign

The November 13 request audit found that the V1 relay forced high reasoning onto native non-thinking auxiliary calls, including AgentLoop context compression. AIOS primary requests already enabled reasoning; this is not evidence of missing primary reasoning support. V1 also clipped main outputs to 16,384 tokens, and the controller used a hard-coded relay default instead of the protocol's output setting. Historical evidence remains unchanged and its rankings are provisional.

`suite.py --validated-controls` creates a separate `VALIDATED-V2` protocol. Main requests use a common requested 65,536-token output budget and high reasoning. Explicit native disabled/none requests retain their reasoning intent and smaller native output budget, including compact/classifier calls; tools and prompts are not replaced. The relay call-count limit is disabled, and the 1,800-second task limit remains. Benchmark-imposed native iteration caps are raised to 4,096 as an emergency bound; hitting any bound remains visible, not a normal task-quality failure. The actual protocol output budget is passed into the relay and native launcher. Every attempt records response truncation, missing terminal events and missing final usage separately. Calibration with such an anomaly cannot admit formal tasks.

V2 requires `BENCH_EXPECTED_CPU_MODEL`, `BENCH_EXPECTED_RUNNER_NAME` and an exactly matching `RUNNER_NAME`. It also requires `BENCH_PROTOCOL_PREFLIGHT_RECEIPT` pointing to a successful live six-probe receipt whose control-source hashes match the executing code. Assign the unique runner label to one dedicated machine, register one runner service, serialize campaign jobs and give every attempt fresh containers and memory. These host checks do not assert constant provider cache state, stable network latency or absence of host load. The hosted V1 workflow is not automatically upgraded or rerun with these controls. Old paid Campaign entrypoints now refuse to start by default; `BENCH_ALLOW_LEGACY_REPRODUCTION=1` is reserved for intentional historical reproduction, not corrected measurements.

Dispatch `deepseek-preflight.yml` with `mode=protocol-validation` for a small six-call live protocol check (main/auxiliary across Chat, Messages and Responses). It checks actual request intent, output budgets, response termination and usage coverage without solving tasks. It does not establish complete six-framework compatibility. A native smoke and internal-compaction check must still pass on the selected fixed runner before a new formal campaign; model/context guards and native SDK failures must be reported separately from task-quality failures. Never merge these new measurements into the frozen V1 campaign.
# 2026-11-13：原始失败轮的进一步核查

历史 72 轮数据保持原样；以下修改只进入新的 validated 控制配置。

- AIOS 的交付 SDK 将 `deepseek-flash` 模糊匹配到旧 DeepSeek 表项，得到
  81,384 总窗、65,000 有效上下文和 62,000 阻断线。7324 第一次的实际主请求
  输入 31,645，但 SDK 将缓存重复计入，原始状态重放估算为 63,673，触发
  `Prompt is too long`。最后两个正常结束的请求属于内部压缩，并非用户任务终态。
- 新测试仅在原生模型配置中使用 SDK 支持的 `deepseek-flash[1m]` 上下文提示；
  代理明确白名单映射回同一个 `deepseek-flash`。实际供应商模型、工具、消息不变。
  模型发现必须证明上下文至少 1,000,000。交付 SDK、源码 patch、依赖锁不修改。
  这不会修改 SDK 的缓存计数算法；原始 usage 与计费仍完整保留。
- 代理新增上游/下游字节数、SHA256、HTTP framing 及终止分类。已经发送 SSE
  响应头后发生异常时直接关闭流，禁止把第二份 HTTP 502 响应写入 SSE 正文。
  不伪造终态或最终 usage，不暗中重试已计费请求。
- DSH 两次历史断流请求的原始/有效正文哈希相同，不能归因为正文改写；历史缺少
  分段传输证据，不能仅凭 EOF 确认网络、服务端或代理的责任。`proxy-forensics`
  单独下载原请求，交替顺序各做一次直连与代理重放，并验证六种协议意图。
  重放不执行工具，不是整题重跑，也不进入原性能、费用或成功率排名。
- Hermes 7324 第三次把同名测试标签 `True`、`False`、`None` 当作 Python 常量，
  改变了 matcher 语义。其历史轮还出现 16K 输出截断，故不能把该轮作为完全排除
  测试条件干扰后的产品能力结论。

## 2026-11-13：两题、同一宿主机重测

入口为 `deepseek-preflight.yml` 的 `two-task-same-host` 模式。只创建一个
360 分钟 job，复用原始加密镜像与冻结题目 7236、7324；六产品各题三次，共
36 次正式测试。先完成两题隐藏测试对照、六产品工具/usage 校准，然后按预先
记录的六个轮换顺序串行执行。AIOS 第一批首先执行，严格启用原交付 AgentLoop。

按用户最新要求，全部产品使用实际分配的全部 vCPU，明确记录型号、可用核数、
CPU quota、affinity、boot ID 与 runner name；每次执行重新验证同一宿主身份。
每个校准/正式任务前均测原生初始空闲：同题基线源码、无网络、无模型推理、
稳定 60 秒后采样 60 秒 RSS/PSS。空闲进程随后移除，任务以全新 HOME、工作区、
临时目录和会话启动；这是配对的独立空闲进程测量，不是同一任务进程暂停测量。
内存统一 8 GiB、禁用 swap；各产品原生 UI/Gateway 与 CLI 的启动方式留档。

任务上限仍 1800 秒、模型请求与验收各 540 秒。不再人为限制每轮 64 请求，
主输出预算 65536，保留原生辅助请求的关闭推理意图。绝不为赶六小时缩短某家
预算：剩余时间不足以容纳完整尝试时停止新任务，明确记录未完成项，并保留
每批原始记录及最终进度。该新 CPU 规格与旧多机数据分开分析，不合并排名。

首次同机运行 43277577553 在第一道正式题的空闲观察阶段发现 Gateway 定时
心跳发起 `Read HEARTBEAT.md` 模型请求，观察进程按设计拒绝推理并退出；尚未
执行任何正式答题。控制器配置现对 AIOS 与 OpenClaw 均显式设置
`agents.defaults.heartbeat.every=0m`，保持 AgentLoop SDK/app 初始化和 60+60 秒
窗口。正式任务也关闭定时心跳，避免后台任务污染。同机任务会话标识带上本轮
实验及题目标识，临时目录仍每次重建。36 个正式尝试分别成为独立 Actions 步骤，
每个尝试立即审计和上传记录，便于监控与定位；完整 36 次均在同一个新 job 内测。
