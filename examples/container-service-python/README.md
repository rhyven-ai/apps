# Persistent Python service example

This counter runs continuously, persists ticks/action counts under `/data`, and
can call the installed Project Knowledge app through a scoped function grant.
Its Python runtime lives in the Docker image. It needs no host Python environment.

Generate a copy with `rhyven app init owner/counter --runtime service --dir ./counter`
or build this directory directly:

```sh
docker build --iidfile image.id .
rhyven app package . --image "$(cat image.id)" --out counter.rhyven.json
rhyven app test counter.rhyven.json --allow-container
# Review the manifest permissions before accepting installation.
rhyven --collection demo install counter.rhyven.json --accept-permissions
rhyven daemon start
rhyven --collection demo service start example/background-counter
rhyven --collection demo call rhyven_call '{"category":"example/background-counter","function":"action_status","args":{}}'
rhyven --collection demo service stop example/background-counter
```
Replace the placeholder image in `app.json` by packaging with `--image` and an
immutable built image ID. Nothing in this directory is published automatically.

Example version 0.1.1 updates the scoped knowledge grant from 0.3.0 to 0.4.0.

Actions: `status`, `increment`, `remember`, and `health`. `remember` needs
`rhyven/project-knowledge` 0.4.0 in the same collection. The supplied
`rhyven_service.py` implements the framed input pump and callback correlation.
The wire contract is `rhyven.service/1`: initialize/ready, call/response,
ping/pong, and scoped callback/callback_result JSON lines. Stdout is protocol-only;
logs go to stderr. Stop background writers and flush `/data` during shutdown.

The app is a lifecycle and composition example, not an autonomous agent controller.

Rhyven-authored files are Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
The separate engine and base-image components retain their own licenses.
