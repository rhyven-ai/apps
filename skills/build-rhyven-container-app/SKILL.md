---
name: build-rhyven-container-app
description: Build a Rhyven on-demand container app with arbitrary Python or other code, a Dockerfile, JSON action schemas, persistent data, and explicit execution tests. Use for bounded actions that finish and exit.
---

# Build an on-demand container app

Target: Rhyven 0.4.0-rc.7, app format 2, protocol `rhyven.container/1`.
Use this mode for custom calculations, parsers, code analysis, and API clients.
Rhyven starts a container for an action, sends JSON on stdin, validates its
response, and retains `/data` between calls. Use service mode for background work.

The image contains the language runtime and dependencies. Recipients need a
compatible local Docker Engine, not Python or a host virtual environment.
Advertise tested platforms only: Linux is supported; macOS is a feedback preview.

## Scaffold the complete contract

```sh
rhyven --version
rhyven doctor
rhyven app init acme/text-analysis --runtime container --dir ./text-analysis
```

Inspect `container.ready` in the doctor report; exit success alone does not mean
Docker is ready. Report unmet host capabilities rather than weakening isolation.
Edit generated `app.json`, `main.py`, `Dockerfile`, guide, and behavior tests.
Keep the app ID and publisher under a namespace the author controls.

The scaffold declares:

- `hosting.mode: local`, `execution.driver: container`.
- `execution.protocol: rhyven.container/1` and an immutable image reference.
- Explicit `timeout_seconds`, `memory_mb`, and `cpus`.
- `state.read`, `state.write`, and `container.execute` permissions.
- Each action's description, input schema, and output schema.

Container actions implement arbitrary code; they do not use the declarative
`operation/object/set` action implementation. Describe exact errors and retry
behavior in `guide`. Do not invent additional MCP tools or app-specific REST routes.

## Implement the one-request process

Input is a single newline-delimited JSON request:

```json
{"protocol":"rhyven.container/1","category":"acme/text-analysis","function":"action_analyze","args":{"text":"hello world"},"context":{"actor":"agent","request_id":"optional-retry-id","collection":"demo","data_dir":"/data"}}
```

Dispatch by `function`, check the protocol, and return exactly one JSON response
on stdout, followed by a newline. Log diagnostics to stderr. Successful results
must match the action's declared output schema. For the generated example:

```json
{"result":{"words":2,"sha256":"a-valid-computed-sha256","calls":1}}
```

The sample hash above is illustrative; compute the real hash in code.
An app failure instead returns:

```json
{"error":{"code":"UNSUPPORTED_FUNCTION","message":"Unknown action"}}
```

Do not return both `result` and `error`, emit progress logs on stdout, keep a
background server running, or assume the container survives the request.
Start from the generated `main.py` for working framing and persistence.

## Build the Dockerfile

For the dependency-free Python scaffold, this is sufficient:

```dockerfile
FROM python:3.12-alpine
RUN python -m pip uninstall -y pip
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY main.py /app/main.py
ENTRYPOINT ["python", "-B", "/app/main.py"]
```

Choose a tested base image. Pin it to a real digest for repeatable release builds
and scan both OS and language packages. Removing unused pip reduces shipped
dependencies; it does not replace vulnerability scanning.

For Python dependencies, copy a fully pinned, hashed `requirements.txt` before
copying source, then install at build time:

```dockerfile
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /app/requirements.txt \
    && python -m pip uninstall -y pip
```

Use this dependency step instead of the early pip removal in the first Dockerfile.
Do not install dependencies at action time. Other languages can use a multi-stage
Dockerfile and copy only the compiled executable/runtime into the final image;
the stdin/stdout protocol remains identical.

Copy explicit source files. Add `.dockerignore` exclusions for `.git`, `.env`,
credentials, trial state, virtual environments, caches, and build artifacts.
Never put tokens in Docker build arguments, image layers, or the app manifest.

## State and permissions

Write persistent app state only under `RHYVEN_DATA_DIR` (normally `/data`). Use
atomic replace or a database transaction, and persist job IDs when effects need
deduplication. Each collection has separate data; Docker shares image layers.
Rhyven's result receipts do not make arbitrary filesystem/network effects atomic.
An interrupted call can return `container_incomplete`; inspect it before retrying.

Expect a read-only image filesystem, bounded writable `/tmp`, dropped capabilities,
CPU/memory/PID limits, and an execution timeout. There is no privileged mode,
Docker socket, host networking, arbitrary host mounts, or published app port.
Network access is disabled unless `network.connect` is declared; that permission
enables container networking and is not a per-domain firewall.
Named environment secrets require `secrets.read` and `execution.secrets`; names
must use the `RHYVEN_SECRET_` prefix. The host supplies values. Request only
capabilities needed by the app.

## Verify the packaged image

```sh
rhyven app validate ./text-analysis
docker build --iidfile ./text-analysis-image.id ./text-analysis
rhyven app package ./text-analysis --image "$(cat ./text-analysis-image.id)" --out ./text-analysis.rhyven.json
rhyven app test ./text-analysis.rhyven.json --allow-container
# After the user reviews and approves package permissions:
rhyven --home ./analysis-trial --collection demo install ./text-analysis.rhyven.json --accept-permissions
rhyven --home ./analysis-trial --collection demo call rhyven_describe '{"category":"acme/text-analysis"}'
rhyven --home ./analysis-trial --collection demo call rhyven_call '{"category":"acme/text-analysis","function":"action_analyze","args":{"text":"hello world"}}'
```

`app package` validates container metadata; it does not execute its tests.
`--allow-container` explicitly permits image pulls and test code execution in
temporary app state. Include useful results, invalid input, app errors, repeated
calls with persistence, and timeout handling. Test without undeclared network.
Report unavailable Docker or untested architectures as limitations.

For distribution, publish the image and repackage using its pullable repository
digest, such as `ghcr.io/acme/text-analysis@sha256:ACTUAL_DIGEST`. A local image ID
is only suitable for local trials. Test that exact release digest again.

Deliver app.json, implementation, Dockerfile, guide, tests, package and results.
Use the publishing skill for release assets and the registry PR. Installation
alone does not start a server; agents still use discover, describe, and call.
