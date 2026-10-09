---
name: build-rhyven-composition
description: Create, discover, test and reuse portable code bricks, mortar, stacks and pallets, or build a complete Rhyven app from them. Use for repeatable code and app composition on Rhyven 0.7.0 or later.
---

# Reusable code and complete apps

Apps are complete applications. A pallet is a source library, not an app package.
A brick is an ordinary function; mortar adapts values; a portable stack composes
functions. Keep their core code independent of Rhyven. Frames are project templates.

## Reuse before regeneration

For a repeated deterministic operation, search saved libraries once with
marketplace action_match_plan and backends=["source"]. Source discovery grants no execution permission. The consuming app or harness
selects the execution backend and approves its scope.
Inspect selected contracts with action_inspect_candidate. Keep task/revision
stable; reuse descriptions. There is one retry and eight distinct inspections.
When a suitable block exists, import/call it rather than regenerate its source.
Build a missing piece or ask a focused question when searching stops being useful.

action_pallet_list lists saved source libraries. action_pallet_describe accepts
selector=publisher/library@version and optional export. It returns an index or
one contract without source. Use contract_hash/if_hash to avoid reloading unchanged
descriptions. Read implementation when needed for review or debugging, not on
every repeated invocation.

## Create and retain a pallet

Use pallet init NAME --dir DIR --language python or javascript when a template
helps. The format is rhyven.pallet/1, with name, version, description, language,
files, exports, tests and optional dependencies/license.

Each export names kind (brick, mortar or stack), description, file, symbol, input
and output JSON schemas. Python functions accept one JSON value and return one;
JavaScript ES module functions may also return promises. Compose source functions
with normal language calls. Do not turn each function into an installed app.

Validate with pallet validate DIR. Test examples use export, args and expect.
pallet test DIR --allow-host executes unsandboxed source; use it only within
authorized code-execution scope after reviewing source. It does not install
dependencies. With declared dependencies, supply an explicitly prepared
--interpreter path. Do not modify a shared venv to satisfy conflicting libraries.

pallet save DIR stores an immutable version in the bound workspace, or the
selected collection when no project is bound. Use --scope global to share it.
It does not execute code, grant permissions, install an app or publish.
Change version when changing source/contracts/tests.

## Use code independently or in an app

pallet export NAME@VERSION --dir NEW_DIRECTORY writes ordinary source,
manifest/lock and a standalone Python/JavaScript launcher. Import the modules
normally in the project. They do not require Rhyven. Other languages can export
source and use their usual compilers/bindings; automatic run/test currently
supports Python 3.10+ and Node 20+.

For a reviewed simple task, pallet run NAME@VERSION EXPORT --args JSON --allow-host
executes the saved implementation without rewriting code or installing an app.
This is unsandboxed host execution, not an MCP installation-approval bypass.
Direct imports/standalone launchers do not automatically enforce the metadata's
JSON schema; validate inputs in the library when independent callers need it.

For a complete script app, write application-level capabilities, persistence and
tests, then app bundle APP_DIRECTORY --pallet ALIAS=NAME@VERSION --out APP.json.
The app imports vendor.ALIAS.module in Python or the equivalent ES module path.
Source and pinned provenance ship inside the app; recipients need no separate
pallet installation. Bundling does not merge dependency locks or install packages.
Follow the normal reviewed app installation flow.

## Engine workflows and frames

app compose still builds engine-managed workflows calling installed apps through
pinned dependencies. These are distinct from portable source stacks and require
Rhyven. Preserve conditions, bounded iteration, permission unions and request IDs.
Failed workflows may have earlier side effects; inspect their reports and app
state before retrying.

Frames use rhyven.frame/1, name/version, files, pallets (exact library@version
selectors) and optional apps (app IDs). app frame FILE --dir DIR previews;
--apply writes a new directory. Neither reference list authorizes installation.

Keep generated code and libraries local. Publication is only user-initiated.
Public marketplace submissions require public source and an open-source license;
private local libraries/apps do not.

## Library scope and marketplace

Use `--project /absolute/project` to bind a workspace library independently of
app collections. Save project helpers with `pallet save PATH --scope workspace`;
use `--scope global` or `pallet promote workspace::NAME@VERSION` only when sharing
across the user's agents is intended. Discovery searches both and labels scope.
Resolve conflicting contents explicitly with `workspace::` or `global::` selectors.
Marketplace libraries use `action_pallet_search`, `action_prepare_pallet` and
`action_apply`; obtain user approval before download. Saving or downloading source
grants no execution permission. Publish only when the user explicitly requests it.

Use `operation:"workflow"` for engine-managed app workflows. `stack` remains a
legacy alias; portable stacks are ordinary composed source functions.
`pallet test` records local evidence at the exact package hash; saving alone does
not run tests. Inspect `tests.status` and per-export coverage before reuse. Passing
declared examples is a ranking signal, not certification or a security guarantee.
