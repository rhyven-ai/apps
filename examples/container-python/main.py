# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""One request on stdin, one response on stdout. Dependencies: Python stdlib."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def handle(request):
    if request["protocol"] != "rhyven.container/1" or request["function"] != "action_analyze":
        return {"error": {"code": "unknown_function", "message": "Unsupported request"}}
    text = request["args"]["text"]
    data = Path(os.environ["RHYVEN_DATA_DIR"])
    path = data / "counter.json"
    calls = json.loads(path.read_text())["calls"] + 1 if path.exists() else 1
    with tempfile.NamedTemporaryFile(mode="w", dir=data, delete=False) as stream:
        json.dump({"calls": calls}, stream)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    os.replace(temporary, path)
    return {"result": {"words": len(text.split()), "sha256": hashlib.sha256(text.encode()).hexdigest(), "calls": calls}}


if __name__ == "__main__":
    try:
        print(json.dumps(handle(json.loads(sys.stdin.readline()))))
    except Exception:
        print(json.dumps({"error": {"code": "failed", "message": "Text analysis failed"}}))
