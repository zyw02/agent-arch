# Cross-product evaluation

Start with the [focused two-layer, six-dimension plan](architecture-core.md): three platform and seven harness studies. Admit complete comparison blocks using pilot estimates; no universal task cutoff or campaign kill budget. Long soak and full-factor experiments are deferred.


The [Harness measurement and visualization contract](harness-evaluation.md) requires source-backed component maps, controlled interactions, task/resource metrics and evidence-linked figures for all seven harness studies. The same runs measure completion time, detailed token usage, CPU, memory and disk, with task acceptance as the quality guard.

[Source-informed DSH/OpenClaw bindings and reuse audit](source-informed-comparison.md) records the pinned code review, existing capability findings, accepted historical observations and concrete gaps before new executions.

This workspace compares Codex, DeepSeek Harness (DSH), and OpenClaw at the platform and harness layers. The [experiment catalogue](experiment-index.md) brings together all scenarios, measurements, and readiness; the [execution protocol](execution-protocol.md) specifies the full two-layer, six-dimension campaign; the [execution plan](plan.md) describes scope and priorities; [first-wave protocols](first-wave-protocol.md) define concrete interventions, observations, and limits. The [progress ledger](progress.json) records per-product work items. The [frozen OpenClaw campaign](../evaluation/README.md) and [V6 archive](../v6/) preserve their original evidence.

## Reproduce the current source-informed slice

The pinned source manifests and protocols are committed before hosted native execution. `comparison-context-skill.yml` first runs all ten synthetic native controls. Dispatch with `live_model=false` for calibration only; `live_model=true` admits two complete real-model blocks only after that run's calibration passes. The workflow uses the configured DeepSeek Actions secret through the observation relay; products receive synthetic credentials. Current protocol is CTX-02; CTX-01 retains its input/scorer defects and all original outcomes under its own evidence directory.

`comparison-reuse-plots.yml` recomputes accepted COST-03 guide accounting and extracts all accepted OBS-02 event partitions from hash-verified permanent archives. It executes no native product and makes no model calls. CSV, JSON and PNG/SVG outputs preserve product version, original states, independent units and missing fields. Native execution and original-archive inspection run only on disposable hosted workers; compact evidence may be analyzed locally.

The completed bounded PA/PC formal studies use `comparison-platform-fault.yml` and `comparison-platform-resource.yml`, with complete pilot/admission evidence retained separately from formal blocks. Their native-only review workflows retain actual isolated model requests and original scores. The PC question set is secondary analysis, frozen after execution started and before formal outcomes were inspected. The [results report](source-informed-comparison.md#native-only-reconstruction-original-answers-support-and-uncertainty) distinguishes matching answer values from supported evidence and preserves all unknowns/errors.

For offline verification, `export_native_review.py` takes the retained original review ZIP, its SHA-256 from `native-review/provenance.json`, the corresponding compressed formal report, frozen review protocol and `--study PA` or `--study PC`. It recomputes source truth and original scoring and verifies actual native-only inputs; it makes no provider requests. `plot_platform_resource.py` reads the PC formal report and `plot_native_review.py` reads the two informed-audit files to reproduce PNG/SVG figures with Matplotlib 3.10.8. Every figure's original inputs and plotting-script hashes are bound in the adjacent provenance record. Comparison tests exercise the retained evidence and reject altered archives, protocols and native projections.

## Progress maintenance

Update each cell's status, evidence paths, and notes in `progress.json`, then run `python3 comparison/dashboard.py` and commit the ledger and generated README. `python3 comparison/dashboard.py --check` detects drift. GitHub Actions shows live job steps. When session calibration finishes, its aggregation job writes the latest run link and outcome to the active branch and regenerates the README. Other experiment states are maintained by their owners.

Statuses are `planned`, `in_progress`, `blocked`, `done`, and `not_applicable`. The last two require an evidence file in the repository. Record the protocol and supporting evidence for each completed item, including any failed acceptance conditions.

## Design revision

Revision `cloud-review-20261028-r1` addresses the cloud design review through [review controls](review-controls.md): bounded scheduling claims, capacity baselines, explicit extension coverage, matched controls, analysis rules and separate failure classifications. Execution readiness is tracked by study and evidence; the retained native read pilot, context/skill study, historical re-extractions and bounded PA/PC formal results are documented in the source-informed report. They do not complete the ten-study plan.

Revision `cloud-review-20261028-r2` adds the admission-matched P03 C6 tool control and explicit H14 C5–C7 normal/failure/cancel acceptance contracts; see [R2 details](review-controls.md#6-revision-r2-tool-control-and-component-acceptance).
