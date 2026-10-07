# Improve a check, keep the evidence

Three installable apps cooperate through Rhyven's existing three-tool MCP:

1. **Preflight Checker** accepts a malformed config because its first policy
   only checks that files exist.
2. **Failure-to-Regression** records the missed failure and a reproducible fixture.
3. **Workflow Evaluator** compares policy versions on the same three cases.
4. The agent adds a JSON-validity check in policy version 2: agreement with the
   expected results goes from 2/3 to 3/3 with no regressed cases.
5. A second MCP connection retrieves the saved policy, evaluation and fix record,
   then reruns the improved check.

The fixtures also include a healthy project and a missing README. Merely rejecting
everything would fail the healthy case. Removing the README check would regress
another case; the unit tests exercise that counterexample.

This is a prepared example using real MCP calls. The recorder drives a fixed
sequence; it is not an autonomous-model benchmark. The improvement is reusable
policy data, not executable-code modification or a change to model weights.
The evaluator scores caller-supplied reports, not signed attestations.

## Reproduce

Requires Rhyven 0.5.5 and Python 3.10+. No Docker or third-party Python packages.
From the apps repository root, build and test the packages:

```sh
mkdir -p /tmp/quality-packages
for app in preflight-checker failure-to-regression workflow-evaluator; do
  rhyven app package "apps/$app" --out "/tmp/quality-packages/$app-0.1.0.rhyven.json"
  rhyven app test "/tmp/quality-packages/$app-0.1.0.rhyven.json" --allow-host
done
python3 demos/quality-toolkit/run_demo.py \
  --binary "$(command -v rhyven)" --home /tmp/quality-demo-home \
  --evidence /tmp/quality-demo-evidence --prepare --packages /tmp/quality-packages
```

A human runs the printed approval commands and reviews each prompt. The native
apps request unsandboxed `host.execute` as well as state read/write; the failure
tracker requests only state read/write. Preparation publishes only to this
isolated local catalog. It does not publish to GitHub.

After approval, run:

```sh
python3 demos/quality-toolkit/run_demo.py \
  --binary "$(command -v rhyven)" --home /tmp/quality-demo-home \
  --evidence /tmp/quality-demo-evidence
```

The driver fails on unexpected results and writes request/response JSONL and
individual result files. Use a fresh home/evidence directory for another run.
Installation requests expire after 15 minutes; prepare new requests if needed.

Agents sharing the same collection can reuse policies and evidence. Keep project
state private, or package a reusable capability under your own namespace and
submit its open-source app package to the marketplace. Ordinary app state is not
published when its source package is published.
