# Patched OpenClaw 2026.5.7 as a sixth product

The original 2026-11-11 campaign used **OpenClaw 2026.11.3**, not the local
analysis/Gateway checkout at 2026.11.1. Its run 42959922129 and retained results
remain unchanged.

`protocol-six.json` adds `openclaw57_patched` to the five frozen products. The
task, hidden tests, problem prompt, provider controls, tariff, 3 repetitions,
600-second limit, fresh writable paths, 2 CPUs, 4 GiB and collection/scoring
boundaries are preserved. It uses the native local agent/coding profile, with
the older version's `security=full, ask=off` equivalent to the current version's
`exec.mode=full`; it does not replace the native agent with a custom solver or
force an additional AgentLoop harness selection.

The provided binary patch transforms baseline commit
`eeef4864494f859838fec1586bedbab1f8fa5702` (tree
`1b7a4b7a7341497f3c5b441ece5d3b93111630a0`) into tree
`25cca8d4848324eaa24e8bf36430b58bcc38feca`. Preparation verifies both trees,
the decrypted delivery hash and the patch hash. The public repository holds
only an encrypted copy of the supplied patch; `OPENCLAW57_PATCH_KEY` is an
Actions secret. The same key seals detailed source build logs.

The SDK was subsequently restored from the user's `agentloop-patch.zip`.
Its SHA-256 matches the delivery (`69cbb01a221b6924a70de8d0aa864a4d8f57fb55cb8c81ff710de8dfaac2eafd`),
but its SHA-512 and dependency declarations differ from the original pnpm lock
despite having the same package name/version. Both fingerprints are preserved
in `inputs/source.json`. The user explicitly authorized using this delivery and
updating only the sixth product's dependency lock. Actions run 43144097151
resolved the local SDK using pnpm 10.33.2; the effective lock is sealed as
`inputs/pnpm-lock.yaml.enc` and its plaintext hash is pinned in the manifest.
Preparation first verifies the unchanged supplied source tree, then adds the
SDK and overlays this separately recorded lock. Installation uses
`--frozen-lockfile`. Shared peer contexts may be re-resolved inside this
sixth-product pnpm workspace; the five historical products' separate npm lock
and Hermes environment remain unchanged. The `enhanced-reproduce` mode restores
the supplied SDK without changing the original lock, attempts the frozen build
to retain the real installer outcome, and never admits model calls. It does
not waive SDK/lock validation for calibration or formal solving. The SDK is
sealed as `inputs/agentloop-sdk.tgz.enc`, using the same Actions secret.

The historical Docker image was runner-local with no registry digest and was
not retained. A new six-product common image is built from the original base
image digests, npm lock, task dependencies and Hermes commit. An exact match
to yesterday's complete image or hosted machine is not asserted. The new
campaign reruns all six products three times on the same hosted worker/image;
historical measurements stay separate because date, provider cache, host and
image differ. Installation and compilation remain outside solving time.

The existing `deepseek-preflight.yml` workflow accepts `enhanced-calibration`
and `enhanced-formal`. Formal mode admits solving only after hidden base/gold
controls and all six native tool/usage calibrations pass. Every run retains
the same provider evidence, resource/storage samples, native state, patches
and independent grades as before. Do not count missing dependencies as a
failed SWE-bench solution or publish a sixth score before it actually runs.

## Independent observed batch

`deepseek-preflight.yml` now also accepts `mode=enhanced-observed` and
`product=openclaw57_patched` (the default). This is a separate diagnostic batch
alongside run 43144468826. It does not cancel or change that execution.

The job builds the same pinned runtime recipe and runs hidden-test controls,
one tool/usage calibration, and three formal repeats in separate Actions steps.
Every segment is audited and uploaded immediately, including on failure. Each
artifact contains the original request/response streams, native state and tool
traces, measurements, candidate patch, and independent hidden grading. The
combined artifact preserves segment environment records and all outcomes.
Live API status is available at each step boundary; raw traces become available
after each segment, rather than waiting for the entire campaign to finish.

Only scheduling and upload boundaries differ: task, prompt, SDK, dependency
locks, provider parameters, native executor, resource limits, and grader are
reused. The image is freshly built, so equality of its ID to the running
six-product campaign is not assumed. These isolated repeats are not rotated
six-product comparison blocks and must not be pooled into that campaign.

The observed mode accepts `observed_task_timeout_seconds=600` (default) or
`1800` (the user-requested threefold extension). Only the selected product's
formal solve limit changes; calibration, grading, resources, provider settings,
source, and dependency locks stay fixed. Each formal Actions step has a
40-minute outer limit and the observed job has a 150-minute outer limit.
Admission checks require the accepted controls and calibration to use the same
image and effective protocol, including the chosen timeout. A cancelled hosted
execution is restarted as a fresh three-repeat batch; prior segment evidence
remains separate and is not pooled with the changed-timeout experiment.
