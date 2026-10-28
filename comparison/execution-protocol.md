# Two-layer, six-dimension execution protocol

**Default execution scope:** the [focused two-layer, six-dimension plan](architecture-core.md) defines seven complete studies: three platform and four harness studies. Duration is controlled by scope and pilot-based admission of complete comparison blocks, without a universal task cutoff or campaign kill budget. Long soak and full-factor sweeps are deferred reference work.


This protocol defines the initial cross-product campaign for Codex, DeepSeek Harness (DSH), and OpenClaw. The [catalogue](experiment-index.md) explains the purpose of each experiment; the scenarios below define the inputs, operations, measurements, and acceptance rules. The [progress table](../README.md#research-progress) records implementation and execution status. The [campaign manifest](campaign.json) lists every case, condition, repetition baseline, and implementation state.

Revision `cloud-review-20261028-r2`: [review controls](review-controls.md) are normative for capacity calibration, statistical analysis, required observations and failure classification. The matrix remains calibration-required.

## 1. Coverage

Each cell identifies its primary experiment and the observation used for the assessment. Additional dimensions can draw on the same evidence.

| Dimension | Platform layer | Harness layer |
| --- | --- | --- |
| Reliability | P01: process termination and task ownership; P02: restart and state | H05: session and effect recovery; H07: model retry |
| Security | P05: identity, state and endpoint access boundaries | H11: execution approval and policy binding |
| Performance | P03: task concurrency, startup and contention | H08: tool scheduling and dependent operations |
| Resource & cost | P03: process-tree resources and idle service cost | H03/H04/H07: context, output and retry usage |
| Extensibility | P04: external entry and operational integration | H14: integration and lifecycle of an added tool |
| Observability | P01/P04: fault visibility and operational diagnosis | H17: reconstruct a model–tool–effect chain |

## 2. Frozen campaign inputs

**Products and entry points.** Record exact binary version, package digest, release/commit if available, platform, entry, configuration hash, and startup command in the run manifest. Start with DSH `0.2.2-alpha.2`, OpenClaw `2026.10.7` (release commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`), and the Codex CLI binary and release resolved and pinned before its first execution. Capture the full dependency lock and Node version for JavaScript packages. A new version creates a new campaign configuration. The existing OpenClaw campaign is a separately pinned baseline.

**Deployment profiles.** Profile A is an isolated local command: Codex `codex exec --json` plus `codex exec resume`, DSH headless `--json` and `--session-id`, OpenClaw `agent --local --json` and an explicit session ID. Profile B measures a long-lived service when supplied by the selected product: OpenClaw Gateway; the equivalent native long-lived DSH/Codex entry if selected and successfully calibrated. Report profile A and B separately; profile B's actual components are part of the result. For interactive approvals, use a native interactive/API entry capable of accepting approval responses; record that entry separately from A. Codex's documented app-server supports thread/turn events and approval handling ([OpenAI documentation](https://developers.openai.com/blog/codex-as-a-platform)).

**Host isolation.** Run only on disposable GitHub-hosted Linux runners. Use a fresh temporary home, workspace, credentials, port allocation, service state, and process group per unit; set the product-specific home/state environment variables explicitly. Synthetic secrets and loopback fixture endpoints are used throughout. Run products in paired blocks on the same runner image with randomized order; preserve independent state between products. Record runner image, CPU count, available memory, kernel, Node/Python versions, time source, and competing background load.

**Comparison tracks.** Track N uses each product's native selected model and defaults with common tasks, permissions and external fixture; it compares product configurations. Track C uses the same model/version, generation settings and fixture tools wherever supported; it estimates harness-level differences while retaining each harness's prompts and context behavior. Track D uses the scripted fixture provider to issue predetermined actions and fault responses; it examines execution semantics rather than model task quality. Report tracks separately. Configuration differences and inaccessible observations are recorded in the result.

**Budget and repetitions.** Deterministic controls and faults use 3 fresh units per product/profile/case; resource and scripted latency conditions use 6 fresh units. Real-model timing is descriptive within the task-instance design below; H08 Track D uses six repetitions. Real-model task instances use 5 unique fixtures × 3 repetitions per product/configuration. A task timeout is 180 s, a held-fault reach timeout 60 s, restart observation 60 s, and cancellation follow-up 10 s with checks at 0.5/2/10 s. Service response delay is 250 ms unless the case specifies another delay. Real provider requests use a user-provided credential via GitHub Secrets; log request usage and actual prices if supplied, and report unknown amounts as unknown. The scripted fixture performs no paid calls.

**Controls and outcome codes.** Each case includes a matched positive control with the same task/fixture and permitted access. Record independent fault/denial reachability. Use separate `validity` (`valid`, `fixture_error`, `adapter_error`, `trigger_not_reached`), `capability` (`supported`, `unsupported`, `unobservable`, `untested`) and `outcome` (`success`, `failure`, `safe_indeterminate`, or null) fields. A reached positive-control request that fails because of the product is a valid failure; retain it and leave dependent fault units unexecuted. Fixture failures/unreached triggers are not product failures. Preserve all valid failures and side effects; disclose excluded counts and reasons. Per-scenario pass/fail wording below describes acceptance criteria, not a combined result field. Apply the [review controls](review-controls.md) denominator rules; never synthesize recovery, retry, approval or deduplication in the adapter.

## 3. Common fixtures and measurement contract

**Model fixture M.** A loopback HTTP service supports OpenAI Chat Completions, Anthropic Messages, and OpenAI Responses with streaming and non-streaming responses as required by each configured provider. It writes an append-only synthetic request/event ledger including `unit_id`, monotonic timestamp, protocol, request number, messages and tool schemas or hashes, response type, and socket close. The fixture supports `ack`, `503_once`, `hold_before_response`, `hold_after_tool_call`, `large_context`, and `scripted_calls`. Responses are protocol-conformant and provide consistent synthetic usage; usage supplied by M is fixture metadata, not real billing. Codex Responses and DSH/OpenClaw adapters must pass the positive control before fault scenarios. The existing `comparison/session_probe.py` implements only a subset of M and provides the DSH/OpenClaw normal-session calibration.

**Tool fixture T.** A loopback MCP server and equivalent product-native shim expose the same operations: `read(key, delay_ms)`, `read_after(key, expected_version)`, `write(key, expected_version, value)`, `create(effect_id, idempotency_key?)`, `large(size_bytes, marker_position, return_reference)`, and `fetch(reference)`. Each invocation writes `call_id`, effect ID, parameters hash, received/start/end timestamps, result and committed state to an independent ledger. Each test resets the datastore. `create` can hold its response after durable commit; in the idempotency-enabled variant, T deduplicates only the same caller-supplied key and logs every invocation. The harness remains responsible for the key it sends and its retry behavior. The shim only translates transport/schema and never retries or enforces the expected result.

**Operating-system observer O.** Sample the product process tree and service processes every 100 ms for RSS and CPU; record process/parent IDs, executable, exit/signal, listeners, state file paths, and lifecycle timestamps. Count shared service baseline and marginal task resources separately, and exclude M, T, and the controller. RSS is a sum of per-process resident memory, reported with that definition. Record missing counters as unavailable.

**Approval driver A.** A native client handles product-provided approval prompts or APIs. It records requested operation, request ID, action, decision and time; it can approve, deny, and revoke only through supported product controls. T's ledger proves the dispatched operation and effects. If an entry cannot receive an approval decision, select a supported native interactive entry; if no entry exposes the operation, record the capability and retain the common safe-task control.

**Artifacts.** For every unit retain manifest, sanitized native events/logs, model/fixture event ledgers, operating-system samples, acceptance JSON, time and usage fields, and the script and configuration hashes. Use only synthetic contents in committed artifacts; retain compact immutable evidence and hosted run IDs. Per-product adapter manifests declare native, public extension, external component, unsupported, or unobservable for each capability and explain how to start, submit, cancel, resume, inspect, and inject faults. Codex's adapter is specified now and remains unexecuted until the user authorizes Codex runs.

## 4. Platform layer

### P01 — Reliability: fault domains

Inputs: M `hold_before_response`; task `Return ACK for <unit_id>`; one client and one session. Conditions: P01-C0 no fault; C1 kill the submitting client after M confirms request; C2 kill the execution process at the same boundary; C3 kill a tool process after T logs entry into `read`. Run C1/C2 on every profile that exposes distinct processes; if client and core are the same PID record the common boundary. OpenClaw Gateway and embedded are distinct profiles. For C3 the positive control must first invoke T.

Steps: start profile; submit task; wait for independent `request_received` or T `start`; terminate the named PID with SIGKILL; observe O and M/T for 10 s; restart the component where supported; use the native resume mechanism once, then observe for 60 s. The fixture remains alive.

Acceptance and metrics: C0 reaches a successful final response. Record fault PID, child survival, model connection, session availability, whether work completes independently, resumed result, time to recovery and external effects. Classify task completion, explicit interruption, ambiguous status, false success and collateral impact separately. Use the tool ledger to assess effects when a fault case performs a write. The structural finding is the actual process ownership and fault propagation; manual and automatic recovery are separate outcomes.

**Paired fault-isolation extension:** Run a second independent healthy session throughout C1–C3, with a baseline unit without a fault. Record its completion, latency and effects, and the number of other sessions interrupted. Classify task recovery and collateral impact separately; correlate both with the observed process boundary.

### P02 — Reliability/security: state and deployment

Inputs: two turns `SESSION_MARKER_<unit>` and `CONTINUE_<unit>`, M `ack`; fresh workspace. Conditions: C0 two turns within one process; C1 restart the entry or client between turns; C2 for a service profile restart the service between turns. Execute one session per unit.

Steps: submit first turn and wait for durable completion and product exit/idle; snapshot file paths and hashes under the owned state root; restart as specified; resume the same session ID; submit second turn. M independently inspects the second request for the prior user marker, assistant ACK, and second input. Record session, workspace, credentials and log ownership and access modes using O, with secret values excluded.

Acceptance and metrics: C0 and C1 pass when both turns succeed and all three elements appear in the second request; C2 uses the same criterion. Record actual state location, processes that can access it, restart steps, elapsed time, and missing state. P05 separately measures actual access enforcement. [Detailed session protocol](first-wave-protocol.md#p02--h05--reconstruct-a-session-after-normal-exit).

**State-consistency extension:** Before restart record a user-confirmed instruction, a completed tool receipt, and a pending operation. After restart check which are reconstructed and whether the pending operation is repeated. The independent tool ledger supplies the effect oracle.

### P03 — Performance/resource & cost: workload and footprint

Inputs: M `ack` with fixed 250 ms delay. Conditions C0 idle service for 30 s; C1 cold one-task; C2 four independent sessions concurrently; C3 eight independent sessions concurrently; C6 one task with one tool read and a verified final answer, separately under direct and external-FIFO admission. C6 is the matched tool positive control for C5; C1 remains its separate model-only performance reference. For a command-only profile, C0 records no service baseline. Use six independent units per condition and randomize product order. Each task must return its own `ACK_<task_id>`; exact service delay is fixed.

Steps: initialize a fresh profile; for C0 start only required resident components; for C1–C3 launch the declared tasks with a barrier, wait up to 180 s, then sample for 10 s after completion. O samples every 100 ms. Record retries and failed/unfinished tasks.

Acceptance and metrics: report task completion/attempts, elapsed wall time, per-task p50 and observed distribution, aggregate tasks/min, peak and time-integrated process-tree RSS, CPU seconds, startup time, residual processes, and idle service cost. Only valid ACKs count as completed. Six units support descriptive distributions; retain raw values and omit p99. Same-machine results compare configurations and profile choices, including their additional components.

**Sustained-load extension:** C4/C5 are gated by fixture capacity calibration and a load-freeze record as specified in [review controls](review-controls.md). The following arrival levels are candidates; only two selected common levels enter formal execution. Add C4 and C5: 30 minutes after a 2-minute warmup, alternating fast (250 ms) and slow (2 s) responses, at arrival intervals of 2 s, 0.5 s and 0.1 s in separate load levels. C5 adds one 250 ms tool read per task. Submit directly at each scheduled arrival; record offered and accepted load and all rejection or timeout outcomes. Run a separate externally limited deployment with an eight-active-task FIFO queue; record planned arrival, supervisor dispatch, product acceptance and completion timestamps. At the end of 30 minutes stop arrivals and drain for at most 180 seconds; classify remaining active and queued tasks separately. The external FIFO holds at most 1,000 waiting tasks and rejects arrivals when full. Queue timeout is 180 seconds from planned arrival; execution timeout is 180 seconds from actual dispatch. Record generator delay, queue timeout, execution timeout, product rejection and drain expiry separately. Run six independent units per condition; retain the complete arrival and dispatch ledger. Capture per-class completion, queue delay, interference, memory and failure rate. Establish a no-contention baseline; compare service and per-task profiles on the same host.

### P04 — Extensibility/observability: external control

Inputs: a minimal external supervisor running on the same host; one task `Return ACK_<unit>`; a second task held at M. Conditions: C0 submit/observe a successful task; C1 cancel while M holds the response; C2 resume a previously completed session with a new turn. Use each product's documented native CLI or API from a supervisor, preserving product-specific request formats.

Steps: implement an adapter using public entry points; record exact changed files/config, source lines in the adapter (excluding fixture and SDK dependencies), setup commands, new processes, and privileges; perform C0, C1, C2. Poll product-native status and independent M events. The supervisor does not manufacture cancellation or session history.

Acceptance and metrics: C0 succeeds when native output and M agree; C1 records cancel acknowledgment, connection closure, product stop and post-cancel activity at 0.5/2/10 s; C2 requires prior history plus new prompt visible to M. Report implementation surface, integration steps, supported operations, external components and their lifecycle. Absence of a native remote entry is recorded along with the adapter needed for the target deployment.

**Integration assessment:** Report entry coverage, additional services, permissions, state ownership, cancellation ownership and upgrade-sensitive interfaces. Record implementation effort as descriptive context with implementer and method.

### P05 — Security: platform identity and state boundaries

Inputs: two synthetic identities A and B with separate state/workspace roots; a random synthetic canary file owned by A; a synthetic Gateway or service token for A when the profile has a remote endpoint. C0 A reads its permitted canary; C1 B attempts to read A's private state through the product's supported access path; C2 unauthenticated or B-token access to A's service endpoint; C3 invalid credentials on B's normal task.

Steps: create the identities and profiles with the product's documented isolation controls, record OS UID and permissions, and perform each request through the native access path. The synthetic task asks for the exact canary string; independent fixture/server logs and file permissions establish access. For local single-user profiles, run A and B under separate OS users and report OS controls as external to the product. For profiles without a remote endpoint, mark C2 `unsupported` and record the deployment path used to expose one.

Acceptance and metrics: C0 must succeed to validate setup. C1/C2 pass if the unauthorized principal cannot obtain the canary or invoke A's task; C3 passes when B is denied and A's valid control remains usable. Record principal, configured boundary, actual file/endpoint effect, access denial, and operational cost. P05 measures a defined platform isolation claim; it does not assume that a product is a multi-tenant server.

**Product authority extension (C4):** Within each supported shared deployment, create two isolated sessions with distinct synthetic credentials and workspaces. For each attempt record the requesting identity, credential ID, native interface, target session or resource, and expected authorization. Attempt cross-session state access, credential reuse and control-entry access using native interfaces, with positive controls for each identity. Require an independent request-reached or policy-decision event before classifying denial; a task that never attempts access is inconclusive. Record enforcement owner and actual effects. Report OS-user isolation separately from product-enforced boundaries.

## 5. Harness layer

### H03 — Reliability/resource & cost: compaction and constraints

Inputs: one task with six exact constraints: output path, protected file, computation rule, required marker, receipt of completed step, and a rule updated from v1 to v2. Place constraints in early/middle/recent turns and fill the history with fixed-hash distractor text. Conditions C0 short history, C1 one native compaction, C2 two native compactions, C3 C1 followed by restart. Separately record automatic and user-triggered compaction. Track N or C uses matched real-model task instances; D can inspect request transformations with M.

Steps: establish baseline; build the same history under the declared model context profile; trigger compaction through the native control or threshold; record whether compaction was reached; ask for the final artifact. Run five distinct fixtures × three repetitions for real-model outcomes. If no public compaction trigger exists use the automatic threshold and report trigger and resulting request visibility; lack of such control is a capability result.

Acceptance and metrics: score each of six constraints, updated rule adherence, completed-step repetition, artifact acceptance, compaction count, tokens by request, retries, and end-to-end time. Compare C0/C1/C2/C3 within the same model configuration. Direct input inspection establishes retention; black-box task outcomes establish observed behavior.

**Matched-history control (C4):** Construct identical long histories for the comparison and compare native compaction with an uncompacted run of the same history where the product exposes that control. Run five task instances and three repetitions per arm; record the exact history hash. Capture pre/post model-visible input and the six constraints. When compaction cannot be controlled, report the observed threshold transition as a separate behavioral study; do not mix it with the controlled comparison.

### H04 — Reliability/resource & cost: large output handling

Inputs: T `large` returns exactly 8, 64, or 256 KiB with three unique markers in head/middle/tail; conditions C0 content only and C1 a retrievable full-content reference. An independent oracle checks exact marker values. Track D instructs the model fixture to invoke T and then reports the received result; Track C/N asks the real model to retrieve all markers.

Steps: reset T; submit the same task with size and reference condition; capture tool result as the product delivers it, subsequent model request when observable, extra `fetch` calls and final answer. Run three deterministic units or five real task instances × three repetitions per condition.

Acceptance and metrics: exact 3/3 marker match; bytes delivered, truncation flag, number of retrievals, tokens and elapsed time. Classify missing model-visible data separately from data present but unused. Mark request payload visibility unavailable when the entry does not expose it.

**Task extension:** Add a structured dataset whose correct aggregate requires values distributed throughout the tool output. Verify the final aggregate and required edits against an independent oracle. Record whether full content and retrieval are supplied by the tool fixture or by the harness.

### H05 — Reliability/observability: state and side effects

Inputs: P02 C1 for session recovery; T `create(effect_id, idempotency_key?)` with independently durable receipt. Conditions C0 no fault, separately with idempotency on and off; C1 terminate before T dispatch; C2 terminate after T commits but before its response; C3 terminate after product records tool result. For each fault use R1 automatic restart, R2 native resume, and R3 explicit user retry; run T with idempotency disabled and enabled.

Steps: wait for the independent T commit event in C2 and for a product-native durable-record event in C3, then kill the relevant product process. Record the event source and timestamp; if the product offers no observable or controllable C3 boundary, mark C3 unobservable. A fixture response-send event establishes a remote boundary only. Execute the chosen recovery path once, and inspect T's actual call/effect counts plus native trajectory. Each (fault, recovery, idempotency) tuple uses three independent units; unsupported recovery paths are retained as capability entries.

Acceptance and metrics: C0 produces one effect and matching acknowledgment. In fault cases classify one effect with correct acknowledgment, one effect with explicit uncertainty, zero effects, duplicate effects, and false success; record key provenance, retries, state retained, and time. `pass` is assigned only to the expected single-effect outcome for that declared interface contract; explicit uncertainty is reported separately as a safe indeterminate outcome. Exactly-once expectations depend on the service and product contract.

**Attribution:** Log dispatch and commit boundaries, model decisions after resume, every retry, idempotency-key creation and service deduplication. Compare automatic continuation and explicit user retry separately; the fixture never invents a key or repeats a call.

### H07 — Reliability/resource & cost: model retry

Inputs: M C0 `ack`, C1 `503_once`, C2 disconnect before first response byte, C3 disconnect after one response chunk. Use one fresh session and a no-tool task; freeze the native retry settings per profile.

Steps: submit the same user marker; M records every request, timing, partial response and disconnect; wait for the product's terminal result. Run three fresh units per condition and capture configured retry maxima and budgets.

Acceptance and metrics: C0 must succeed. Fault cases report final status, request count, delay, repeated history, partial-response handling, product retry classification, and token usage where available. A correct success requires exactly one coherent final answer and no duplicated user history. A terminal error is reported as a product outcome with attempt count; it is not discarded. C3 is calibrated separately for each wire protocol.

### H08 — Performance/reliability: tool scheduling

Inputs: T with 250 ms calls. C0 four independent `read` calls; C1 B reads the version written by A; C2 two writes target the same record in known order; C3 one of four reads fails while the others succeed; C4 slow and fast calls return out of order. Track D sends a fixed sequence when the native model/tool protocol supports it; Track N/C uses a real model and the same user request.

Steps: reset T; run the case; capture M requests, T dispatch/start/end events, call IDs, native result events and final datastore; allow 180 s. For C1, send the dependent call only after the first response. C1 establishes cross-turn result propagation under provider-imposed ordering; it cannot establish that the harness discovers or schedules dependencies. Test harness-owned dependency ordering separately only through a supported native dependency contract, documenting its representation and enforcement owner. For C2, deliver both writes in one model response and record the product’s actual scheduling; record product-chosen behavior for real-model runs.

Acceptance and metrics: C0 needs four correctly matched results; C1 requires B's observed version to match A's committed version; C2 reports the committed order and final state against the product’s documented ordering contract; C3 preserves three successful results and exposes the error; C4 results match call IDs. Report overlapping intervals, wall time, retries, and final correctness. Serial execution can satisfy correctness; concurrency is reported as a separate measure.

**Scheduling control:** In the independent-read and conflict cases, deliver all calls in one model response and let the product decide dispatch. For a separate native dependency study, evaluate only ordering guarantees actually advertised by the product; record unsupported guarantees separately. The fixture records time and effects without serializing calls on behalf of the product.

### H11 — Security/observability: execution approval

Inputs: a synthetic write to T and one permitted read control. C0 approve the exact operation; C1 deny it; C2 approve A and attempt parameter/target B; C3 revoke a grant before dispatch; C4 restart and attempt reuse. Drive approvals through A using a native interactive/API entry. For an endpoint without tool-level approvals, test an equivalent supported execution surface and record the operation and enforcement boundary.

Steps: establish a policy that prompts for the write; hold dispatch until A records decision; perform the condition; record approval request ID, decision/scope, policy effective time, actual dispatch and T ledger. The parameter mutation is performed through a public native control if available; otherwise C2 is marked unsupported and the corresponding approved/denied control remains valid.

Acceptance and metrics: C0 produces exactly the approved effect; C1/C3 produce no effect after denial/revocation is effective; C2 requires a new approval or a denial before B executes; C4 follows the documented grant lifetime. Record prompt count, allowed/blocked effects, policy provenance and timing. An absent approval surface is reported as a capability gap and does not silently become a passing control.

**Approval contract:** Before each case record the native approved object, scope, lifetime and enforcement point. Match these to the actual dispatched operation and distinguish unsupported parameter mutation from an authorization failure.

### H14 — Extensibility: tool lifecycle

Inputs: T exposes `read` and `create`; profiles baseline B0 without T and B1 with T configured through a documented public extension surface. Conditions C0 discovery and invocation, C1 T startup unavailable, C2 T exits during an operation, C3 disable/remove T and start a fresh session, C4 two tools with different names coexist.

Steps: use product-native configuration or documented public plugin/API; record files, lines of adapter code, dependency list, setup commands, restart requirement and policy settings; run C0–C4 with M driving the equivalent call. After each failure inspect product status and recovery using its public interface. Keep the independent T effect ledger.

Acceptance and metrics: C0 returns the expected receipt; C1/C2 expose failure and retain product control; C3 makes T unavailable in a new session; C4 preserves both tools' distinct identities. Record code/config changes, installation and recovery time, failed call propagation, cancellation/cleanup, and which component owns state and permissions. A product-native shim may bridge a transport, but its code and resource cost are reported separately.

**Component extension:** C5 connects the same synthetic provider; C6 installs a context component over input `KEEP: output=results.json` and `DROP: distractor-7345`; its successful normal transformation contains KEEP and omits DROP; C7 replaces the execution component using a public interface where available. Run three independent units per condition/state using the [R2 acceptance table](review-controls.md#h14-c5c7-normal-failure-and-cancellation-acceptance). Compare canonical normal C5/C7 results with their normal oracle and C6 history with the transformed oracle; fault/cancel hashes are diagnostic only. Inject failure and cancellation at the declared public component boundary; record ownership of state, policy, usage, cancellation and recovery, the public API used, and any core changes; require KEEP retention in any successful C6 normal/fallback result, and DROP removal in the normal transformation; record a failed-transform native fallback separately. Record unavailable extension points as capabilities.

### H17 — Observability: causal reconstruction

Inputs: one task includes a model request, an approved T `create`, a transient T failure, a retry or a terminal failure, and an independent effect receipt. Use a no-fault positive control and a fault variant. M/T/O retain the ground truth separately from the product's accessible native logs.

Steps: freeze the case and product records; give a blinded investigator only product-native records and the task identifier. Ask for user request, model request ID, tool name/parameters, approval/policy source, fault and retry reason, final effect, and terminal status. The investigator can answer unknown. Compare answers with the withheld M/T/O ledger. Use three investigators and randomized product/case order when available; report individual results.

Acceptance and metrics: C0 requires a correct observable effect in T. Score each reconstructable link, correct/unknown/incorrect claims, diagnosis time, log access privileges and needed external data. Provide a field-level trace completeness table; an explicit unknown remains distinct from a confident incorrect claim. Preserve native trajectory, recovery state, and telemetry as separate sources.

**Diagnosis protocol:** Freeze a question set and answer key against the external ledger before assigning records. Score each investigator separately as correct, unknown or incorrect, together with diagnosis time and required access. Reuse the same fault records from P01, H05 and H11 when their native evidence is sufficient.

### H18 — End-to-end task delivery

Inputs: three task families: repository change with hidden tests, data reconciliation with a fixed oracle, and a multi-step operation with an external effect ledger. Prepare five independent instances per family, three repetitions per product and configuration. Conditions C0 normal, C1 long context with six fixed constraints, C2 a single injected tool failure after dispatch, and C3 interruption followed by native recovery: for the effect task, interrupt after external commit but before acknowledgment; for repository and data tasks, interrupt after the fixture tool sends its response, using the remote response-send boundary. A product-native receive-to-persistence boundary may be tested separately when observable and controllable. Verify the declared boundary with its own event source. Each repository fixture starts from a clean pinned commit and a failing hidden regression test; success requires that test and the existing suite to pass with the protected files unchanged. Each data fixture has a fixed input CSV, a reference aggregate and a required output schema. Each effect fixture contains three ordered operations with unique IDs; success requires one committed effect per ID and matching receipts. Use a 600-second task timeout and freeze per-product model, permissions and token budget before each matched batch.

Steps: run each instance through the native task entry, inject each condition at its verified boundary, and retain artifact, effect ledger, native trajectory, all model usage and elapsed time. Track native-product and shared-model results separately.

Acceptance and metrics: independently test repository changes, compare data results with the oracle, and verify effect count and receipt. Report task-instance success, constraint violations, duplicates, retry and recovery outcomes, full-run time and cost. Link each outcome to H03–H17 evidence and identify the mechanism supported by the trace.

## 6. Execution sequence and readiness

1. Implement M/T/O/A and profile adapters, including Responses streaming and approval-driver integration. Verify the fixture with protocol conformance tests, positive/negative controls, state reset, synthetic-only egress and fault reachability.
2. Run DSH and OpenClaw positive controls and deterministic P01–P05/H03–H18 scenarios on GitHub-hosted runners. Separate calibrations from formal batches; freeze hashes after calibration.
3. Implement and review the Codex adapter against its pinned binary and official public interfaces. Codex execution remains pending until authorized; its unsupported/unobservable conditions are included in the matrix.
4. Freeze matched model/provider and budget for Track C; run real-model cases with approved credentials and record usage. Compare same-track products, then integrate evidence into two six-dimension tables.

**Current status:** the protocol is specified; only session reconstruction has a working DSH/OpenClaw hosted calibration. M's Responses mode, common T, O, A, product adapters, and the remaining CI cases are implementation work. They must pass their controls before any formal cross-product result is published.

## 7. Execution matrix

`campaign.json` specifies the condition factors. Run `python3 comparison/expand_campaign.py --profile full` to enumerate the reference full-matrix identifiers; the command defaults to the focused core plan. The expansion is a plan; each adapter must still confirm its native fault and observation boundaries during calibration. H18 task fixtures and hidden acceptance files are implementation work and must be committed with hashes before the formal batch.

The expanded plan now includes explicit control IDs, required observations and load-gate labels. It remains a product-independent plan; product/profile binding, calibrated adapters and runner preflight must be frozen before any formal scheduling.
