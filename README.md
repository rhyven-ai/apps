# Rhyven apps

Open-source headless applications for the Rhyven runtime. All Rhyven-authored
app materials in this repository are licensed under **Apache-2.0**. The Rhyven
engine is also open source under Apache-2.0, in the separate
[rhyven-ai/rhyven repository](https://github.com/rhyven-ai/rhyven).

| App | Source | Execution |
| --- | --- | --- |
| Work Management | [manifest](catalog/work-management.json) | Declarative |
| Project Knowledge | [manifest](catalog/project-knowledge.json) | Declarative |
| Error Management | [manifest](catalog/error-management.json) | Declarative |
| CI Management | [manifest](catalog/ci-management.json) | Declarative |
| Inventory | [manifest](catalog/inventory.json) | Declarative |
| User Questions | [manifest and usage](apps/user-questions/README.md) | Declarative |
| Starter Runner | [source and setup](apps/starter-runner/README.md) | Persistent container |
| File RAG | [standalone repository](https://github.com/rhyven-ai/file-rag) | Native Python script |
| Razorback | [standalone repository](https://github.com/rhyven-ai/razorback) | Native Python connection app |
| Messaging | [source and build instructions](apps/messaging/README.md) | Persistent container |
| Rhyven Repo Documentation Tool | [source and build instructions](apps/repo-documentation-tool/README.md) | On-demand container or native Python |

CI Management records pipeline state; it does not execute builds. Messaging and Repo Documentation Tool have source version 0.1.1 candidates. Check the
[public registry](https://github.com/rhyven-ai/registry) for installable versions
and immutable image digests; publishing source does not release a new image.

## Use or modify an app

Install a compatible Rhyven binary separately. These apps use manifest format 2
and the three-tool interface in Rhyven 0.5.2. Linux is the tested container platform; check the runtime's platform
requirements and license terms. No Rust source build is needed to author an app.

From this repository's root:

```sh
rhyven app validate catalog/inventory.json
rhyven app test catalog/inventory.json
rhyven app package catalog/inventory.json --out /tmp/inventory.rhyven.json
# Review permissions before accepting installation.
rhyven --home ./trial-state --collection demo install /tmp/inventory.rhyven.json --accept-permissions
rhyven --home ./trial-state --collection demo call rhyven_describe '{"category":"rhyven/inventory"}'
```

For a container app, follow its README to build the image, package the immutable
image ID and run `app test --allow-container`. A local image ID only works on
that host. Distribution needs a pullable repository digest. Python and language
servers are inside the image; recipients need Docker, not host language runtimes.

To publish a modified app, choose your own app ID/publisher namespace, update the
guide and behavior tests, and retain the license/notices. Record modifications.
The license grants no general permission to brand a fork as a Rhyven product.
App state belongs to the selected local collection; do not commit it here.

## Agent interface

Apps share `rhyven_categories()`, `rhyven_describe(category)`, and
`rhyven_call(category, function, args)`. The category is an installed app ID.
Read its description for current function schemas and guidance. Agents can
coordinate tasks, knowledge and messages without app-specific MCP servers.

Give your agent the [Use Rhyven skill](skills/use-rhyven/SKILL.md), or merge the
shorter [usage rule](skills/use-rhyven/RULE.md) into its supported project
instructions. Both cover discovery, collection selection, marketplace approval
and app operations. Preserve existing instructions; neither file changes client
configuration or grants installation consent by itself.

## Build your own

- [Declarative app skill](skills/build-rhyven-declarative-app/SKILL.md)
- [Native Python and JavaScript skill](skills/build-rhyven-script-app/SKILL.md)
- [Native Python example](examples/script-python/README.md)
- [Native JavaScript example](examples/script-javascript/README.md)
- [On-demand container skill, including Dockerfile](skills/build-rhyven-container-app/SKILL.md)
- [Persistent service skill, including Dockerfile](skills/build-rhyven-service-app/SKILL.md)
- [Publishing skill](skills/publish-rhyven-app/SKILL.md)
- [Small Python action example](examples/container-python/README.md)
- [Persistent Python example](examples/container-service-python/README.md)

`examples/remote-inventory.rhyven.json` is an experimental loopback contract
fixture, not a hosted service or an advertised v1 backend.

## Tests

```sh
python3 -m unittest discover -s apps/starter-runner/tests -v
python3 -m unittest discover -s apps/messaging/tests -v
python3 -m unittest discover -s apps/repo-documentation-tool/tests -v
```

These unit tests need only Python's standard library. Docker integration tests
need the runtime binary and a built image; see each app's README. The documentation
app's external toolchains are downloaded only during image builds.

For dependency licensing and image distribution obligations, read
[THIRD_PARTY.md](THIRD_PARTY.md). Report security issues privately through the
[registry security channel](https://github.com/rhyven-ai/registry/security/advisories/new).
Do not attach credentials, customer repositories, app state or private reports
to public issues. Contributions should include tests and use Apache-2.0 terms.

## Optional starter apps

Existing harnesses can use all general apps through the same three tools. Users
without a harness can add [Starter Runner](apps/starter-runner/README.md), which
connects their own model API to tasks, knowledge and user questions. It requires
Docker. [User Questions](apps/user-questions/README.md) is a separate declarative
app, also useful to existing harnesses. Neither is required for ordinary app use.
