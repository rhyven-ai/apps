# Third-party components

Apache-2.0 covers the Rhyven-authored files in this repository. It does not
relicense dependencies installed by the Dockerfiles, downloaded toolchains, or
operating-system packages. Preserve their own copyright and license notices.

The Messaging app and small examples use Python's standard library. Their base
images include Python and Alpine components under their respective licenses.

The documentation image additionally installs Ubuntu packages, Node.js, Pyright,
TypeScript, TypeScript Language Server, fortls, clangd, gopls, Rust tooling and
Eclipse JDT LS. `package-lock.json` and `toolchains.json` identify pinned direct
downloads; distro package versions are resolved at image build time. The complete
component inventory therefore comes from the exact built image, not just these
source files.

Before redistributing a built image:

1. Inventory the exact image and all layers, including OS packages and transitive
   language dependencies; retain the upstream license files and attribution.
2. Satisfy corresponding-source and notice requirements for components whose
   licenses require them. An Apache-2.0 app license does not remove those duties.
3. Scan the image for vulnerabilities and credentials; keep a report tied to its
   immutable digest. Review any exceptions against that exact image.
4. Publish only tested digests and supported architectures. Do not claim that
   publication of this repository certifies a particular image's compliance.

The Rhyven engine is not bundled in these Dockerfiles. It remains separately
licensed and is not covered by this repository's Apache-2.0 grant.
