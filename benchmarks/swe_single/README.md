# Five-harness single-task comparison

中文执行协议与指标口径见 [measurement-contract.zh-CN.md](measurement-contract.zh-CN.md)。

SWE-SINGLE-01 compares DSH, OpenClaw, Hermes, Codex and Claude Code on the same
DeepSeek model, with native tools and orchestration. This separately authorized
experiment does not change the historical OpenClaw campaign or its frozen scope.

The five-hour session constraint controls task selection and execution: one
SWE-bench Verified task, three independent runs per product, ten minutes per run
(150 minutes maximum formal agent time). Leave time for installation, gold/base
controls, tool/usage calibration and analysis. Do not select a replacement after
examining which product wins. Equal results are legitimate observations.

## Frozen task and acceptance

`pytest-dev__pytest-7490` has a human difficulty of 15 minutes to one hour, two
FAIL_TO_PASS cases and 78 PASS_TO_PASS cases. The issue concerns dynamically
added xfail markers, strict unexpected passes and test/report hook timing. The
21-line reference production change is not exposed to agents. `select_task.py`
binds the full task record to an immutable dataset parquet and SHA-256.
The issue text, including its original environment listing, is identical for all
five products. No hints, hidden tests, reference patch or original Git objects
enter the agent image or container mounts.

`pytest-5787` was demoted before any candidate execution because its 1–4 hour
human difficulty and larger serialization change are too heavy for this time
budget. `pytest-10356` was rejected because its hidden test introduces an API
parameter not explicitly specified by its issue. Public benchmark contamination
remains possible; this experiment cannot establish an overall harness ranking.

Before paid calls, require both hidden fix cases to fail on base, then require
two fresh gold controls to pass the whole affected test file. Grade candidate
production changes in a clean snapshot with hidden tests and no network. Test
and configuration modifications fail policy. Primary completion requires native
CLI success within the time limit, source policy acceptance, and resolution of
every F2P/P2P item. Also retain patch-only resolution independently. P2P skipped
cases follow current SWE-bench maintenance semantics; missing tests fail.
This is a SWE-bench-derived single-task experiment with an independently
validated JUnit scorer, not an official leaderboard submission.

## Common data and exact sources

| Data | Common source for all five products | Precision and limitations |
| --- | --- | --- |
| Fix and regression acceptance | Clean scoring container, hidden patch, JUnit and all test output | Per-case statuses, missing cases and application errors retained |
| Wall time | Controller monotonic start to native CLI exit receipt | Same launch boundary; polling delay excluded from successful CLI exit time |
| Time to first model request | First admitted relay request minus controller start | Startup preparation, not provider first-token latency |
| Model latency | Relay headers, first bytes, first meaningful event and terminal timestamps | Preserve each attempt and parallel-interval union; no inferred tokens/second |
| Request and response counts/bytes | Unique per-run fixed-origin relay | Includes native retries, auxiliary work and child requests using that route |
| Input, noncached input, cache hits, output | Raw upstream terminal usage normalized by protocol | Core counters must exist; unknown is null, never zero |
| Reasoning and cache creation | Raw protocol-specific usage fields | Optional subset/coverage fields; reasoning is never added to inclusive output |
| Estimated cost | Frozen DeepSeek peak/off-peak tariff applied to each recorded usage | Same reference tariffs for all products; known subtotal retained if incomplete; not an invoice |
| CPU, memory, device I/O and PIDs | Linux cgroup v2 counters and 0.5-second samples | All container descendants; memory.peak is kernel peak when available; I/O is physical device accounting |
| Workspace, home and /tmp storage | Independent initial/final filesystem scans and 2-second samples | Logical regular-file bytes, allocated blocks, file/directory counts; sampled peak is a lower bound |
| Native state breakdown | Frozen user-home files classified as logs, DB/WAL/SHM, caches and other | Raw native state archived; filesystem metadata overhead excluded |
| Package footprint | Exact package lock and common image metadata | Shared dependencies and common runtimes must not be misrepresented as exclusive product size |
| Patch size | Initial/final source hashes and independent unified diff | Added, deleted, modified files and source-policy violations |

Harness-specific metrics remain diagnostic: a native step, dispatched tool,
completed item, SDK retry, compaction or approval has different semantics across
products. Preserve native types and IDs; do not rank their raw counts as though
they were interchangeable. Model-emitted tool calls are separate from actual
native execution and can be compared only with that scope label.

### Token accounting contract

DSH and Claude Code use DeepSeek's native Messages endpoint; OpenClaw and Hermes
use Chat Completions; Codex uses Responses. There is no protocol/tool/message
translation. The relay changes only preregistered reasoning/output controls and
requests streaming usage where supported. Original and effective bodies are both
retained. DeepSeek documents that compatibility paths may increase effective
Messages output limits for some clients: 16,384 is a common requested limit,
not a proven strict service cap.

Messages input is uncached input plus cache-read and any explicit creation
counter. Chat/Responses input is inclusive, so subtract cache hits to obtain
the common noncached billing bucket. Preserve creation counters when returned;
DeepSeek has hit/miss billing, not a separately billed cache-write tier. Missing
reasoning cannot be compared as zero. Stream usage updates are cumulative and
merged, never summed as increments. Each physical attempt is counted once.

Every run gets a distinct relay and fresh home/workspace. Only three fixed-origin
inference endpoints and local model listing are exposed. Direct external
retrieval and provider-side web tools are blocked. The real provider credential
exists only in the host controller; CLIs receive a placeholder. Child/auxiliary
traffic that attempts another route cannot silently escape measurement.

The relay keeps reading an already-admitted upstream response if a client
disconnects, to preserve billed usage when possible. Unsettled, interrupted,
missing-counter and error attempts remain explicit. `usage_complete` requires
every forwarded attempt to have terminal, settled, valid core usage. Zero is
accepted only when reported. Retain raw native usage for reconciliation; native
main-session totals alone are not proof of whole-run billing completeness.

Each native tool smoke must read an unpredictable receipt, run Python, write
the independently checked digest and return complete core provider usage before
formal comparisons are admitted. Synthetic controls separately validate all
three wire mappings, cumulative usage, overlap, missing usage, clean grading,
storage accounting and a real HTTP relay frontend without paid model calls.

## Native collection adapters

| Product | Execution | Additional native evidence |
| --- | --- | --- |
| DSH | Headless JSON CLI, explicit API-key route | Status/tool JSONL, compressed session event logs, retry/compaction/approval event types |
| OpenClaw | Local agent, explicit isolated workspace/state | CLI result, assistant transcripts and usage, session DB/schema if present |
| Hermes | Native oneshot CLI with usage file and local coding toolsets | Main and auxiliary usage report, state DB/WAL/SHM and native logs |
| Codex | Native exec JSONL, custom Responses provider | Turn usage, completed command/MCP/file-change items and persisted rollouts |
| Claude Code | Native print stream-json with verbose events | Final usage/modelUsage, assistant tool IDs and project/subagent transcripts |

`native.py` labels unsupported projections as unknown. SQLite schema inventory
uses immutable main-file inspection to avoid changing the frozen state; raw WAL
and SHM are retained for subsequent complete offline inspection. Only the
common provider ledger is used for primary token comparison.

## Run and retain

Use the existing `deepseek-preflight.yml` Actions workflow on the research branch
with `mode=calibration` or `mode=formal`; the default `connection` mode preserves
the earlier connection check. Formal mode first runs every control and all five
native calibrations, then the three rotated complete blocks on one disposable
host. The same built image, CPU/memory limits and installed task dependencies
apply to all five products; the Python environment used by the task is distinct
from Hermes' supported interpreter. All versions and the actual image ID are
recorded. Installation is excluded from solving time.

Artifacts include source/environment hashes, locks, controls, order, per-run
results, raw original/effective requests, timestamped SSE, upstream usage,
stdout/stderr, native state, storage/resource samples, patches and scoring
output. Collector trace/archive storage is separate from product storage.
Scan all files and decompressed native archives for the real credential before
artifact publication. Preserve calibration failures as environment/collection
failures; never replace them with task failures or fabricated zero usage.

After downloading an evidence artifact, regenerate the analysis with
`python3 benchmarks/swe_single/verify_usage.py <campaign-directory>`, then
`python3 benchmarks/swe_single/report.py <campaign-directory>` and
`python3 benchmarks/swe_single/reconcile.py <campaign-directory>`.
The verifier replays retained wire events and requires final usage evidence;
original ledgers and run results stay unchanged. The report separates all-run
consumption from successful-run consumption, and exports storage categories,
device I/O, coverage, and known partial token subtotals in `runs.csv`.
`requests.csv` retains each physical or blocked attempt, replayed counters,
final-usage flags and relay-observed latency boundaries. Its first-byte field is
an HTTP/SSE byte boundary, not a claim about model-token generation speed.
The optional `plot.py <campaign-directory>` uses Matplotlib to show every formal
observation in PNG/SVG; its version and input/script hashes accompany the plot.
Native/provider reconciliation names each native counter's scope and preserves
differences instead of treating agreement as proof of completeness.

Primary sources: [SWE-bench](https://www.swebench.com/SWE-bench/guides/quickstart/),
[frozen dataset](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/tree/c104f840cc67f8b6eec6f759ebc8b2693d585d4a),
[DeepSeek Messages](https://api-docs.deepseek.com/guides/anthropic_api/),
[DeepSeek Responses](https://api-docs.deepseek.com/guides/responses_api/),
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing.md),
[Codex JSONL](https://learn.chatgpt.com/docs/non-interactive-mode),
[Claude Code print mode](https://code.claude.com/docs/en/headless),
[OpenClaw usage](https://docs.openclaw.ai/reference/token-use),
[Hermes observers](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks).

Task issue/reference code retain their upstream pytest MIT license; the dataset
is distributed by its upstream maintainers. No upstream license is changed.
