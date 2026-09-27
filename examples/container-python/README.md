# Python container app

Build the image, package its immutable local image ID, test, then install:

```sh
docker build --iidfile image.id .
rhyven app package . --image "$(cat image.id)" --out app.rhyven.json
rhyven app test app.rhyven.json --allow-container
rhyven --collection demo install app.rhyven.json --accept-permissions
rhyven --collection demo call rhyven_call '{"category":"example/text-analysis","function":"action_analyze","args":{"text":"hello world"}}'
```

Use the category name chosen at `app init` if you renamed this example. The zero
image ID in app.json is a placeholder; packaging replaces it with your build ID.
The application reads one JSON request, writes one JSON response, and exits.
Persist files only in RHYVEN_DATA_DIR (/data). Logs belong on stderr.
For distribution, push the image to your registry and package its immutable
repository@sha256 digest instead of the local image ID. No Python installation
is needed on the recipient's host; a local Docker Engine is required.

Rhyven-authored files are Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
The separate engine and base-image components retain their own licenses.
