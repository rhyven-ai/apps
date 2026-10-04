---
name: build-rhyven-script-app
description: Build and test a native Python or JavaScript Rhyven app without Docker, including packaged source, locked dependencies, action schemas and collection state. Use for custom logic that runs once per action with approved host access.
---

# Build a native script app

Target: Rhyven 0.5.4, app format 2, protocol `rhyven.action/1`.
Linux is the tested platform. Native Windows execution is unsupported.
Use the installed runtime's `--help` and generated scaffold as the contract.

## Marketplace source requirement

For now, apps submitted to the public Rhyven marketplace must be open source.
Provide a publicly accessible source repository with an OSI-approved license in
LICENSE. Publish the source corresponding to the submitted release, including
app logic, manifests and container build files when applicable; a public binary
or image alone is insufficient. Community apps do not have to use Apache-2.0.
This is a marketplace submission policy, not a restriction on private local apps.
Do not publish a private repository or relicense code without user authorization.

## Choose the execution model

Use declarative operations for records, expressions and rules they already cover.
Use native scripts for custom Python/JavaScript logic when unsandboxed execution
as the OS user is acceptable. Containers fit system dependencies, other languages,
binary assets and enforced isolation. Persistent processes need container services.

`host.execute` allows host filesystem, network and subprocess access. A venv or
node_modules directory isolates dependencies, not permissions. Do not describe
state.write or declared endpoints as a native filesystem/network sandbox.

## Scaffold

The host needs Python 3.10+ or Node 20+. Rhyven does not install interpreters or
system packages. Respect the user's chosen language and project location.

```sh
rhyven --version
rhyven app init acme/text-tools --runtime python --dir ./text-tools
```

Use `--runtime javascript` for Node. Read generated `app.json`, source and tests.
Choose the publisher's namespace; do not use the reserved `rhyven` namespace.

The Python manifest contains these fields alongside objects, actions and tests:

```json
{
  "execution": {
    "driver": "script",
    "language": "python",
    "protocol": "rhyven.action/1",
    "entrypoint": "main.py",
    "python_version": "3.10",
    "environment": "isolated",
    "timeout_seconds": 30
  },
  "permissions": ["state.read", "state.write", "host.execute"],
  "files": ["main.py"]
}
```

For Node use `language: javascript`, `entrypoint: main.mjs`, and
`node_version: "20.0"` instead of python_version. Version fields are minimum
major.minor values. Entrypoints are file paths, not shell commands or launch flags.
Declare each action's input and output schemas; no custom MCP server is needed.

## Implement the action contract

Each invocation reads one JSON request from stdin and returns one JSON envelope
on stdout, then exits. Keep logs on stderr and preserve the generated adapter.

```json
{"protocol":"rhyven.action/1","category":"acme/text-tools","function":"action_analyze","args":{"text":"hello world"},"context":{"actor":"agent","request_id":"example-id","collection":"trial","data_dir":"/runtime/supplied/path"}}
```

Reply with `{"result":{...}}` matching the output schema, or
`{"error":{"code":"APP_ERROR","message":"Explanation"}}`.
Use `context.data_dir` or `RHYVEN_DATA_DIR` for persistent collection-specific
files. Never hardcode the example path, use the working directory as durable
storage, or share user data through a dependency environment.

Timeouts are 1–300 seconds; stdout and stderr are each bounded to 1 MiB.
Ordinary child processes are cleaned up after a call. Do not launch detached
workers or claim native scripts provide CPU/memory quotas or service supervision.
For retries, reuse a request ID only for the identical operation. On
`script_incomplete`, inspect persisted state before starting a new attempt;
side effects may have happened before the process stopped.

## Package dependencies

Include all source and lockfiles in `files`. Only UTF-8 package files are embedded;
the current limits are 128 files and a 1 MiB package. Do not include venvs,
node_modules, secrets, symlinks or paths outside the app directory.

Set `execution.dependencies` as needed:

```json
{"pip":"requirements.lock","npm":"package-lock.json"}
```

- pip: one `name==version --hash=sha256:HASH` requirement per noncomment line.
  Use real artifact hashes and pin/hash every transitive dependency. Multiple
  hashes per requirement are allowed. Only wheels are installed; source builds,
  editable requirements, URL requirements and pip option directives are rejected.
  The host needs venv/pip bootstrap support. Do not invent hashes or assume a
  multiline pip-generated requirements file is accepted without normalization.
- npm: include package.json and a version-3 package-lock.json. Entries require
  HTTPS artifacts and SHA-512 integrity. Installation uses `npm ci --ignore-scripts`;
  local/git dependencies and install-script-dependent builds are unsuitable.
- Both managers can be declared in either language when the app needs both tools.
  Missing imports fail; Rhyven does not infer or install undeclared dependencies.

Installation prepares dependencies after permission approval. `isolated` is the
default; the same package may reuse its environment across collections while
keeping separate data. `shared` reuses environments only for matching interpreter
identities, locks and npm manifests. It is not one mutable global venv.
Changed dependencies create a new environment. Do not pip-install into a prepared
environment. A missing environment or changed interpreter requires reinstallation.

## Validate, test and distribute

```sh
rhyven app validate ./text-tools
rhyven app test ./text-tools --allow-host
rhyven app package ./text-tools --out ./text-tools.rhyven.json
rhyven app test ./text-tools.rhyven.json --allow-host
```

Validation and packaging do not run native code or install dependencies.
`--allow-host` explicitly allows unsandboxed tests; use it only when execution is
within the user's authorized task. `--allow-container` does not authorize native
execution. Test the packaged artifact, error cases and state isolation, not just
its manifest. An unavailable interpreter is a blocked execution test, not a pass.

For distribution, upload the self-contained JSON package as a new release asset
and submit its exact byte hash/asset ID to the registry. Use a matching rc.9+
validator. `rhyven app publish` only writes a local catalog. Public uploads and
registry PRs require authorization. See https://rhyvenai.com/#skills/publish-rhyven-app.

Removal retains app data; backup/restore covers the app data directory and
rebuilds environments. Container-to-script conversion is not an in-place update:
use a separate installation and explicit migration. Native migration/health
hooks are unsupported; declarative SQLite migrations remain available.

In 0.5+, actions may include optional `keywords` (up to 16 strings, each 1–64
bytes) to improve discovery without changing execution. Use the 0.5 validator.
