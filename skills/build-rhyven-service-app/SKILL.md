---
name: build-rhyven-service-app
description: Build a persistent Rhyven container service with a Dockerfile, supervised lifecycle, durable state, health checks, and scoped peer-app calls. Use for workers, watchers, inboxes, and background processing.
---

# Build a persistent Rhyven service

Target: Rhyven 0.5.2, app format 2, protocol `rhyven.service/1`.
Use a service when work must continue after an action returns or an agent
disconnects. Rhyven supervises one instance per app and collection. The image
contains the program and its dependencies; no host Python or venv is needed.
An ordinary web server image needs a Rhyven protocol adapter before it is usable.

## Marketplace source requirement

For now, apps submitted to the public Rhyven marketplace must be open source.
Provide a publicly accessible source repository with an OSI-approved license in
LICENSE. Publish the source corresponding to the submitted release, including
app logic, manifests and container build files when applicable; a public binary
or image alone is insufficient. Community apps do not have to use Apache-2.0.
This is a marketplace submission policy, not a restriction on private local apps.
Do not publish a private repository or relicense code without user authorization.

## Choose this backend

Use a service for work that must continue between calls, long-lived connections
or resident workers. Persistence of data alone does not require a service:
declarative apps, native scripts and on-demand containers all retain app state.
Native scripts run once per action and cannot replace the supervised service
backend. Neither service mode nor Docker makes business logic deterministic.

## Scaffold and inspect

```sh
rhyven --version
rhyven doctor
rhyven app init acme/background-counter --runtime service --dir ./counter
```

Check `container.ready` in doctor output. Review generated `app.json`, `main.py`,
`rhyven_service.py`, Dockerfile, guide and tests. Keep the generated adapter unless
you deliberately implement the full service protocol in another language.

The manifest uses `execution.driver: container`, `execution.mode: service`, and
`execution.protocol: rhyven.service/1`. Declare the immutable image, CPU/memory
limits, action/startup/shutdown timeouts, restart limit, and start policy.
Keep `manual` start unless first-use startup is part of the intended behavior;
`on-demand` permits that startup but still requires a running supervisor.

Permissions include `state.read`, `container.execute`, and `service.run`.
Add `state.write` for writable `/data`. All action inputs/outputs need schemas.

## Implement actions and background work

The Python scaffold registers functions like:

```python
from rhyven_service import Service

def health(args, context, service):
    return {"ok": True}

if __name__ == "__main__":
    Service({"action_health": health}).run()
```

This snippet only illustrates registration. Extend the complete generated example
for startup, shutdown, threading and persistence. Keep code and manifest actions
in agreement. Declare a cheap `health_action` that does not depend on a peer app.

The adapter must handle initialize/ready, correlated call/response messages,
heartbeat ping/pong, and shutdown. Stdout is newline-delimited protocol JSON;
stderr is logs. Do not use the one-shot container request loop for service mode.
Keep the input pump responsive during actions and background work.

Load persistent state before readiness. Put durable data under `RHYVEN_DATA_DIR`
(`/data`), protect shared state from concurrent background/action access, and use
atomic writes or database transactions. On SIGTERM, stop workers, flush state,
and exit within `shutdown_timeout_seconds` (1–30 seconds).

Persist job IDs and completion records for recoverable background work. Runtime
request receipts do not make app data, peer mutations, and external side effects
one transaction. `service_incomplete` means a call may have executed; reconcile
state rather than automatically repeating it with a new request ID.

## Add peer-app cooperation only when needed

The scaffold includes an optional Project Knowledge callback. Inspect its actual
`execution.calls` version pin. To retain it, install that exact peer version in
the same collection and test the callback; installing a service does not install
its peers. For an independent app, remove the `remember` action/handler, its guide
references, `execution.calls`, and the `app.call` permission together.

Peer callbacks require `app.call` plus exact category/function/version grants.
Only local declarative targets in the same collection are supported. Calls cannot
target platform management, another collection, a container/service, or a remote
provider. The supervisor supplies the caller identity and checks each grant.
Use stable request IDs for peer mutations; avoid embedding a broad REST token.

## Build the image

For the dependency-free Python scaffold:

```dockerfile
FROM python:3.12-alpine
RUN python -m pip uninstall -y pip
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY main.py rhyven_service.py /app/
ENTRYPOINT ["python", "/app/main.py"]
```

Pin the release base to a verified digest and scan the final image. If dependencies
are needed, copy a locked, hashed requirements file and run
`python -m pip install --no-cache-dir --require-hashes -r requirements.txt` before
removing unused pip. Use explicit COPY paths and a `.dockerignore` excluding
secrets, `.git`, caches and test state. Other languages may use multi-stage builds.

The image filesystem is read-only; `/data` and bounded temporary storage are
writable as permitted. Docker socket access, privilege escalation, host networking,
arbitrary mounts and app port publishing are unavailable. Declare `network.connect`
only when required; it is coarse network access, not domain filtering. Declare
`secrets.read` and named `execution.secrets` for host-supplied environment secrets;
names must use the `RHYVEN_SECRET_` prefix.

## Validate and exercise the lifecycle

```sh
rhyven app validate ./counter
docker build --iidfile ./counter-image.id ./counter
rhyven app package ./counter --image "$(cat ./counter-image.id)" --out ./counter.rhyven.json
rhyven app test ./counter.rhyven.json --allow-container
# After the user reviews and approves permissions and peer grants:
rhyven --home ./counter-trial --collection demo install ./counter.rhyven.json --accept-permissions
rhyven --home ./counter-trial daemon start
rhyven --home ./counter-trial --collection demo service start acme/background-counter
rhyven --home ./counter-trial --collection demo call rhyven_describe '{"category":"acme/background-counter"}'
rhyven --home ./counter-trial --collection demo call rhyven_call '{"category":"acme/background-counter","function":"action_increment","args":{"amount":2,"request_id":"increment-1"}}'
rhyven --home ./counter-trial --collection demo service status acme/background-counter
rhyven --home ./counter-trial --collection demo service logs acme/background-counter
rhyven --home ./counter-trial --collection demo service stop acme/background-counter
```

Use the same home for the daemon and clients. Packaging does not execute code;
`app test --allow-container` does. Verify background progress without agent calls,
state after restart, same-ID retries, action errors, clean stop, and recovery
after a crash. An explicit stop must remain stopped until explicitly started.
Confirm termination before inspecting snapshots or replacing stored data.

The supervisor owns restart/backoff; do not add a competing Docker restart policy.
Clients closing does not stop the service. Default aggregate budgets are eight
services, 4096 MiB memory and four CPUs; inspect daemon status for admission errors.
Clean up a trial by stopping its service and `rhyven --home ./counter-trial daemon stop`.

For OS startup, `rhyven daemon unit --out ./rhyven-supervisor.service` generates
a unit for review; it does not install/enable one. Linux user units usually start
at login; boot without login needs systemd lingering and an available Docker engine.
The current Rhyven preview supports Linux service supervision.

Agents use the same three tools as other apps. Service lifecycle functions live
under `rhyven/runtime`; app actions use the installed app ID as their category.
Deliver implementation, manifest, Dockerfile, tests, package and lifecycle results.
For distribution, use a pullable immutable image digest and the publishing skill.

In 0.5+, actions may include optional `keywords` (up to 16 strings, each 1–64
bytes) to improve discovery without changing execution. Use the 0.5 validator.
