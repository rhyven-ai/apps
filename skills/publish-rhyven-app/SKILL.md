---
name: publish-rhyven-app
description: Prepare, test, package, and submit a Rhyven app to the GitHub-backed marketplace. Use for release assets, container image digests, registry entries, and publishing PRs.
---

# Publish a Rhyven app

Target: Rhyven 0.4.0-rc.7, app format 2. Use the installed CLI's `--help`
to resolve version differences. This workflow needs Rhyven, Git, and authenticated
GitHub CLI access to the publisher's repository. Container apps also need Docker.

## Establish the release target

1. Read `app.json`, its guide, tests, and any Dockerfile.
2. Establish the app ID, publisher, version, release repository, visibility, and
   target registry from the user's instructions. Resolve missing information.
3. Public releases expose uploaded files; check the exact files before upload.
   Keep credentials, customer data, and private platform source out of packages.
   Proceed with publication when authorized; otherwise prepare reviewable files
   and ask before creating public resources or submitting the PR.
4. Use the publisher's registered namespace, not the reserved `rhyven` namespace.
   The public registry is `rhyven-ai/registry`. Read its current contribution
   instructions. New namespaces require maintainer registration; organization
   submissions currently go through the maintainer.

`rhyven app publish` publishes into a LOCAL catalog. It does not create a GitHub
release, upload an image, or submit a marketplace PR.

## Validate and package

Replace `acme`, repository names, paths, and version with the actual release.

```sh
rhyven --version
rhyven app validate ./my-app
rhyven app test ./my-app
rhyven app package ./my-app --out ./my-app.rhyven.json
```

The commands above are for a declarative app. Packaging runs its behavior tests.
For containers/services, build and test the image explicitly, then publish that
image to a registry recipients can access. The image includes executable code;
the JSON package references it rather than embedding the build directory.

```sh
docker build --iidfile ./my-app-image.id ./my-app
rhyven app package ./my-app --image "$(cat ./my-app-image.id)" --out ./my-app-local.json
rhyven app test ./my-app-local.json --allow-container
docker tag "$(cat ./my-app-image.id)" ghcr.io/acme/my-app:0.1.0
docker push ghcr.io/acme/my-app:0.1.0
```

Take the actual immutable repository digest from the push result. Replace the
placeholder below; a tag or local-only image ID is insufficient for distribution.

```sh
rhyven app package ./my-app --image ghcr.io/acme/my-app@sha256:REPLACE_WITH_DIGEST --out ./my-app.rhyven.json
rhyven app validate ./my-app.rhyven.json
rhyven app test ./my-app.rhyven.json --allow-container
```

Test the exact image recipients will pull, for each advertised CPU architecture.
An unavailable Docker engine is a blocked execution test, not a passing test.
Ensure runtime and registry validator versions accept the features you use.

## Create the release and entry

After authorization, upload the final package to the namespace owner's repository.
Use a new version; do not replace assets referenced by existing registry entries.

```sh
gh release create v0.1.0 ./my-app.rhyven.json --repo acme/my-app --title 'My app 0.1.0' --notes-file ./release-notes.md
gh api repos/acme/my-app/releases/tags/v0.1.0 --jq '.assets[] | {id, name}'
```

Use the numeric ID of `my-app.rhyven.json` in this command:

```sh
rhyven registry-entry ./my-app.rhyven.json --repository acme/my-app --asset-id 123456789 > ./entry.json
```

The generated hash covers the exact release bytes. Do not reformat or modify the
uploaded package afterward. Runtime canonical hashes are a different value.
Review ID, version, publisher, description, permissions, image digest, execution
limits, and any secret names against the final manifest.

## Submit and verify

1. Fork/clone the target registry and create a branch from its current default
   branch. Save the original `index.json` outside the checkout as the base file.
2. Append the generated entry to `apps`; preserve all prior entries unchanged.
   Keep registry format 1 and the existing namespace ownership mapping.
3. Validate the candidate against the saved original:

   ```sh
   rhyven registry-validate ./index.json --base /path/to/original-index.json
   ```

4. Submit a PR from the authorized publisher account with app purpose, version,
   permissions, test results, execution requirements, and package/image links.
   Use `gh pr create --body-file ./pr-body.md` for the prepared description.
5. Wait for automated validation and maintainer review. A PR submission is not
   a marketplace listing. New entries are `Unverified`; do not invent Verified
   or Certified status. Account ownership does not establish certification.
6. After merge, use a fresh Rhyven home to download and install the listing.
   Review permissions with the user before accepting an install. Public registry
   access requires no GitHub account; private images still require Docker auth.

```sh
rhyven --home ./release-trial --collection demo registry-sync rhyven-ai/registry --anonymous
rhyven --home ./release-trial --collection demo inspect acme/my-app
# After permission review and approval:
rhyven --home ./release-trial --collection demo install acme/my-app --accept-permissions
rhyven --home ./release-trial --collection demo call rhyven_categories '{}'
rhyven --home ./release-trial --collection demo call rhyven_describe '{"category":"acme/my-app"}'
```

Exercise one useful action through `rhyven_call`, read persisted state from a
second client in the same collection, and report the exact installed version.
For a persistent service, start the daemon with the same home before starting
the app. Follow its service skill for readiness, stop, and restart checks.

Registry validation checks schemas, metadata, byte hashes, and declarative tests;
it does not execute container code. Report Docker execution tests separately.
Deliver the package, image digest if used, registry entry, release/PR links,
validation results, and any remaining installation or review blockers.
