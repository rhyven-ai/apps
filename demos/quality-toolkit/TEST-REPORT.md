# Quality toolkit acceptance — 2026-10-07

Tested using the released Rhyven 0.5.5 Linux x86-64 binary, Python 3.10,
and the three packaged v0.1.0 apps. No runtime source changes.

- Preflight Checker: 3 packaged contract cases passed.
- Failure-to-Regression: 4 packaged contract cases passed.
- Workflow Evaluator: 6 packaged contract cases passed.
- Eight subprocess unit tests passed: all check kinds, input validation,
  immutable policy/suite versions, mismatched comparisons, regression detection,
  persisted state, collection isolation and non-execution of supplied Python.
- Real MCP workflow: the baseline agreed with 2/3 expected results; the candidate
  agreed with 3/3 on the same suite, with zero regressed cases.
- A second MCP connection/actor read the saved evaluation, policy and fixed
  failure record, then rejected the malformed config using the improved policy.
- A stale revision update was rejected by the declarative runtime.

Installation initially returned `approval_required`. The operator explicitly
approved the reviewed packages in chat and instructed installation; the CLI's
`--accept-permissions` option installed those exact package bytes into the
isolated `quality-demo` collection. No automated or fabricated human approval
was supplied to MCP. This was not a test of host form elicitation.

Host requirements inspection warned that Python `ensurepip` was missing. These
apps declare no pip dependencies; their isolated environments and actual calls
succeeded. The warning is retained in the private preparation evidence rather
than misrepresented as a clean host diagnosis.

[evidence/events.jsonl](evidence/events.jsonl) records the actual MCP requests
and responses used for the demo. Its fixed sequence is driven by the recorder;
it is not evidence of an autonomous model solving an unseen task. Timings are
not a speed benchmark. Cross-app references and submitted reports are not signed
attestations. The video is a shortened, captioned replay of these results.
