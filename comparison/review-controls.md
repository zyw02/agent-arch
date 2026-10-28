# Cloud design review controls — 2026-10-28

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

`expand_campaign.py --load-freeze FILE` validates the freeze record and evidence hashes. Without it, C4/C5 rows have `load_gate_satisfied=false`. Unselected candidates remain visible and gated. The freeze JSON requires:

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

Each row has an explicit `control_unit_id`, matched on case, track, fixture factors, task instance and repeat block. H03 C4 additionally links its opposite long-history arm. H05 controls match idempotency mode. P03 C2–C5 use the one-task C1 reference, with idle C0 reported separately. Before execution bind both sides to the same pinned product/profile/model/tool/permission configuration and paired host block. A failed control blocks dependent fault execution. The runner must preserve each required observation value or an explicit unsupported/unobservable/not-applicable reason and evidence reference.

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
