# Rhyven Repo Documentation Tool acceptance results

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
