# Architecture-first core campaign

This is the default research plan after the user's requirement for architectural insight and rejection of 30+ hour experiments. It supersedes the full campaign's default execution order and sample counts. The full catalogue remains a reference; it is not authorized for automatic execution. Revision: `architecture-core-20261028-r1`.

## What the experiments can establish

The deliverable is a responsibility map and a set of supported architectural tradeoffs. Each claim must connect **competing explanations → one controlled intervention → independently observed boundary → mechanism attribution → operational consequence → applicability limit**. A pass count alone is insufficient. Runtime behavior can establish a mechanism under tested conditions; an author's original intent requires explicit design/source documentation and must not be invented from behavior.

| Study | Intervention and observation | Architecture question | Important limit |
| --- | --- | --- | --- |
| K01 ownership/fault domains | Normal, kill entry, kill core; inspect processes and an independent healthy companion | Who owns work, and which sessions share failure fate? | If entry/core are the same PID, record the shared boundary and coalesce duplicate intervention; service presence alone does not establish availability |
| K02 persistence/effects | Normal versus native resume after commit-before-ack, with external deduplication off/on | What is persisted, what is replayed, and who supplies idempotency? | Attribute scripted model decisions and service deduplication separately from harness recovery |
| K03 authority | Same operation allowed, denied, or revoked before dispatch; inspect independent effects | Where and when is authority enforced? | Tests a defined boundary, not general security certification |
| K04 context | Same long history with/without native compaction; inspect transformed output and next M request | What information is retained, and does the harness actually adopt the transformation? | Same-history arms must be feasible; synthetic summaries show integration, not real summarization quality |
| K05 scheduling | One read versus four independent reads delivered together; trace dispatch/start/end | Where is concurrency introduced or serialization imposed? | A serial result needs native dispatch/source evidence to distinguish harness from service bottlenecks |
| K06 lifecycle/resources | Short idle, one-task and four-task observations | What fixed/marginal costs accompany the chosen process lifecycle? | No sustainable-throughput, leak, p99 or long-run stability claim |
| K07 extension boundary | Normal read-only tool extension versus a controlled extension fault | What is delegated across the extension boundary, and who handles failure? | Freeze one common extension surface; do not multiply provider/context/executor variants by default |
| K08 task consequence | Three distinct small real-model tasks, each normal and with one tool fault | Does the observed mechanism affect accepted task delivery? | Illustrative paired evidence, not a broad model/product leaderboard |

K01/K02 provide the platform/harness responsibility map. K03 supplies authority evidence. K04/K05 explain context and execution control. K06 connects structure to cost. K07 explains extension coupling. K08 checks whether a mechanism has practical task consequences. H17 reuses these traces for causal reconstruction; it launches no additional product runs. P04 setup/interfaces and source/design-document inspection accompany the responsibility map.

The remaining H04 output-size sweep, H11 parameter permutations, H14 all-component fault/cancel matrix, extensive H18 families and P03 long soak are not default runs. Reuse an already available matching result where justified, or record them as deferred. Any additional runtime study must replace allocated core slots within the same budget or require a separately agreed campaign; no automatic expansion.

## Discriminating evidence instead of a scorecard

Before running each study, freeze the product/profile/configuration, native interface, competing explanations, input hashes, intervention boundary, positive controls and independent observations in `architecture-core.json` plus the adapter binding. Use one selected deployment per product. Record actual extra services and privileges; do not silently multiply local/gateway modes. Cross-product outcomes describe these deployments. Prefer within-product paired changes for causal attribution, then compare the observed mechanisms.

For example, a client kill with continuing model requests, a surviving worker and a completed independent effect supports service-owned execution. A client kill alone with missing output does not identify ownership. Likewise, duplicates disappearing only when the external service deduplicates support a service dependency; that is not proof of harness-owned exactly-once execution. A correct C6 transform that is absent from the next M request is failed context integration.

Corroborate each mechanism with a pinned source path/configuration or native protocol contract where available. When a boundary cannot be observed, an intervention cannot be reached, or the evidence cannot distinguish the proposed explanations, label the claim unresolved and specify the missing observation. Do not turn uncertainty into a product failure or invent a design rationale.

Each final finding records: claim; tested deployment; positive control; intervention and independent receipt; before/after outcome; mechanism owner; source/contract evidence; cost/benefit; alternative explanations eliminated or remaining; and confidence limited to the tested conditions. No composite winner score is required.

## Four-hour total runtime budget

The core plan allocates exactly **48 units per product, three products, 144 units total**:

- K01: 3 conditions × 2 units = 6.
- K02: 4 conditions × 2 units = 8, including both no-fault deduplication controls.
- K03: 3 conditions × 2 units = 6.
- K04: 2 arms × 2 matched histories = 4.
- K05: 2 conditions × 3 units = 6.
- K06: 3 conditions × 2 units = 6.
- K07: 2 conditions × 3 units = 6.
- K08: 2 conditions × 3 distinct task instances = 6.

Every unit has a **90-second inclusive limit** covering launch, boundary reach, the observation window, any native recovery, evidence flush and cleanup. Maximum unit runtime is 144 × 90 = 12,960 seconds (216 minutes). Installation, shared fixture calibration, tool/provider positive controls and binding checks get **8 minutes per product**, 24 minutes total. Aggregate charged runner time and campaign wall time are each capped at **240 minutes**. This is a configured worst-case experiment budget, not a measured duration or a promise that every product supports every scenario. Parallel jobs cannot increase the aggregate allowance.

Use at most 30 seconds for each K06 observation window. Fixture concurrency/overhead checks are shared and charged to setup; use a short check at the fixed four-task load rather than a sustained rate ladder. If those checks cannot establish sufficient fixture capacity within budget, report K05/K06 attribution unresolved. Do not launch a 30-minute load sweep to repair the result.

The runtime supervisor must reserve a unit slot and remaining time before launch, use one monotonic wall deadline and an aggregate runner-time ledger, enforce process-group cleanup inside each slot, and stop before the cap. A reservation that would exceed either cap is rejected. Installation or adapter setup exceeding its allowance marks the configuration blocked and prevents product tasks. Invalid controls, unavailable interfaces and timeouts remain in the evidence; replacement attempts consume existing slots, never extra repetitions. No automatic reruns, per-product four-hour resets, extra deployment profiles or fallback to the full matrix are allowed.

Two repeats in deterministic mechanism probes check reproducibility only. Three real-model task pairs are examples, not independent-population estimates. Preserve failures and censored timings; do not report statistical superiority, capacity limits or long-term reliability from this core plan. If the first valid pair shows the observation surface cannot discriminate explanations, stop that study and report the gap instead of consuming all repetitions.

Implementation/debugging time and offline interpretation are separate from this experiment-runtime budget and must be reported separately. Real-provider cost/model availability and Codex execution retain their existing authorization constraints. An unavailable real-model arm remains untested; scripted fixtures cannot replace it while retaining the task-quality claim.

## Plan commands and readiness

```sh
# Default: bounded architecture core, including questions and budget calculation
python3 comparison/expand_campaign.py
# Equivalent explicit core plan
python3 comparison/expand_campaign.py --profile core
# Reference-only full design; not default and not authorized for automatic execution
python3 comparison/expand_campaign.py --profile full
```

`plan_core.py` rejects unit expansions or configured ceilings exceeding the four-hour core budget and requires the architecture evidence contract for each study. All emitted rows are `plan_only`; `runtime_ready=false`. A bounded runtime supervisor and calibrated adapters must exist before these rows can run. Plan validation proves budget arithmetic and specification completeness, not actual runtime enforcement or experimental results. The runner must implement the deadline/ledger rules above before execution; it must never interpret the reference full matrix as an automatic fallback.
