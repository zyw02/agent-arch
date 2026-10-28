# Contributing

Submit ongoing OpenClaw evaluation and maintenance to `main`. Current work uses exactly six dimensions: reliability, security, performance, resource usage/cost, extensibility, and observability. Hermes is outside the current test scope. The `archive/v6` branch is a frozen historical snapshot at commit `a33644efc9490ff771d058ebf047f08550e4ccb3`; do not push changes or target pull requests to it.

Use English for repository documentation, issue descriptions, and pull request descriptions. Preserve multilingual inputs and upstream quotations where they are part of the experiment.

Before submitting a change:

1. Run `python3 tools/check_repository.py` from the repository root.
2. Run `python3 evaluation/tools/check_design.py`, `python3 -m unittest discover -s evaluation/tests -v`, and `python3 -m unittest discover -s comparison/tests -v`.
3. If the matrix changes, regenerate the catalogue with `python3 evaluation/tools/suite.py catalogue > evaluation/experiment-catalogue.md` before running the design check.
4. Explain the problem, the changed behavior or documentation, and the validation performed. A selected plan or passing fixture test is not a completed OpenClaw experiment.
5. Keep runtime installations, logs, databases, generated results, and credentials out of the commit.

Do not reformat vendored sources, rewrite frozen protocol fields, or translate task prompts as documentation cleanup. Behavioral changes require a separately identified experiment revision and evidence; V6 remains the historical reference.

If an intentional archive packaging change modifies a file under `v6/`, update its inventory with `python3 tools/update_manifest.py`, review the manifest diff, and run the checks again. This updates recorded hashes; it does not validate changed experiment behavior. Keep the source index and Windows bundle manifest consistent with any affected file.

Use the existing upstream licenses for third-party files. Changes to the licensing of the original evaluation materials require an explicit decision by their rights holders.
