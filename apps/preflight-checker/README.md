# Preflight Checker

Run reusable checks on text snapshots supplied by an agent. Save immutable policy
versions and reports so another agent can repeat the same check.

## Checks

| Kind | Behavior |
| --- | --- |
| `exists` | Require a file in the snapshot. |
| `contains` | Require a literal string. |
| `not_contains` | Reject a literal string. A missing file still fails. |
| `json_valid` | Parse strict JSON; reject duplicate keys and non-finite numbers. |
| `json_equals` | Compare a JSON value reached through object keys. |
| `python_syntax` | Parse Python syntax without executing the source. |

All checks operate on supplied `{path, content}` entries, not a live checkout.
The agent chooses which files to read. Paths are normalized relative POSIX paths;
there is no globbing, shell command, regex engine or arbitrary test execution.

## Agent calls

Call `rhyven_describe("rhyven/preflight-checker")` for the current schemas, then
use `rhyven_call(category, function, args)`:

```json
{"category":"rhyven/preflight-checker","function":"action_save_policy","args":{"name":"release","version":"1","checks":[{"id":"config","kind":"json_valid","path":"config.json"}]}}
```

Use the returned `policy_hash` with `action_run` and a `files` snapshot. Retrieve
reports through `action_get_run`, policies through `action_get_policy`, and
recent records through `action_list_runs` / `action_list_policies`.

A report contains the policy hash, input snapshot hash, individual check results,
failed check IDs and elapsed check time. The report does not retain source text.
A policy name/version cannot be overwritten: save version `2` to improve it.
Changing policy data does not change executable app code; code changes require a
new package version and the normal update review.

## Requirements and limits

Python 3.10+ in a Rhyven-managed isolated environment; standard library only.
No Docker, pip packages, network access or project subprocesses are used.
Permissions: `state.read`, `state.write`, `host.execute`. Native execution is
**unsandboxed** under the local user despite this app's limited operations.

Up to 100 checks, 100 files and 400 KB of UTF-8 source per snapshot. JSON equality
supports object keys, not array indexing. Python grammar is that of the host
interpreter. Syntax checks cannot prove correctness or security.
Reports and policies use SQLite in the app's collection data directory.

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
