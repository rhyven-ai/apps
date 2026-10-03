# SPDX-License-Identifier: Apache-2.0
"""One JSON action per process; data survives in the selected collection."""
import hashlib
import json
import os
from pathlib import Path
import sys

request = json.loads(sys.stdin.readline())
if request['protocol'] != 'rhyven.action/1' or request['function'] != 'action_analyze':
    raise ValueError('Unsupported action protocol')
text = request['args']['text']
counter = Path(os.environ['RHYVEN_DATA_DIR']) / 'calls.json'
calls = json.loads(counter.read_text()) + 1 if counter.exists() else 1
temporary = counter.with_suffix('.tmp')
temporary.write_text(json.dumps(calls))
temporary.replace(counter)
print(json.dumps({'result': {'words': len(text.split()), 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'calls': calls}}))
