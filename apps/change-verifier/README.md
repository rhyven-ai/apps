# Change Verifier

Run the same Python regression test before and after a change. Also run the
candidate's existing test suite. Keep structured outcomes and logs for another
agent to inspect. This app does not edit the original repository.

The connected agent supplies approved UTF-8 source snapshots, with `{path,
content}` entries for `baseline`, `candidate` and separate `regression` test
files. Commit IDs are optional labels; content hashes identify the actual input.
No arbitrary host paths, symlinks, submodules or dependency downloads are used.

- `action_prepare`: save snapshots and return a run ID.
- `action_run`: start one background comparison.
- `action_get`: inspect status and the report. Poll with new request IDs.
- `action_cancel`: cancel pending work or request cancellation of running tests.

This is a supervised container service so cancellation and status remain
available during tests. It starts on demand through the Rhyven daemon. On restart,
unfinished work becomes `interrupted`; explicitly run it again to retry. Only one
comparison runs at a time. Each stage has a 1–30 second timeout. Up to 100
comparisons are stored per collection. Backups include its SQLite reports.

The image includes Python and pytest 9.0.3. It runs a fixed pytest command with
plugin autoload disabled and no project config file. It does not accept shell
commands. Projects needing other dependencies require a separately reviewed
image. Supply existing tests in the candidate; an empty suite is inconclusive.

`supplied_case_verified` requires an assertion failure on the baseline, a pass
on the candidate and a passing candidate suite. Setup errors, missing dependencies,
collection errors, cancellation and timeouts do not establish a fix. A candidate
that fails its existing suite is reported separately.

Tests are arbitrary code. Run only approved source in the container, with the
runtime's filesystem, resource and network restrictions. Supplied tests can
forge reports; hashes and results are evidence, not security attestations.
No host secrets or Docker socket are exposed. Outputs and logs are bounded.

Link the run ID and result in Work Management, Failure-to-Regression or Project
Knowledge. The calling agent remains responsible for interpreting the result.

```sh
python3 -m unittest discover -s apps/change-verifier/tests -v
# The test environment must have pytest==9.0.3 installed.
docker build -t change-verifier ./apps/change-verifier
# Package with the immutable image digest returned by your registry:
rhyven app package apps/change-verifier --image ghcr.io/OWNER/change-verifier@sha256:DIGEST --out change-verifier.rhyven.json
```
