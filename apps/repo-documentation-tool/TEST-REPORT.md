# Rhyven Repo Documentation Tool acceptance results

## Native script candidate — September 28, 2026

Tested on Linux x86-64 / WSL2 with Python 3.10.12 and Node 22.23.2 using the
`feature/script-runtime` source build. This native variant is not published.
It uses the same app action schemas and three-tool MCP interface as the container.

Passed:

- Native packaging, explicit host-execution consent, installation and discovery.
- Real Pyright scanning: all four fixture symbols, expected line numbers,
  100-reference cap with truncation flagged, and live relationship refresh.
- Calling-agent fixture summaries in symbol → file → directory → subsystem →
  main-flow order, with parent dependency checks and persisted artifacts.
- Authenticated REST and direct MCP reading the same state; backup/restore,
  removal/reinstallation, collection isolation and stale-index rejection.
- Real JavaScript and TypeScript scans, each returning three fixture symbols.
- Seven app unit tests; 62 Rust workspace tests; formatting and strict Clippy.
- Python and JavaScript CLI scaffolding, validation, packaging, consent, action
  calls and retry receipts. Child processes did not inherit a test credential.
- Managed environment reuse, separate collection state, incomplete receipts,
  output bounds and timeout cleanup of ordinary child processes.
- A pinned Python wheel installed and imported successfully; an incorrect wheel
  hash prevented activation. This separate dependency test used a temporary
  CPython 3.12 interpreter with pip bootstrap support.

Limits observed:

- clangd, fortls, gopls, rust-analyzer and JDTLS were absent from this host's PATH.
  The app reported incomplete scans and missing-server issues for their languages.
  Full native language coverage was not demonstrated.
- The host Python lacked pip/venv bootstrap support. The documentation app needs
  no pip packages and worked with `venv --without-pip`; Python apps with pip
  dependencies need an interpreter with that support installed.
- Native code has unsandboxed OS-user access after `host.execute` approval.
  Dependency isolation is not filesystem, network or memory isolation.
- The existing test Docker daemon was stopped. No fresh real-container regression
  result is claimed for this branch; the earlier container results below remain
  historical evidence.
- Source validation/export checks passed. Runtime and registry release alignment
  is required before publishing script packages.

Reproduce the native acceptance test:

```sh
python3 apps/repo-documentation-tool/tests/integration.py /path/to/branch/rhyven --script
```

## Earlier container acceptance — September 24, 2026

Tested September 24, 2026 on Linux x86-64 / WSL2, using Docker Engine 28.5.1.
Rhyven's existing release binary installed and operated the app. No Rust runtime
or transport changes were needed for this app.

## Passed

- Seven unit tests: nested/async Python declarations and line positions;
  bottom-up summaries and transitive invalidation; stale source/artifact rejection;
  path traversal and symlink rejection; 100-reference cap, deduplication and
  external-location exclusion; pagination/subsystem coverage; malformed Python
  combined with language-server startup failure.
- Rhyven manifest validation, package creation, real container conformance tests,
  installation and discovery through the existing three MCP tools.
- Import helper against actual stdio MCP, followed by Python structure scanning.
- Real Pyright: four fixture symbols, expected declaration lines, live reference
  refresh, exactly 100 stored references with truncation flagged for a function
  used more than 100 times. Pyright also returned call-hierarchy results.
- Calling-agent-written fixture summaries persisted through symbol, file,
  directory, subsystem and main-flow levels. Premature parent writes were
  rejected. All final summaries were fresh in `structur.json` and `ATLAS.md`.
- Direct REST and local MCP read the same summaries.
- Full app-state backup/restore into another collection, removal/reinstallation
  with retained state, independent empty state in a separate collection, and
  rejection of queries against changed source before rescan.
- Real language servers, without app network access:

| Language | Server | Fixture symbols |
| --- | --- | ---: |
| Python | Pyright + AST | 4 |
| C | clangd | 2 |
| C++ | clangd | 3 |
| Fortran | fortls | 1 |
| Go | gopls | 2 |
| Rust | rust-analyzer | 2 |
| Java | JDTLS | 2 |
| JavaScript | TypeScript language server | 3 |
| TypeScript | TypeScript language server | 3 |

Each fixture reported complete structural coverage and no file-scan issues.
These are small fixture tests, not evidence that every real project or language
feature resolves without its dependencies and build configuration.

## Issues found and fixed

The TypeScript language server rejected the removed `--tsserver-path` flag.
Its path now uses the documented initialization configuration, with automatic
package acquisition disabled. Both JS and TS passed the subsequent full run.
See the upstream [initialization options](https://github.com/typescript-language-server/typescript-language-server/blob/master/docs/configuration.md).

Malformed Python plus a failed LSP startup originally bypassed partial-coverage
handling; the fallback now preserves a partial report rather than aborting.
Exporting an artifact after source changes now rejects the stale index.

The initial temporary daemon used the VFS storage driver, which copied the large
image for each new container. Acceptance ran on a separate isolated overlay2
daemon after moving the built image there and replacing its app source with the
final files. The production Dockerfile builds those same app files and toolchains.

## Distribution status

The source is Apache-2.0. Version 0.1.1 includes security-related toolchain updates;
the public registry still carries version 0.1.0 until a new package/image is
published and accepted. Source availability alone is not an image-release test.

## Remaining limits / release work

- The uncompressed image is approximately 1.9 GB because it includes all language
  toolchains. The image and marketplace listing are public preview releases.
- Only Linux x86-64 was executed here. ARM64 build paths are present but untested;
  Docker Desktop/macOS needs its own acceptance run.
- Inputs are explicitly imported snapshots: changes on the host require another
  import/rescan. No host checkout is implicitly mounted.
- References and caller/callee results depend on each language server, project
  configuration and available offline dependencies. Structural `complete` does
  not imply complete relationship resolution.
- App bounds remain 5,000 files / 20 MiB, 200,000 bytes per file, a 100-reference
  cap per symbol, bounded scan duration and paginated output. See the README.
- Semantic summary quality belongs to the calling agent. The app enforces ordering
  and freshness; it does not use an internal LLM or verify prose for correctness.

Reproduce with the commands in [README.md](README.md). Set `RHYVEN_TEST_ARTIFACTS` to an explicit output directory to retain
synthetic fixture artifacts. By default, acceptance state is temporary.

## Header package reassessment — 2026-10-03

The [candidate image audit](https://github.com/rhyven-ai/rhyven/actions/runs/37145695026)
built and passed functional integration for version 0.1.1. Its scan failed because
Ubuntu installed `linux-libc-dev` version `6.8.0-146.146`, while the previous
assessment covered only `6.8.0-142.142`.

Evidence from the same image:

- Image ID: `sha256:f4d24791fa2c2ae5ae2cd9e7a3b098685dd217cfd1d8acd37a6d679a1ee889e0`.
- Package inventory: 990 regular-file paths, all `.h` files below `/usr/include/`
  or documentation below `/usr/share/doc/linux-libc-dev/`. No kernel executable.
- Inventory SHA-256: `5a15802d74dc2627710dab673e69c73f7099bc42074f3b81f1eda0e56b2f44d0`.
- All 168 high/critical findings belong to that header package and describe
  kernel vulnerabilities. No other high/critical findings or secrets were reported.

The reviewed package supplies interfaces for code analysis; its kernel advisories
do not identify executable kernel code in this image. The host kernel remains
the operator's responsibility. This is an applicability assessment, not a claim
that the host kernel is patched or that no lower-severity findings exist.

The gate now covers only the new exact package version, requires the package
inventory and scan to identify the same image, checks every inventoried path,
and applies the assessment only to findings whose description identifies the
kernel. All other high/critical findings and secrets still block release.
The original expiry, **2026-10-11**, is unchanged. Publication rebuilds, tests,
scans and inventories its exact image again; the audit image is not blindly reused.
