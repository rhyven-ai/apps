# Python script app

Requires the experimental script runtime branch and Python 3.10+ on PATH.
Review `host.execute`: app code runs unsandboxed as your OS user.

```sh
rhyven app validate .
rhyven app test . --allow-host
rhyven app package . --out ../script-app.rhyven.json
rhyven --collection script-trial install ../script-app.rhyven.json --accept-permissions
```

The `analyze` action counts words, calculates a SHA-256 checksum and persists a
per-collection invocation count. Set `execution.environment` to `shared` before
packaging to share an identically locked dependency environment across apps.
