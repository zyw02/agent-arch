# Cloud design review controls — 2026-10-28

**Default execution scope:** the [focused two-layer, six-dimension plan](architecture-core.md) defines seven complete studies: three platform and four harness studies. Duration is controlled by scope and pilot-based admission of complete comparison blocks, without a universal task cutoff or campaign kill budget. Long soak and full-factor sweeps are deferred reference work.


Revision `cloud-review-20261028-r1` amends the cross-product design at baseline `b243db1f1b03a5e24d9434716076067427670c46`. These rules take precedence over conflicting first-wave statements. They specify required execution behavior; adapters and hosted formal runs remain implementation work. The expanded matrix is a plan, not evidence of completed experiments.

## 1. Scheduling claims

H08 C1 sends B only after receiving A's result. The scripted provider owns that ordering. Its conclusion is limited to cross-turn result propagation and observed value correctness; it cannot establish that the harness discovers dependencies or schedules a dependency graph. C0/C2/C4 still test harness-chosen dispatch of calls supplied together. A separate dependency-scheduling study is allowed only where a public native dependency contract exists; freeze its dependency representation, dispatch owner, positive/negative controls and expected guarantee before execution. Unsupported native contracts remain capability entries, not failures of the cross-turn experiment.

## 2. Capacity controls before sustained load

P03 C4/C5 rates 0.5, 2 and 10 arrivals/second are candidates. Before any product comparison:

1. Run M/T and the generator without a product at each candidate offered rate and twice the highest intended formal rate. Use 30 seconds warmup plus 120 seconds measurement. Record offered/received/completed requests, errors, response delay overshoot, generator lateness, process CPU/RSS and achieved load. Include both the mixed 250 ms/2 s model workload and the additional 250 ms tool read.
2. Replay the same workload with O disabled and enabled in randomized paired blocks (three fresh pairs). Measure observer CPU, latency and completion impact. O's process exclusion from product counters does not remove host contention. Retain host CPU/memory availability and all M/T/O counters during product runs.
3. Run short product pilots (30 seconds warmup, 120 seconds measurement, one fresh unit per profile/rate) before freezing formal load. Preserve failures and generator saturation. Pilots never enter formal estimates.

Freeze numeric capacity criteria before running pilots: maximum generator delay, maximum fixture p95 response-delay overshoot, maximum observer CPU percent and observed overhead. Controls pass only if achieved arrivals match offered arrivals within the frozen tolerance, error counts and delay meet the frozen thresholds, and fixture/generator capacity exceeds intended formal load. Record the numerical tolerance and all outcomes in the capacity report. Do not select thresholds after examining product rankings.

Select one common sustainable and one common overload level from the candidate set using a predeclared completion/queue-growth criterion. If no common pair exists, redesign the ladder and re-calibrate before freezing. Use the same selection and freeze evidence for every product/profile in the matched comparison. Six formal units per selected level, tool condition and admission mode yield 48 sustained-load units per eligible product/profile: at least 25.6 runner-hours including the two-minute warmup, before setup and draining. Confirm total cost across actual profiles before launching.

`expand_campaign.py --profile full --load-freeze FILE` validates the freeze record and evidence hashes. Without it, C4/C5 rows have `load_gate_satisfied=false`. Unselected candidates remain visible and gated. The freeze JSON requires:

- `selected_arrival_intervals_s`: two distinct strings from `2`, `0.5`, `0.1`;
- `capacity_controls_passed: true`, and `selection_rationale` linking the frozen selection criterion and all product pilots;
- `fixture_capacity` and `observer_overhead`: each an object with `path` (relative to the freeze file) and `sha256` for the retained report;
- positive numeric `max_generator_delay_ms`, `max_fixture_p95_ms`, `max_observer_cpu_percent`, `stop_memory_percent`, `stop_processes`, `stop_generator_delay_ms`. Here `max_fixture_p95_ms` measures response-delay overshoot above the assigned synthetic delay, not the intentional 2-second service time. Percentage limits cannot exceed 100.

Hash validation establishes evidence identity; the runner/reviewer must also verify the reports' measured acceptance and pilot coverage. The flag alone is not proof of calibration. Commit compact synthetic capacity reports and the frozen selection or preserve immutable archive references before formal publication.

During execution, stop new arrivals at frozen host-memory/process/generator thresholds; record a censored overload outcome and drain for at most 180 seconds. Preserve every offered task and distinguish product rejection, queue timeout, execution timeout, generator delay and drain expiry. If fixture latency or observer overhead violates its control threshold, report compromised attribution rather than calling it a product failure. Retain the direct arm without a hidden concurrency cap; adding a cap defines another deployment. The separate external FIFO keeps eight active tasks and at most 1,000 waiting tasks.

## 3. Mandatory coverage and paired controls

The matrix and expander now require `native_outcome` and `independent_oracle` for every unit. Additional coverage is explicit:

| Experiment | Required coverage |
| --- | --- |
| P01 | Healthy companion throughout each fault, matched healthy baseline, companion outcome and collateral impact |
| P02 | Separate conversation/state-consistency variants; instruction retention, completed receipt, pending operation and repetition count |
| H04 | Separate marker and distributed-aggregate task variants at every size/reference/track combination |
| H14 C5–C7 | Separate normal, injected-failure and cancellation integration variants, plus state/policy/usage ownership |

For P02's conversation-only variant, state-consistency fields are explicitly not applicable with a reason; they must never be silently omitted. For state-consistency variants, commit the exact setup and pending-operation boundary and require an independent effect ledger. Each P01 fault unit includes its companion; this is not an additional untracked optional test. H04 scores the oracle relevant to its task kind. Every H14 failure/cancel variant points to its normal integration control as well as the original C0 baseline.

Each row has an explicit `control_unit_id`, matched on case, track, fixture factors, task instance and repeat block. H03 C4 additionally links its opposite long-history arm. H05 controls match idempotency mode. P03 C2–C4 use the one-task C1 reference. Under revision R2, C5 instead uses the admission-matched C6 tool positive control, with C1 retained as a separate performance reference and idle C0 reported separately. Before execution bind both sides to the same pinned product/profile/model/tool/permission configuration and paired host block. A failed control blocks dependent fault execution. The runner must preserve each required observation value or an explicit unsupported/unobservable/not-applicable reason and evidence reference.

All rows remain `plan_only=true`, even after a load freeze passes. Formal readiness additionally requires pinned product/profile/model/budget/permissions, calibrated per-condition adapters, verified fault boundaries and passing matched controls. The expander never starts products and does not certify these future runner requirements.

## 4. Analysis units, repetitions and denominators

Deterministic mechanism calibration uses three fresh units; P03 performance and H08 scripted scheduling timing use six. Real-model conditions use five distinct task instances × three repeats. H08 real-model timing is descriptive within that task design, separate from the controlled six-unit timing study.

Freeze an analysis plan before formal execution, including primary outcome per experiment, paired blocking, sample count, timeouts, exclusion reasons, usage coverage and reporting script hash. Use accepted task completion for H18, constraint retention for H03, oracle correctness for H04, effect/acknowledgment classes for H05, correctness and elapsed time for H08, unauthorized effects for P05/H11, and valid completions/offered tasks plus resource integration for P03. Other metrics are secondary.

For real-model studies aggregate repeats within each task instance first, then report all five instance summaries and paired product/condition differences. Fifteen runs do not constitute fifteen independent tasks. If estimating uncertainty, resample distinct task instances while preserving paired blocks and disclose the limited sample. Publish raw deterministic timings and distributions; avoid p99 or broad product-ranking claims from six units. Do not pool native-model, controlled-model or scripted tracks.

Use separate fields for experiment validity, capability and product outcome:

| Field | Values |
| --- | --- |
| validity | valid, fixture_error, adapter_error, trigger_not_reached |
| capability | supported, unsupported, unobservable, untested |
| outcome | success, failure, safe_indeterminate, null |

A reached no-fault request that fails because of the product is a valid negative observation. Keep it; mark dependent fault units unexecuted with the failed-control reference. Fixture failure or an unreached fault is not a product failure. Outcome is null when validity/capability prevents assessment. Safe uncertainty after an ambiguous commit is separate from successful delivery.

Report valid supported product outcomes with explicit success/failure/indeterminate counts. Also report all planned units by capability/validity and reasons for exclusion; never silently drop a failed positive control. Product timeouts remain failures and censored durations at their declared deadline. Report usage completeness and known amounts; unknown usage is not zero. Fixture token fields do not represent real billing.

## 5. Readiness

First implement and validate the common fixtures and adapters, then run hosted calibration, verify mandatory coverage and capacity evidence, freeze the bound plan and statistical method, and execute formal units. This revision repairs the design and its plan validation; it does not promote previous session calibration to full recovery evidence or mark any product experiment complete.

## 6. Revision R2: tool control and component acceptance

Revision `cloud-review-20261028-r2` adds P03 C6 and mandatory H14 acceptance contracts to the matrix. These rules supersede the earlier C5-to-C1 positive-control link.

### P03 C6: single-task tool positive control

C6 uses one fresh session and one task through the same product adapter, MCP/native shim, tool schema, permission policy and datastore as C5. The scripted model requests exactly one `read` with a unit-specific key, receives the fixture value and then returns `ACK_<task_id>` containing that value. Each of the two model requests has a fixed 250 ms response delay; the read has a fixed 250 ms delay. Use six independent units for each admission mode (`direct`, `external_fifo`), with the FIFO otherwise empty. Record the model call sequence, exactly one T read receipt, call/result IDs, exact value in the final native answer, exit/terminal status and resource samples.

A passing C6 requires one successful read, its matching result and a correct final answer; an ACK without an independent tool receipt fails. A no-fault product error remains a valid failure. A fixture/adapter error has its own validity reason. C5's `control_unit_id` now references C6 with matching admission mode and repeated block. Do not run the dependent C5 unit until that C6 passes. C1 is retained separately as `performance_reference_unit_id`; it is a model-only cost reference, not proof of tool readiness. C6 compares tool increment descriptively with C1. It is a short positive control and does not require the sustained-load freeze; C5 still does.

### H14 C5–C7: normal, failure and cancellation acceptance

Use read-only T operations in these component-extension variants so fault/cancel acceptance does not depend on ambiguous external writes. C0–C4 retain their original tool-lifecycle scenarios. Each integration variant must first pass its matching normal component control. Observe boundaries through M/T or public lifecycle hooks; the fixture may hold or fail only its own component. If a public boundary cannot be controlled or observed, record unsupported/unobservable with a reason; do not replace it with a core patch or classify an unreached intervention as a product failure.

| Component | Normal | Injected failure | Cancellation boundary |
| --- | --- | --- | --- |
| C5 provider | Expected synthetic answer delivered through native output; canonical provider content matches the normal oracle | At M `request_received`, before the first response byte, return HTTP 503 once; subsequent attempts behave normally | Hold the first response before any bytes and invoke native cancellation after M confirms receipt |
| C6 context | Component-controlled history contains KEEP, excludes DROP, and its canonical content hash matches the transformed oracle | Raise one controlled exception after public component entry and before returning transformed history | Hold at the public context-component entry before any transformed history is returned |
| C7 executor | One dispatched read, one matching independent T receipt and the correct final answer | Return one controlled executor error after public dispatch entry and before the read reaches T; subsequent native attempts may proceed normally | Hold at public executor dispatch before the read reaches T |

Failure-handling acceptance (`acceptance_met`) is assessed separately from the product outcome: an explicit native error maps to product `outcome=failure` even when graceful failure handling meets the case contract. Handling is accepted for an explicit native error with preserved operational control, or a verified native recovery/fallback with the correct final answer and ledger evidence. Record the policy, fallback owner, all attempts and usage. Do not require retries or implement them in the adapter. A C6 fallback must preserve KEEP; record whether DROP remains because the failed transform was bypassed. DROP removal is mandatory for the successful normal transform, not for an explicitly identified native fallback. C7 recovery requires a matching read receipt; a reported success without a verified result fails. C5 recovery requires delivery of the expected synthetic answer. No implicit success follows from exit code zero alone.

For cancellation, record the native cancellation request, acknowledgment/effective event, held boundary and actual cessation. Inspect at 0.5, 2 and 10 seconds after cancellation becomes effective. Require native cancelled terminal status and quiescence within 10 seconds: no active task-owned execution or new model/tool dispatch after effective cancellation, and no unapproved workspace effects. Release the held fixture only for cleanup after observation; it must never manufacture a successful answer. No native effective-cancellation observation means cancellation effectiveness is unobservable, not a passing result. If cancellation is never acknowledged/effective within 10 seconds of the request, retain the reached request as a cancellation failure (or fixture/adapter error where independently established); do not wait indefinitely for a timer start. The overall case timeout is 180 seconds.

Allowed residue is limited to native session/error records, the installed extension/configuration, and shared services idle at their measured baseline. Task-owned processes or queued old work surviving the cessation deadline are failures. Snapshot residual processes, queued work, datastore and protected workspace hashes. After the fault/follow-up window, disable the injected intervention and run a separate fresh native health task through the normal component; record its exact answer and read receipt where applicable. This checks that product control remains usable and does not resume the cancelled task.

Exact normal-output comparisons use a predeclared canonical component payload: provider text for C5, component-controlled transformed history for C6, and read result for C7. Exclude only frozen metadata fields such as request IDs/timestamps; never discard answer content or tool arguments. C6 is compared with the transformed oracle, not the unmodified history. Failure/cancel hashes are diagnostic evidence only. They are not required to equal normal-success hashes. Always record the native terminal state, boundary event, complete M/T ledger, residual state and post-case health outcome. `campaign.json` carries these per-condition/state contracts into every expanded H14 row.
