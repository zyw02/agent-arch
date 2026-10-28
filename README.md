# Agent Platform and Harness Architecture Evaluation

Architecture research for **Codex, DeepSeek Harness (DSH), and OpenClaw**, across two complementary layers: how a system hosts agent work, and how its harness manages each execution. Six dimensions—reliability, security, performance, cost, extensibility, and observability—apply to both layers.

## Six dimensions, two architecture layers

The platform layer examines how each system hosts and operates agent work. The harness layer examines how it assembles, controls, and recovers an individual run. Each experiment contributes evidence to one or more dimensions.

| Dimension | Platform question | Harness question | Initial work |
| --- | --- | --- | --- |
| **Reliability** | Which failures stay within a process or deployment boundary, and what state survives? | Are context and actions preserved, recovered, or retried correctly? | P01, P02, H03, H04, H05, H07, H08 |
| **Security** | Where do state and credentials reside, and who can reach them? | Does authorization cover the operation actually dispatched? | P02, H11 |
| **Performance** | What throughput and resource contention result from the deployment? | How does tool scheduling affect time and correctness? | P03, H08 |
| **Resource & cost** | What are the idle and marginal costs of hosting work? | What do context handling and retries consume? | P03, H03, H04, H07 |
| **Extensibility** | How much integration is required to submit and control work through another entry? | Which execution components can be extended without taking over critical responsibilities? | P04; harness component replacement is a future protocol |
| **Observability** | Can operators see failures and their impact across boundaries? | Can they reconstruct approval, tool effects, and recovery? | P01, P04, H05, H11, H17 |

Explore the [experiment protocols](comparison/first-wave-protocol.md) for the planned scenarios, measurements, and acceptance criteria.

[![Architecture research progress](comparison/progress.svg?v=1737fbda3a88)](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/workflows/comparison-calibration.yml?query=branch%3Amain)

<!-- comparison-dashboard:start -->
## Research progress

| Layer / experiment | Dimensions | Codex | DSH | OpenClaw |
| --- | --- | --- | --- | --- |
| Platform · P01 Fault domains | Reliability, Observability | Planned | Planned | Planned |
| Platform · P02 State and deployment | Reliability, Security | Planned | Planned | Planned |
| Platform · P03 Resources and concurrency | Performance, Resource & cost | Planned | Planned | Planned |
| Platform · P04 Access and operations | Extensibility, Observability | Planned | Planned | Planned |
| Harness · H03 Compaction and constraints | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H04 Large tool outputs | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H05 Recovery and side effects | Reliability, Observability | Planned | In progress | In progress |
| Harness · H07 Model failure and retry | Reliability, Resource & cost | Planned | Planned | Planned |
| Harness · H08 Tool scheduling | Performance, Reliability | Planned | Planned | Planned |
| Harness · H11 Approval binding | Security, Observability | Planned | Planned | Planned |
| Harness · H17 Execution trace | Observability | Planned | Planned | Planned |

**Latest session calibration:** success (three independent calibration units). [View calibration evidence](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40624966995).

[OpenClaw architecture study](evaluation/reports/full-20261026-architecture.md) · [Experiment details](comparison/README.md)
<!-- comparison-dashboard:end -->

## Research and evidence

| Start here | Contents |
| --- | --- |
| [Three-product workspace](comparison/README.md) | Scope, dashboard maintenance and evidence rules |
| [First-wave protocols](comparison/first-wave-protocol.md) | Concrete platform and harness scenarios, controls and limits |
| [Execution plan](comparison/plan.md) | Priorities, comparison tracks and evidence reuse |
| [OpenClaw campaign](evaluation/README.md) | Frozen six-dimension design, tooling and execution guides |
| [OpenClaw architecture report](evaluation/reports/full-20261026-architecture.md) | Source-backed results and tradeoffs for the frozen campaign |
| [Chinese scenario observations](evaluation/reports/full-20261026-observations-zh.md) | Experiment-by-experiment facts and limitations |
| [Historical V6](docs/history/v6-methodology.md) | Earlier OpenClaw/Hermes protocol |

The completed OpenClaw campaign used version 2026.10.7, commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. The new DSH target is the preview `0.2.2-alpha.2`.

## Further information

See the [contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md), [license](LICENSE), and [third-party notices](THIRD_PARTY_NOTICES.md). The [workspace guide](comparison/README.md) covers how to maintain progress and reproduce the research.
