# Agent Platform and Harness Architecture Evaluation

**Default research plan:** [two layers, six dimensions, six focused studies](comparison/architecture-core.md). Each layer has three studies that explain architecture mechanisms and tradeoffs. Complete comparison groups are scheduled using pilot estimates; no universal task cutoff or campaign kill budget. Adapters and runtime execution remain implementation work; the full catalogue is reference-only.


Architecture research for **Codex, DeepSeek Harness (DSH), and OpenClaw**, across two complementary layers: how a system hosts agent work, and how its harness manages each execution. Six dimensions—reliability, security, performance, cost, extensibility, and observability—apply to both layers.

## Six dimensions, two architecture layers

The platform layer examines how each system hosts and operates agent work. The harness layer examines how it assembles, controls, and recovers an individual run. Each experiment contributes evidence to one or more dimensions.

| Dimension | Platform evaluation | Harness evaluation | Initial work |
| --- | --- | --- | --- |
| **Reliability** | Task ownership and fault propagation | Context and constraint retention | PA, HA |
| **Security** | Identity across external control entry points | Tool authorization and dispatch binding | PB, HB |
| **Performance** | Startup, lifecycle and shared-resource contention | Tool scheduling and failure-path latency | PC, HC |
| **Resource & cost** | Fixed and marginal lifecycle cost | Total compaction and model-input cost | PC, HA |
| **Extensibility** | Public control integration | Public tool integration and responsibility boundaries | PB, HB |
| **Observability** | Ownership and interruption reconstruction | Scheduling/failure/retry reconstruction | PA, HC |

Explore the [experiment catalogue](comparison/experiment-index.md) and [execution protocol](comparison/execution-protocol.md) for scenarios, measurements, acceptance, and readiness.

[![Architecture research progress](https://raw.githubusercontent.com/zyw02/agent-arch/main/comparison/progress.svg?v=ef4c19e9fa90)](https://github.com/zyw02/agent-arch/actions/workflows/comparison-calibration.yml?query=branch%3Amain)

<!-- comparison-dashboard:start -->
<details>
<summary>Full catalogue progress (reference)</summary>

## Research progress

| Layer / experiment | Dimensions | Codex | DSH | OpenClaw |
| --- | --- | --- | --- | --- |
| Platform · P01 Fault domains | Reliability, Observability | Planned | Planned | Planned |
| Platform · P02 State and deployment | Reliability, Security | Planned | Planned | Planned |
| Platform · P03 Resources and concurrency | Performance, Resource & cost | Planned | Planned | Planned |
| Platform · P04 Access and operations | Extensibility, Observability | Planned | Planned | Planned |
| Platform · P05 Identity and access boundaries | Security | Planned | Planned | Planned |
| Harness · H03 Compaction and constraints | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H04 Large tool outputs | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H05 Recovery and side effects | Reliability, Observability | Planned | In progress | In progress |
| Harness · H07 Model failure and retry | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H08 Tool scheduling | Performance, Reliability | Planned | Planned | Planned |
| Harness · H11 Approval binding | Security, Observability | Planned | Planned | Planned |
| Harness · H14 Tool lifecycle and integration | Extensibility, Reliability | Planned | Planned | Planned |
| Harness · H17 Execution trace | Observability | Planned | Planned | Planned |
| Harness · H18 End-to-end task delivery | Reliability, Performance, Resource & cost | Planned | Planned | Planned |

**Latest session calibration:** success (three independent calibration units). [View calibration evidence](https://github.com/zyw02/agent-arch/actions/runs/40623428889).

[OpenClaw architecture study](evaluation/reports/full-20261026-architecture.md) · [Experiment details](comparison/README.md)

</details>
<!-- comparison-dashboard:end -->

## Research and evidence

| Start here | Contents |
| --- | --- |
| [Three-product workspace](comparison/README.md) | Scope, dashboard maintenance and evidence rules |
| [Experiment catalogue](comparison/experiment-index.md) | Shared scenarios, measurements, architecture evidence and readiness |
| [Execution protocol](comparison/execution-protocol.md) | Two-layer, six-dimension scenarios and acceptance |
| [First-wave protocols](comparison/first-wave-protocol.md) | Initial execution controls and acceptance criteria |
| [Execution plan](comparison/plan.md) | Priorities, comparison tracks and evidence reuse |
| [OpenClaw campaign](evaluation/README.md) | Frozen six-dimension design, tooling and execution guides |
| [OpenClaw architecture report](evaluation/reports/full-20261026-architecture.md) | Source-backed results and tradeoffs for the frozen campaign |
| [Chinese scenario observations](evaluation/reports/full-20261026-observations-zh.md) | Experiment-by-experiment facts and limitations |
| [Historical V6](docs/history/v6-methodology.md) | Earlier OpenClaw/Hermes protocol |

The completed OpenClaw campaign used version 2026.10.7, commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. The new DSH target is the preview `0.2.2-alpha.2`.

## Further information

See the [contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md), [license](LICENSE), and [third-party notices](THIRD_PARTY_NOTICES.md). The [workspace guide](comparison/README.md) covers how to maintain progress and reproduce the research.
