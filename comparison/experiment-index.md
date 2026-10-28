# Cross-product experiment catalogue

This catalogue is the shared reference for comparing Codex, DeepSeek Harness (DSH), and OpenClaw. Each entry specifies the architectural mechanism, a common scenario, the observations to collect, and the interpretation the comparison supports. The [dashboard](../README.md#research-progress) tracks each product separately.

## Readiness

The [execution protocol](execution-protocol.md) defines the full two-layer, six-dimension campaign: fixtures, product profiles, scenario conditions, controls, measurements, acceptance, and evidence. DSH and OpenClaw have passed three hosted session-reconstruction calibration units. The remaining adapters, fixtures, and CI cases are implementation work; Codex runtime calibration is pending.

## Shared comparison contract

Each run records product version, entry point, deployment, configuration, model and provider, tools, permissions, task and fixture versions, external components, environment, observations, acceptance, and evidence links. Start each independent unit with isolated state. Attribute actions to the component that actually performs them.

Use three complementary tracks: **native product** configurations for operational results; **controlled harness** configurations with a shared model and tools where supported; and **mechanism studies** using each product's native controls. Record differences in prompts, tool schemas, and observation access. Compare outcomes only within a track and retain the raw per-product results. Codex is specified for future execution; no Codex runs are part of the current campaign.

| ID | Layer | Dimensions | Assessment |
| --- | --- | --- | --- |
| [P01](#p01--fault-domains) | Platform | Reliability, observability | Task ownership and failure propagation |
| [P02](#p02--state-and-deployment) | Platform | Reliability, security | State ownership and restart behavior |
| [P03](#p03--resources-and-concurrency) | Platform | Performance, resource & cost | Lifecycle footprint and task contention |
| [P04](#p04--access-and-operations) | Platform | Extensibility, observability | Integration and operational control |
| [P05](execution-protocol.md#p05--security-platform-identity-and-state-boundaries) | Platform | Security | Identity, state and endpoint boundaries |
| [H03](#h03--compaction-and-constraints) | Harness | Reliability, resource & cost | Context retention and compaction cost |
| [H04](#h04--large-tool-outputs) | Harness | Reliability, resource & cost | Output visibility and retrieval |
| [H05](#h05--recovery-and-side-effects) | Harness | Reliability, observability | Session and effect recovery |
| [H07](#h07--model-failure-and-retry) | Harness | Reliability, resource & cost | Retry behavior and its cost |
| [H08](#h08--tool-scheduling) | Harness | Performance, reliability | Concurrency, dependencies, and failures |
| [H11](#h11--approval-binding) | Harness | Security, observability | Approval scope and actual dispatch |
| [H14](execution-protocol.md#h14--extensibility-tool-lifecycle) | Harness | Extensibility, reliability | Tool integration and lifecycle |
| [H17](#h17--execution-trace) | Harness | Observability | Causal reconstruction |
| [H18](execution-protocol.md#h18--end-to-end-task-delivery) | Harness | Reliability, performance, resource & cost | Task delivery under context, faults and interruption |

## Platform experiments

### P01 — Fault domains

**Scenario:** Start a task, hold the model response after the fixture receives it, terminate the client entry point, and observe the connection, process tree, task, and recovery. Run OpenClaw Gateway and embedded modes as separate configurations; exercise the native Codex and DSH entries. Repeat with tool-process termination after a tool adapter is calibrated.

**Measure:** Fault reachability, surviving processes and connections, task outcome, recovery path, and elapsed time. Three independent units per condition.

**Architecture evidence:** Shows whether work is owned by the caller or a separate service, how faults propagate, and which component is responsible for recovery. [Protocol](first-wave-protocol.md#p01--task-ownership-after-an-entry-point-exits).

### P02 — State and deployment

**Scenario:** Map process, session, workspace, credential, and log locations for each selected deployment. Run a two-turn session across a normal process restart; inspect which state the second turn consumes. Record Gateway-backed and embedded OpenClaw separately.

**Measure:** State owner and location, persistence lifecycle, external dependencies, restored user and assistant content, and required restart steps. Three independently initialized session units.

**Architecture evidence:** Connects the deployment topology to state ownership and restart behavior. Credential location informs the security boundary; authorization requires separate testing. [Session protocol](first-wave-protocol.md#p02--h05--reconstruct-a-session-after-normal-exit).

### P03 — Resources and concurrency

**Scenario:** On a matched host, measure a cold start and one task with a fixed synthetic model response. Measure Gateway idle cost and task increment separately; record the full process tree for every product. A subsequent concurrency subscenario will submit multiple independent tasks with fixed service delays.

**Measure:** Startup-to-request time, sampled process-tree RSS, CPU, task completion, residual processes, and external-component cost. Six fresh units for the resource baseline; freeze the concurrency load after calibration.

**Architecture evidence:** Quantifies the cost of a long-lived shared service and per-invocation execution, alongside contention under a common workload. [Baseline protocol](first-wave-protocol.md#p03--execution-footprint-and-lifecycle).

### P04 — Access and operations

**Scenario:** Use each supported native entry or public interface to submit a task, observe progress, cancel it, and continue an existing session. Record the steps and extra components needed to provide an equivalent remote entry.

**Measure:** Supported operations, public interface coverage, configuration and integration changes, dependencies, observed cancellation and resume, and diagnostic access.

**Architecture evidence:** Shows which control and integration responsibilities are built into the deployment and which must be supplied around it. **Calibration needed:** establish each product's entry point and comparable cancellation behavior.

## Harness experiments

### H03 — Compaction and constraints

**Scenario:** Give each product the same multi-turn task containing early and recent constraints, a completed step, and a rule updated from v1 to v2. Compare a short control with a long history that triggers native compaction; inspect model-visible requests wherever accessible. Repeat with the product's manual compaction path when available.

**Measure:** Constraint and updated-rule retention, repeated steps, final acceptance, requests, tokens, and elapsed time. Record the trigger and compaction configuration.

**Architecture evidence:** Relates context maintenance to information retention, task continuity, and cost. **Calibration needed:** establish the trigger, context size, and request visibility for each product.

### H04 — Large tool outputs

**Scenario:** A common tool returns 8, 64, and 256 KiB of synthetic text with unique values at the beginning, middle, and end. Repeat with and without a reference to the complete content. Ask the agent to return all values.

**Measure:** Exact values returned, content reaching the model when visible, truncation notices, full-content retrieval, extra tool calls, and token usage.

**Architecture evidence:** Shows how the harness handles oversized results and whether its retrieval path preserves task-relevant information. **Calibration needed:** connect the same fixture through each native tool surface and verify retrieval access.

### H05 — Recovery and side effects

**Scenario A — session:** Run the two-turn P02 session-reconstruction protocol. **Scenario B — effects:** A controlled external service records a create operation. Interrupt before dispatch, after the service commits but before the response arrives, and after the result is recorded; then use native resume and, separately, explicit user retry. Run service variants with and without an idempotency key.

**Measure:** Retained conversation, missing or duplicate effects, acknowledgment, reported uncertainty, recovery path, and the component that creates or enforces the idempotency key.

**Architecture evidence:** Separates conversation persistence, execution continuation, and external-effect consistency. **Calibration needed:** effect-tool integration and deterministic interruption at each boundary; normal session reconstruction has already been calibrated for DSH and OpenClaw.

### H07 — Model failure and retry

**Scenario:** The local model endpoint returns HTTP 503 once and then a valid fixed response; a positive control returns success immediately. Use the product's native retry configuration and run three independent units.

**Measure:** Request count and intervals, repeated user content, final outcome, duration, and usage where available.

**Architecture evidence:** Reveals retry ownership, attempt limits, and delay. [Protocol](first-wave-protocol.md#h07--model-request-failure-and-retry). **Calibration needed:** Codex Responses error behavior and each product's retry settings.

### H08 — Tool scheduling

**Scenario:** Provide four independent reads, a read dependency chain, conflicting writes to the same record, and one failed call among successful calls. Use a fixed call sequence when a product supports a deterministic model adapter, and a separate real-model task where the model chooses the calls.

**Measure:** Dispatch and completion times, overlap, call/result ID alignment, order of dependent operations, final external state, and handling of partial failures.

**Architecture evidence:** Relates concurrency and ordering decisions to correctness and completion time. **Calibration needed:** common tool access, fixed-call support, and independent event timestamps.

### H11 — Approval binding

**Scenario:** Request approval for a synthetic operation; test a changed argument or target, policy revocation before dispatch, and a resumed session. Where the product provides an extension that changes parameters, test the final dispatched action against the approved scope.

**Measure:** Requested and granted scope, policy effective time, actual dispatched parameters, external effect, and available authorization records.

**Architecture evidence:** Shows how approval and policy decisions bind to execution across entry points and lifecycle changes. **Calibration needed:** map each product's native approval and policy controls to the same operation.

### H17 — Execution trace

**Scenario:** Run a synthetic task with a model request, tool invocation, one injected failure or retry, and an external effect. Provide only native product records to a blinded investigator, then compare the reconstruction with the independent fixture ledger. Add approval and child-task variants when those controls are calibrated.

**Measure:** Recoverable user request, call and result identifiers, authorization source, retry cause, actual effect, missing evidence, and diagnosis time.

**Architecture evidence:** Tests whether the system connects its decisions, operations, and outcomes well enough to investigate a failure. **Calibration needed:** accessible native logs and a reproducible fault that all three products can exercise.

## Detailed execution

The [execution protocol](execution-protocol.md) contains scenario conditions, controls, repetitions, and acceptance for every item above, including P05 and H14.

## Evidence and reporting

The first-wave protocol starts deterministic scenarios with three independent units and the resource baseline with six; freeze additional sample sizes after calibration. Mark adapter errors and unreached faults separately, retain valid product failures, and link each observation to its fixture and configuration. The [evaluation plan](plan.md) defines the six-dimensional assessment and evidence reuse.
