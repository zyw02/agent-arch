# 五小时、五个 harness 的同模型实测协议

主测题冻结为 SWE-bench Verified 的 `pytest-dev__pytest-7490`：动态添加 xfail
标记后的执行与报告行为。数据集人工难度为 15 分钟至 1 小时，隐藏集合包含
2 个 FAIL_TO_PASS 和 78 个 PASS_TO_PASS。它是公开历史题，不能排除训练污染；
一次单题实验也不能保证一定拉开差距。

五家均使用 `deepseek-flash`、high reasoning，2 核、4 GiB 内存，单次解题限时
600 秒，各做 3 次。正式解题上限共 150 分钟。先在独立目录完成原生工具与
usage 校验，再按固定种子轮换顺序运行 3 个区组；校验不计入正式成功率。
安装与环境校验耗时单列。每次使用全新 home、工作区与临时目录，禁止跨次记忆。

## 什么可以直接横向比较

| 指标 | 五家共同来源与边界 | 完整性规则 |
| --- | --- | --- |
| 解题完成 | 原生 CLI 正常结束、未超时、改动符合 src/ 策略、独立评分副本的 F2P/P2P 全部满足 | 同时保留仅补丁通过与完整运行通过，逐项保存测试状态 |
| 成功比例 | 固定题目每家 3 次的观测比例 | 不将它解释为总体成功率，不合并校验运行 |
| 端到端耗时 | 控制器启动容器前至原生 CLI 结束回执，单调时钟 | 超时、中断和异常退出单列 |
| 启动准备耗时 | 同一启动边界至首个被转发的模型请求 | 不能用各家第一条日志代替；不能保证 provider 缓存冷态 |
| 请求、响应与延迟 | 每次运行独占的固定上游记账代理 | 每个实际转发尝试只记一次，保留失败尝试和重试；并发耗时取区间并集 |
| 输入、未缓存输入、缓存读、输出 | 三种原生 API 返回的原始 usage，按下表换算 | 所有转发尝试均终结、已结算且核心计数有效，才标 usage_complete |
| reasoning、缓存创建 | 上游确实返回的字段 | 保存字段覆盖率；reasoning 是输出子集，缺失不记零 |
| 估算成本 | 已记录的 usage × 冻结的 DeepSeek 峰/谷参考价 | 价格口径一致；不完整时仅列已知小计，不宣称实际账单 |
| CPU、内存、设备 I/O、进程数 | Linux cgroup v2，包含容器内全部后代进程 | 内存优先使用内核 memory.peak；设备 I/O 与逻辑文件大小分别报告 |
| 存储占用 | 外部扫描工作区、home、/tmp 的初始值、最终值和每两秒样本 | 逻辑字节、分配块、文件/目录数分别记录；运行中为非原子采样近似值，最终扫描时暂停容器 |
| 安装体积 | 同一镜像的实际 ID/大小，以及安装目录逐文件扫描 | 产品包目录仅作诊断，共享依赖不能重复宣称为产品独占体积 |
| 代码改动 | 初始/最终源文件哈希、独立 unified diff | 包括新增、删除与修改文件，不依赖 agent 自己建立 Git 仓库 |

模型发出的工具请求可按共同协议口径统计，但不等于工具实际执行成功。
原生步数、工具数、重试、压缩、审批、子代理仅作诊断：保留原生类型、ID 与原始日志，
未支持的投影为 null。未观察到审批也不能证明发生了零次操作系统提权。

## 各家怎么接入、怎么保留原始证据

| Harness | 原生执行与协议 | 额外保留 |
| --- | --- | --- |
| DSH | headless JSON；DeepSeek Messages | stdout 状态/工具事件、压缩会话日志、原生 usage、重试/压缩/审批事件类型 |
| Claude Code | print + verbose stream-json；DeepSeek Messages | 最终 usage/modelUsage、assistant tool_use ID、项目与子代理会话文件 |
| OpenClaw | local agent，明确指定隔离 workspace/state；Chat Completions | CLI 结果、assistant transcript、usage、数据库与 schema |
| Hermes | 原生 oneshot，隔离 HERMES_HOME，开启 usage-file；Chat Completions | 主/辅助调用 usage 文件、state.db/WAL/SHM、原生日志 |
| Codex | exec JSONL，自定义 Responses provider | turn usage、完成的 command/MCP/file-change 项、持久化 rollout |

共同 token 比较以代理上游账本为准；原生 usage 用于复核和解释差异。
代理不转换协议、工具或消息，不自动重试；仅按冻结协议统一 reasoning/输出请求上限，
以及在支持时请求流式 usage。原始请求与实际转发请求均保留，便于审计。

## Token 口径

| 协议 | 输入总量 | 未缓存计费输入 | 缓存读取 | 输出 |
| --- | --- | --- | --- | --- |
| Messages | input_tokens + cache_read_input_tokens + 显式 cache_creation_input_tokens | input_tokens + 显式 cache_creation_input_tokens | cache_read_input_tokens | output_tokens |
| Chat | prompt_tokens | prompt_tokens − 缓存读取 | prompt_cache_hit_tokens；或 prompt_tokens_details.cached_tokens | completion_tokens |
| Responses | input_tokens | input_tokens − input_tokens_details.cached_tokens | input_tokens_details.cached_tokens | output_tokens |

DeepSeek 按缓存命中/未命中计费，本轮没有单独的缓存写入计费桶。原始缓存创建字段照存；
缺失值不伪造为测得的零。reasoning 只在返回时展示，绝不重复加到 inclusive output。
流式 usage 是累计快照，按字段合并，不能逐条相加。

超时后代理尽可能继续读取已被接纳的上游响应，以取得其最终 usage。
未终结、断流、错误或缺少核心字段的尝试，均保留未知标记。看见一部分数字不代表全次
运行的账已完整；原始事件与每请求覆盖率必须一起审阅。

## 存储口径

- 分开报告工作区、会话目录、临时目录；会话目录再按日志、数据库/WAL/SHM、缓存和其他分类。
- 逻辑大小是普通文件的 st_size；分配空间是 st_blocks × 512，同一范围内按 inode 去重硬链接。
- 不跟随符号链接；目录/inode 元数据不计入上述文件字节。运行期间每两秒扫描，停止后冻结容器并做最终扫描。
- 运行中扫描会与创建、移动、删除文件并发，不是原子快照；采样最大值可能漏掉瞬时峰值，也可能受扫描竞态影响，不能宣称精确峰值或严格数学下界。
- cgroup io.stat 是设备 I/O，不能冒充应用程序逻辑读写量。/dev/shm 等 IPC tmpfs 不在路径扫描内，相关内存计入 cgroup。
- 评测器的请求账本、stdout/stderr、打包归档另存，不算成 harness 会话目录开销。
- 安装目录数据区分共享 npm 树、各产品包目录、Hermes 环境、共同 Python 与任务环境，不将它们简单相加排名。

## 评分与验收

付费调用之前，要求 base 的两个修复用例全部失败，两个独立 gold 副本通过受影响测试文件。
候选评分在全新的初始副本中只叠加 src/ 改动，再由控制器加入隐藏测试，断网运行。
修改测试/配置等策略违规单列，不能靠候选目录中的测试插件或缓存改变判分。
PASS_TO_PASS 的 skip 语义沿用当前 SWE-bench 维护口径；缺失用例失败。

每家校验必须读取一个不可预测的文件、执行 Python、写出独立核验的摘要并返回完整核心 usage。
任一家校验失败就暂停正式解题，先修复接入或采集问题，不把环境故障计为能力失败。

原始产物包括版本/镜像/源快照哈希、锁文件、运行顺序、原始及有效请求、时间戳 SSE、usage、
stdout/stderr、原生状态归档、资源/存储样本、补丁及逐项评分；另生成 runs.csv 和中文 report.md。
实际观测以 Actions 产物为准，本文件只定义协议，不能代替实测通过证明。
