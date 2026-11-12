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

The patch requires `extensions/agentloop/zte-agentloop-sdk-6.26.20-b4.tgz`,
which is absent from the delivered tree. The exact tarball is mandatory before
building; its SHA-512 must equal the supplied pnpm lockfile integrity. Removing
this dependency, stubbing the SDK or excluding the plugin would change the
requested treatment. Input admission stops before any model calls if it is
absent. Once supplied, seal it as `inputs/agentloop-sdk.tgz.enc` and register
its ciphertext SHA-256 in `inputs/source.json` using the same stored key.

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
