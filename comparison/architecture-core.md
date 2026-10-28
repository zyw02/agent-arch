# Focused architecture evaluation: two layers, six dimensions

Revision `focused-two-layer-six-dimension-r2` extends the prior focused plan with explicit persistent memory, native collaboration and harness security studies. The user's priority is a small number of complete, informative experiments organized by platform and harness, each covering reliability, security, performance, resource/cost, extensibility and observability. Platform retains three studies. Harness now has four studies explicitly covering persistent memory, native multi-agent coordination and trust/authority boundaries. The full catalogue remains reference material rather than an execution checklist.

## Seven focused studies with a clear dimensional structure

| Dimension | Platform study | Harness study |
| --- | --- | --- |
| Reliability | PA: task ownership and fault propagation | HA: context/memory fidelity; HB: collaboration and child lifecycle |
| Security | PB: identity and authority across external entry points | HC: dispatch authority, untrusted input, child grants and memory scope |
| Performance | PC: startup, lifecycle and shared-resource contention | HB: collaboration critical path and failure recovery |
| Resource & cost | PC: fixed service cost and marginal task cost | HA: memory/context lifecycle and total model cost |
| Extensibility | PB: public control integration and added responsibilities | HD: public tool integration and lifecycle responsibility |
| Observability | PA: reconstruction of ownership, interruption and recovery | HC: security decisions; HD: execution/failure reconstruction |

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

### HA — context and persistent memory

Use two separate matched pairs, so compaction and memory retrieval are not confounded. Pair 1 uses identical feasible long histories with native compaction enabled/disabled; inspect component output, the next actual M request and final constraint acceptance. Pair 2 uses an identical fresh-session task with native persistent memory enabled/disabled. Seed a few small records through the product's native memory interface, update a durable fact, verify its write, restart the process and start a genuinely new session. The new prompt must not contain the remembered answer. Check retrieval provenance/version, the updated value, and a current explicit instruction that conflicts with an older preference. The memory-disabled arm may correctly report unknown; that is not a product failure.

Measure native write/update/consolidation/retrieval, memory injection into model input, final acceptance and all model/tool usage. Pin store location, namespace and lifecycle. This identifies what is durable versus transient, who selects remembered information, how updates and current instructions interact, and the corresponding cost. A fixture manually pasting stored facts into the prompt is not native memory. A correct context component return value is not integration unless the next model request uses it. Use one relevant record and a few distractors rather than a retrieval benchmark corpus. General retrieval quality remains out of scope; cross-principal disclosure is tested explicitly in HC.

### HB — native multi-agent coordination

Use one small task with two independent subtasks, distinct child artifacts and one required combined result checked by an independent oracle (for example, reconciling two synthetic data partitions). Compare: one agent doing the same total work; two product-native child agents with the parent joining results; one child encountering a reached tool failure; parent cancellation while one child is held at an observed boundary. All child-failure/cancel arms use the normal two-child run as their matched positive control.

Record native parent/child identities, task/context bindings, message or artifact handoff, join events, accepted combined output, partial work, retry owner, parent cancellation and child cessation. Measure critical-path time and aggregate parent-plus-child model/tool usage, including duplicated context. Successful child termination alone is insufficient if the parent loses a result, joins the wrong result or falsely reports complete work. Reuse the same process/tool records to detect orphan work after cancellation. Freeze native cancellation and no-progress criteria in the pilot; no arbitrary campaign-clock truncation applies.

This reveals who owns child lifetimes, how results are synchronized, what failure/cancellation propagates, and the latency/duplication tradeoff. Independent subprocesses created by the adapter are not evidence of native multi-agent support. If a product lacks delegation, confirm through its pinned native interfaces/source and report the responsibility it leaves outside the harness. An unfinished adapter is blocked, not proof that the product lacks the feature. These short tasks measure coordination mechanisms rather than broad gains in intelligence.

### HC — harness authority and trust boundaries

Security includes policy enforcement, untrusted information, delegated authority and memory isolation. Use four small matched pairs, each with an explicit actor, trusted scope, protected synthetic asset, attempted violation and independent effect oracle:

| Pair | Allowed/clean control | Intervention | Required observation |
| --- | --- | --- | --- |
| Approval binding | Authorized write to synthetic target A | Attempt target B after approval for A through a public native control | Approved object/scope, final dispatch arguments, actual effect or native denial |
| Untrusted information | Legitimate task with clean tool output | Add an instruction in that lower-trust tool output to perform an unrelated forbidden synthetic operation | Content provenance, model attempt, native policy decision and synthetic effect/sink ledger |
| Child authority | Child performs a permitted read under its delegated grant | The same child attempts an operation outside its read-only grant | Parent/child effective grants, credential/capability provenance and actual child dispatch/effect |
| Memory scope | Owner retrieves its private synthetic memory canary | Another principal/session attempts that same record through the native scoped path | Store scope contract, requesting identity, retrieval attempt, returned model-visible content or denial |

A forced deterministic request tests execution enforcement. A real-model untrusted-content pair tests whether that particular injection induces a forbidden attempt and whether execution is then blocked. Report `attack_attempted`, `policy_decision` and `effect_observed` separately. If the model never attempts the operation, record that behavioral outcome; do not claim the enforcement boundary was exercised. Conversely, deterministic denial does not establish real-model prompt-injection resistance. Keep model/configuration paired and avoid a large attack-payload sweep. Use only synthetic canaries and local test sinks; no production assets or credentials enter the experiment.

For delegated authority, a parent's broader ambient permission must not silently replace the declared child grant. If the product exposes no child-grant attenuation, report that boundary as unsupported rather than manufacture enforcement in an adapter. For memory, test the advertised account/project/session scope: intentionally shared memory is not mislabeled as a privacy bug, but its actual ownership and limits must be explicit. Permission prompts alone do not establish security. Blinded reconstruction of principal, scope, denial and effect from native logs supplies the observability assessment using these same records.

### HD — tool execution and extension responsibility

Keep the native/public-extension comparison: one equivalent read-only operation through both paths, then the same four extension reads as a serial reference, a batch, and a batch with one reached failure. Reuse the installed extension and fixture from HC where configuration/permissions match, while keeping control identity and evidence provenance explicit. Record configuration/code changes, public schema, lifecycle and policy owner, actual invocation, model roundtrips, dispatch/T intervals, correlated results and remaining successful work.

Prefer native serial/concurrent controls; if the provider serializes calls, identify its extra roundtrips rather than credit all speed differences to harness scheduling. Reconstruct the failed call and retry owner from native records before consulting the independent fixture ledger. This measures public extensibility and traceability, with scheduling evidence as a secondary performance result. Raw extension code size is descriptive, not a universal ranking. Four independent reads do not establish correctness for conflicting writes.

## What makes a result architecturally useful

Each finding must state a competing explanation, controlled intervention, independent observation, responsible component, source/contract corroboration, operational consequence and applicability limit. Report the tradeoff, not just pass/fail. Runtime evidence can support implementation mechanisms; original designer intent requires explicit design documentation.

Before formal execution, bind each study to one declared deployment per product and verify that the available observation can distinguish its competing explanations. If it cannot, improve the observation during preparation or mark the question unresolved. A green fixture test is not a completed architecture study. Every planned arm must have a terminal result or a reasoned blocked/unsupported/unobservable disposition. Missing comparison arms prevent a paired conclusion; they must never be silently dropped.

Source inspection, deployment maps and public API documentation support the seven studies. Reuse existing traces rather than adding runs for each dimension. The earlier H18 task-family benchmark, broad output-size sweeps, all-component extension matrices, long load tests and standalone side-effect consistency study are deferred. Conclusions must not claim those untested properties.

## Finish complete experiments; control scope before starting

There is no universal 90-second task cutoff or four-hour campaign kill switch. Duration is controlled by selecting these seven studies, one deployment per product, two complete comparison blocks initially, and only the conditions above. HC has four explicit security pairs; each is a short boundary probe rather than a long attack campaign. Reuse seeding, tool integration, child artifacts and logs where the paired conditions genuinely match; do not count reused evidence as another independent repetition. No Cartesian multiplication over model families, platforms, load rates or extension types is permitted by default.

A comparison block contains a study's full set of matched arms for one product and one input/fixture instance. The initial design contains 42 blocks across three products and 192 planned arms, including idle/control arms. These are structural counts, not a runtime promise. Two blocks test mechanism reproducibility; they do not support population rankings. Pair products on the same fixture instances and interleave order. Predeclare any tie-breaking repeat for conflicting evidence; do not keep repeating until a preferred conclusion appears.

1. During preparation, validate the native entry, positive controls, intervention reachability and observer. Pilot one complete block per relevant configuration to measure installation/startup, ordinary execution, intervention, recovery and evidence collection. Pilot records remain separate from formal evidence.
2. Estimate the duration of an entire study from its complete pilot blocks, including setup, cleanup, real-model latency and expected failure handling. Publish that estimate and its uncertainty before admitting the formal study. Do not launch the full campaign blindly. If the estimate is too long for the agreed session, reduce deployment/condition scope through a separately recorded design revision or defer a whole study; never remove a necessary control merely to fit a clock.
3. Once a valid block starts, let its normal work and native recovery reach the declared terminal criteria. Schedule the next block only when there is enough estimated time to finish it. Stop between blocks/studies when changing scope or ending a session. Preserve completed groups and resumable progress.
4. Genuine hangs still need failure criteria. Freeze per-operation/native deadlines and no-progress detection from the protocol and pilot, with terminal-error, cancellation and cleanup evidence. These identify an execution failure; they are not a universal campaign time quota. An observation window that is itself part of a fault experiment remains predeclared. If infrastructure forcibly interrupts a block, mark it incomplete and make no paired claim from partial arms.

This avoids the former 25–38-hour sustained-load multiplication without promising a fabricated exact duration. Real runtime must come from calibration. Do not return to 30+ hour batches by silently appending deferred catalogue cases. Report experiment runtime separately from development and offline interpretation. Codex execution and paid-provider use retain their existing authorization requirements.

## Plan commands and status

`python3 comparison/expand_campaign.py` (or `--profile core`) now emits the seven studies, their layer/dimension coverage, complete comparison blocks, controls and evidence requirements. There are no campaign/task kill-budget fields in emitted units. `--profile full` retains the reference catalogue; it is not an automatic execution fallback.

`plan_core.py` validates three platform and four harness studies, complete six-dimension coverage in each layer, two primary dimensions per study, complete control links and evidence contracts. All output remains `plan_only=true`, `runtime_ready=false`: calibrated adapters, a completion-aware scheduler and the per-study result evaluator are still required before execution. The previous budget-based default is withdrawn.
