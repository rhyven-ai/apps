# Failure-to-Regression

Keep a failure, a reproducible fixture and its fix evidence together. This is a
purely declarative app: no Python, Docker or executable package code.

## Agent flow

Use category `rhyven/failure-to-regression` with the universal three-tool
interface. Discover schemas through `rhyven_describe(category)`.

1. `action_record_failure`: save title, project, symptom and reproduction.
   Optional `source_app` and `source_record_id` link the originating report.
2. `action_add_regression`: attach a case ID, supplied snapshot and expected
   pass/fail outcome to the failure.
3. Add that fixture to a Workflow Evaluator suite. Run both the original and
   candidate Preflight Checker policies against the same suite.
4. `action_mark_fixed`: supply the failure ID, expected revision, fix summary,
   successful evaluation ID and suite hash.
5. `action_reopen`: reopen a failure if it recurs; old fix references are cleared.

Generic object query/get functions support search and filtering of failures and
regressions. Records have runtime-managed timestamps and revisions. Expected
revision checks prevent silently overwriting another agent's update.

## Boundaries

The app stores state and enforces its local relationships and status transitions.
The caller still performs the fix, executes checks, interprets results and links
cross-app evidence. Evaluation IDs and suite hashes are references, not verified
foreign keys into another app. Marking a failure fixed does not independently
prove that the evaluation passed.

Permissions are only `state.read` and `state.write`. Objects live in the runtime's
collection database. The regression fixture must be supplied text, not a command
to execute. Use synthetic or appropriately redacted examples.

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
