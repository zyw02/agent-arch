# Focused architecture evaluation: two layers, six dimensions

Revision `focused-two-layer-six-dimension-r1` replaces the previous eight-study/four-hour core plan. The user's priority is a small number of complete, informative experiments organized by platform and harness, each covering reliability, security, performance, resource/cost, extensibility and observability. The full catalogue remains reference material rather than an execution checklist.

## Six studies with a clear dimensional structure

| Dimension | Platform study | Harness study |
| --- | --- | --- |
| Reliability | PA: task ownership and fault propagation | HA: preservation of constraints and state through context maintenance |
| Security | PB: identity and authority across external entry points | HB: approval scope bound to actual tool execution |
| Performance | PC: startup, lifecycle and shared-resource contention | HC: dispatch overlap and failure-path latency |
| Resource & cost | PC: fixed service cost and marginal task cost | HA: compaction cost versus subsequent model-input cost |
| Extensibility | PB: public control integration and added responsibilities | HB: public tool integration and ownership of policy/lifecycle |
| Observability | PA: reconstruction of ownership, interruption and recovery | HC: reconstruction of scheduling, failure and retry cause |

Each study has two primary dimensions. Secondary evidence may inform another dimension but must not be counted as a separate experiment or an independent result. Platform questions concern hosting and operating multiple runs; harness questions concern processing and controlling one run.

### PA — task ownership and fault domains

Use one primary task plus one independent healthy companion. Compare healthy execution, client exit and execution-owner exit at the same independently observed request boundary. Record process ancestry, surviving work, companion impact, recoverable state and actual terminal results. Give a reviewer only native records and ask them to locate the interruption and ownership; then check their reconstruction against the independent ledger from the same run.

This reveals who owns the task lifetime, which sessions share failure fate, and whether native records expose those facts. Corroborate with pinned process/source ownership. If client and owner are the same PID, record and coalesce that shared boundary in the frozen binding rather than pretending two distinct interventions occurred. A separate service can decouple client lifetime while creating a shared failure domain; report both consequences where observed.

### PB — public control integration and identity boundary

Connect one minimal external supervisor through a public native entry. Compare an authorized native operation, the same authorized operation through the integration, and a reached unauthorized attempt through that integration. Preserve the same harmless operation and target. Record changed configuration/code, public API, added processes/privileges, principal, actual effect and enforcement owner.

The result explains which control and security responsibilities the platform provides and which the integrator must supply. Count integration surface descriptively; raw lines of code are not a universal extensibility score. Local single-user products are not assumed to implement multi-tenancy: distinguish OS enforcement, product enforcement and unsupported identity surfaces. The wrapper must not manufacture product authorization.

### PC — lifecycle cost and resource sharing

Use five narrowly defined conditions: idle service baseline, cold single task, warm single task, and the same four accepted tasks executed sequentially versus concurrently. Freeze cold/warm cache and service state for the selected deployment; do not silently substitute a long-lived deployment for a command profile. Calibrate the fixture and observer at this fixed load, without an arrival-rate sweep.

Measure accepted completion time, startup, CPU seconds, integrated RSS, process counts and model/tool calls. Idle observation uses a short predeclared sampling interval selected by pilot; active workloads run until all four tasks reach classified outcomes. Compare equal work for concurrency, and distinguish resident cost from task increments. This supports lifecycle/sharing tradeoffs, not sustainable-capacity, p99, leak or long-run stability claims.

### HA — context fidelity and total information cost

Use one long history with immutable constraints, an updated rule and a completed-step receipt. Compare native compaction with an uncompacted run of the identical feasible history, keeping model, tools and final task fixed. Require independently observed next-model requests as well as component output and final task acceptance. Count all summary-generation and downstream calls when calculating usage.

The result explains what the harness treats as durable information, whether its transformation really reaches the model, and the cost/retention tradeoff. A correct component output alone is not success if the downstream request ignores it. If a matched control is impossible, declare the causal comparison unavailable and report only observed behavior. Synthetic summaries test integration; semantic quality requires a real-model configuration. Do not infer external-effect consistency from retained conversation state.

### HB — tool extension and authorization binding

Choose one harmless operation with equivalent native-tool and public-extension implementations. Compare native allowed, extension allowed, extension denied and a changed approved target through a supported public control. Keep the operation, principal and intended target matched. Use the extension's allowed run as the positive control for its denied/changed-target arms.

Record tool schema, extension lifecycle/configuration, approved scope, dispatch arguments and independent effects. This reveals how execution policy crosses the extension boundary and whether extensibility preserves authority. Unsupported mutation or extension surfaces remain explicit capability results; core patches are not used to create a test surface. Scope this study to one tool extension, not every provider/context/executor hook.

### HC — scheduling performance and failure diagnosis

Use the same four independent reads in a serial reference, one batched request, and a batched request with one reached tool failure. Prefer a public native serial/concurrent control. Where absent, label the sequential-model-dispatch arm as a protocol reference and account separately for extra model roundtrips; do not attribute their entire latency difference to the harness.

Inspect model calls, dispatch and T start/end intervals, result identity, surviving successful calls, failure handling and final outcome. Reconstruct the failing call and retry owner from native logs with fixture truth withheld, then compare. Reuse these exact traces for observability; do not launch a separate diagnosis matrix. Non-overlap alone cannot locate a bottleneck without native/source or fixture-concurrency evidence.

## What makes a result architecturally useful

Each finding must state a competing explanation, controlled intervention, independent observation, responsible component, source/contract corroboration, operational consequence and applicability limit. Report the tradeoff, not just pass/fail. Runtime evidence can support implementation mechanisms; original designer intent requires explicit design documentation.

Before formal execution, bind each study to one declared deployment per product and verify that the available observation can distinguish its competing explanations. If it cannot, improve the observation during preparation or mark the question unresolved. A green fixture test is not a completed architecture study. Every planned arm must have a terminal result or a reasoned blocked/unsupported/unobservable disposition. Missing comparison arms prevent a paired conclusion; they must never be silently dropped.

Source inspection, deployment maps and public API documentation support the six studies. Reuse existing traces rather than adding runs for each dimension. The earlier H18 task-family benchmark, broad output-size sweeps, all-component extension matrices, long load tests and standalone side-effect consistency study are deferred. Conclusions must not claim those untested properties.

## Finish complete experiments; control scope before starting

There is no universal 90-second task cutoff or four-hour campaign kill switch. Duration is controlled by selecting these six studies, one deployment per product, two complete comparison blocks initially, and only the conditions above. No Cartesian multiplication over model families, platforms, load rates or extension types is permitted by default.

A comparison block contains a study's full set of matched arms for one product and one input/fixture instance. The initial design contains 36 blocks across three products and 120 planned arms, including idle/control arms. These are structural counts, not a runtime promise. Two blocks test mechanism reproducibility; they do not support population rankings. Pair products on the same fixture instances and interleave order. Predeclare any tie-breaking repeat for conflicting evidence; do not keep repeating until a preferred conclusion appears.

1. During preparation, validate the native entry, positive controls, intervention reachability and observer. Pilot one complete block per relevant configuration to measure installation/startup, ordinary execution, intervention, recovery and evidence collection. Pilot records remain separate from formal evidence.
2. Estimate the duration of an entire study from its complete pilot blocks, including setup, cleanup, real-model latency and expected failure handling. Publish that estimate and its uncertainty before admitting the formal study. Do not launch the full campaign blindly. If the estimate is too long for the agreed session, reduce deployment/condition scope through a separately recorded design revision or defer a whole study; never remove a necessary control merely to fit a clock.
3. Once a valid block starts, let its normal work and native recovery reach the declared terminal criteria. Schedule the next block only when there is enough estimated time to finish it. Stop between blocks/studies when changing scope or ending a session. Preserve completed groups and resumable progress.
4. Genuine hangs still need failure criteria. Freeze per-operation/native deadlines and no-progress detection from the protocol and pilot, with terminal-error, cancellation and cleanup evidence. These identify an execution failure; they are not a universal campaign time quota. An observation window that is itself part of a fault experiment remains predeclared. If infrastructure forcibly interrupts a block, mark it incomplete and make no paired claim from partial arms.

This avoids the former 25–38-hour sustained-load multiplication without promising a fabricated exact duration. Real runtime must come from calibration. Do not return to 30+ hour batches by silently appending deferred catalogue cases. Report experiment runtime separately from development and offline interpretation. Codex execution and paid-provider use retain their existing authorization requirements.

## Plan commands and status

`python3 comparison/expand_campaign.py` (or `--profile core`) now emits the six studies, their layer/dimension coverage, complete comparison blocks, controls and evidence requirements. There are no campaign/task kill-budget fields in emitted units. `--profile full` retains the reference catalogue; it is not an automatic execution fallback.

`plan_core.py` validates three studies per layer, complete six-dimension coverage in each layer, two primary dimensions per study, complete control links and evidence contracts. All output remains `plan_only=true`, `runtime_ready=false`: calibrated adapters, a completion-aware scheduler and the per-study result evaluator are still required before execution. The previous budget-based default is withdrawn.
