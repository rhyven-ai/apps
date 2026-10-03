# SPDX-License-Identifier: Apache-2.0
"""Create a source directory for the native variant using the same action schemas."""
import argparse
import json
from pathlib import Path
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--environment', choices=['isolated', 'shared'], default='isolated')
args = parser.parse_args()
source = Path(__file__).resolve().parent
package = json.loads((source / 'app.json').read_text())
package['version'] = '0.2.0'
package['execution'] = {
    'driver': 'script', 'protocol': 'rhyven.action/1', 'language': 'python',
    'entrypoint': 'main.py', 'python_version': '3.10', 'node_version': '22.0',
    'environment': args.environment, 'dependencies': {'npm': 'package-lock.json'},
    'timeout_seconds': 300,
}
package['permissions'] = ['state.read', 'state.write', 'host.execute']
package['files'] = ['main.py', 'atlas.py', 'lsp.py', 'package.json', 'package-lock.json', 'LICENSE', 'NOTICE', 'THIRD_PARTY.md']
package['description'] += ' Native Python variant with managed Pyright and JS/TS servers.'
package['guide'] += '\nNative variant: host.execute grants unsandboxed access as the runtime OS user. Python and Node are required on PATH. Rhyven installs locked Pyright/TypeScript dependencies. Other language servers must already be installed; survey reports availability. Repository imports and summaries use the same actions as the container variant.'
args.out.mkdir(parents=True, exist_ok=False)
for name in package['files']:
    shutil.copyfile(source / name, args.out / name)
(args.out / 'app.json').write_text(json.dumps(package, indent=2) + '\n')
print(args.out)
