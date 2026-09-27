# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Persistent background counter and scoped Project Knowledge callback example."""
import json
import os
from pathlib import Path
import threading
import time
import uuid

from rhyven_service import Service

data = Path(os.environ.get("RHYVEN_DATA_DIR", "/data"))
lock = threading.Lock()
state = {}
thread = None


def save():
    path = data / "counter.tmp"
    with path.open("w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    path.replace(data / "counter.json")
    descriptor = os.open(data, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def start(service):
    global thread
    path = data / "counter.json"
    state.update(json.loads(path.read_text()) if path.exists() else
                 dict(ticks=0, calls=0, boots=0))
    state["boots"] += 1
    save()

    def tick():
        while not service.stopping.wait(.25):
            with lock:
                state["ticks"] += 1
                save()

    thread = threading.Thread(target=tick, daemon=True)
    thread.start()


def stop(service):
    if thread:
        thread.join(timeout=2)
    with lock:
        save()


def status(args, context, service):
    with lock:
        return dict(state)


def increment(args, context, service):
    with lock:
        state["calls"] += args["amount"]
        save()
        return dict(state)


def remember(args, context, service):
    request = context.get("request_id") or uuid.uuid4().hex
    result = service.call("rhyven/project-knowledge", "action_remember", {
        "title": args["title"], "body": args["body"], "topic": "service-demo",
        "request_id": "service-note-" + request[:100],
    })
    return {"note_id": result["id"]}


def health(args, context, service):
    return {"ok": True}


if __name__ == "__main__":
    Service({"action_status": status, "action_increment": increment,
             "action_remember": remember, "action_health": health},
            start=start, stop=stop).run()
