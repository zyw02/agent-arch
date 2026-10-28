# Cross-product evaluation

Start with the [focused two-layer, six-dimension plan](architecture-core.md): three platform and seven harness studies. Admit complete comparison blocks using pilot estimates; no universal task cutoff or campaign kill budget. Long soak and full-factor experiments are deferred.


The [Harness measurement and visualization contract](harness-evaluation.md) requires source-backed component maps, controlled interactions, task/resource metrics and evidence-linked figures for all seven harness studies. The same runs measure completion time, detailed token usage, CPU, memory and disk, with task acceptance as the quality guard.

[Source-informed DSH/OpenClaw bindings and reuse audit](source-informed-comparison.md) records the pinned code review, existing capability findings, accepted historical observations and concrete gaps before new executions.

This workspace compares Codex, DeepSeek Harness (DSH), and OpenClaw at the platform and harness layers. The [experiment catalogue](experiment-index.md) brings together all scenarios, measurements, and readiness; the [execution protocol](execution-protocol.md) specifies the full two-layer, six-dimension campaign; the [execution plan](plan.md) describes scope and priorities; [first-wave protocols](first-wave-protocol.md) define concrete interventions, observations, and limits. The [progress ledger](progress.json) records per-product work items. The [frozen OpenClaw campaign](../evaluation/README.md) and [V6 archive](../v6/) preserve their original evidence.

## Progress maintenance

Update each cell's status, evidence paths, and notes in `progress.json`, then run `python3 comparison/dashboard.py` and commit the ledger and generated README. `python3 comparison/dashboard.py --check` detects drift. GitHub Actions shows live job steps. When session calibration finishes, its aggregation job writes the latest run link and outcome to the active branch and regenerates the README. Other experiment states are maintained by their owners.

Statuses are `planned`, `in_progress`, `blocked`, `done`, and `not_applicable`. The last two require an evidence file in the repository. Record the protocol and supporting evidence for each completed item, including any failed acceptance conditions.

## Design revision

Revision `cloud-review-20261028-r1` addresses the cloud design review through [review controls](review-controls.md): bounded scheduling claims, capacity baselines, explicit extension coverage, matched controls, analysis rules and separate failure classifications. Product experiments remain pending.

Revision `cloud-review-20261028-r2` adds the admission-matched P03 C6 tool control and explicit H14 C5–C7 normal/failure/cancel acceptance contracts; see [R2 details](review-controls.md#6-revision-r2-tool-control-and-component-acceptance).
