# Agent Platform and Harness Architecture Evaluation

Architecture research for **Codex, DeepSeek Harness (DSH), and OpenClaw**, across two complementary layers: how a system hosts agent work, and how its harness manages each execution. Six dimensions—reliability, security, performance, cost, extensibility, and observability—apply to both layers.

## Six dimensions, two architecture layers

The platform layer examines how each system hosts and operates agent work. The harness layer examines how it assembles, controls, and recovers an individual run. Each experiment contributes evidence to one or more dimensions.

| Dimension | Platform evaluation | Harness evaluation | Initial work |
| --- | --- | --- | --- |
| **Reliability** | Failure isolation, state persistence, and deployment recovery | Context retention, execution recovery, and retry behavior | P01, P02, H03, H04, H05, H07, H08, H18 |
| **Security** | State and credential ownership, access boundaries, and isolation | Authorization scope and consistency between approval and execution | P02, P05, H11 |
| **Performance** | Throughput, concurrency, and resource contention | Tool scheduling, execution latency, and dependency handling | P03, H08, H18 |
| **Resource & cost** | Idle footprint and marginal cost per task | Context processing, retry overhead, and model usage | P03, H03, H04, H07, H18 |
| **Extensibility** | Entry-point integration and operational control | Component extension and responsibility boundaries | P04, H14 |
| **Observability** | Fault visibility and diagnosis across system boundaries | Reconstruction of approvals, tool effects, and recovery | P01, P04, H05, H11, H17 |

Explore the [experiment catalogue](comparison/experiment-index.md) and [execution protocol](comparison/execution-protocol.md) for scenarios, measurements, acceptance, and readiness.

[![Architecture research progress](https://raw.githubusercontent.com/zyw02/agent-arch/main/comparison/progress.svg?v=ef4c19e9fa90)](https://github.com/zyw02/agent-arch/actions/workflows/comparison-calibration.yml?query=branch%3Amain)

<!-- comparison-dashboard:start -->
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
