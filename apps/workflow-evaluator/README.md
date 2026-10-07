# Workflow Evaluator

Compare two check policies against the same saved fixtures. Record outcomes and
identify both improved cases and regressions.

## Flow

1. `action_save_suite`: save a name, version and cases. Each case has an ID,
   `{path, content}` files and an `expected_pass` boolean.
2. Run every fixture through Preflight Checker with the baseline policy.
3. `action_evaluate`: submit the `suite_hash` and one `{case_id, report}` for
   every case. Repeat with the candidate policy.
4. `action_compare`: supply `baseline_id` and `candidate_id` from those results.

Use category `rhyven/workflow-evaluator` through `rhyven_call`. The app rejects
missing, duplicate or changed inputs, mixed policies, and comparisons across
different suites. It reports `improved_without_regressions` only when at least
one case improves and none regress. A higher total alone is insufficient.

Suite versions are immutable. Add a case in a new version and rerun **both**
policies. `action_get_suite`, `action_get_evaluation`, `action_list_suites` and
`action_list_evaluations` let another agent retrieve the saved work. Lists omit
fixture contents; get a suite explicitly when its source is needed.

## Evidence and limits

The calling agent runs the checks and supplies the reports. This app scores and
validates their shape, input hashes and policy consistency; it does not execute
other apps, invoke a model or authenticate reports as signed attestations.
Accuracy means agreement with the supplied expected outcomes, not a claim about
unseen projects or general agent intelligence.

Timing is reported check time only, excluding process startup, model and
transport time. A single run is not a speed benchmark.

Python 3.10+, standard library only, no Docker or pip dependencies. Permissions:
`state.read`, `state.write`, `host.execute`. Native execution is **unsandboxed**.
Up to 30 cases, 100 files and 400 KB per snapshot; the whole suite is limited to
600 KB of canonical UTF-8 JSON. SQLite retains suites and evaluations in the
app's collection data directory.

## Installation and state

Requires Rhyven 0.5.5 or later. Discover the package in the marketplace, review
its permissions and approve installation. Agents use `action_prepare_install`
and wait for human approval before `action_apply`; they must not approve their
own installation requests.

App state belongs to the selected collection. Agents connected to the same
collection can retrieve it; a different collection has separate state. Normal
removal retains state unless explicitly purged. Use Rhyven collection backups
for recovery. Fixture text is stored locally: do not submit credentials or
private data that should not be retained.

Source is Apache-2.0. No runtime changes or app-specific MCP server are needed.
