# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Build-time only: verify pinned upstream archives before installing language servers."""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import tarfile
import tempfile
import urllib.request

locks=json.loads(Path('/build/toolchains.json').read_text())
arch={'x86_64':'x86_64','aarch64':'aarch64'}[platform.machine()]
for entry in locks:
    if 'rust-analyzer-' in entry['url'] and f'rust-analyzer-{arch}-' not in entry['url']: continue
    with urllib.request.urlopen(entry['url'],timeout=120) as response: data=response.read()
    assert hashlib.sha256(data).hexdigest()==entry['sha256'],'Toolchain checksum mismatch'
    if 'rust-analyzer-' in entry['url']:
        path=Path('/usr/local/bin/rust-analyzer');path.write_bytes(gzip.decompress(data));path.chmod(0o755)
    else:
        Path('/opt/jdtls').mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile() as f:
            f.write(data);f.flush()
            with tarfile.open(f.name) as archive: archive.extractall('/opt/jdtls',filter='data')
