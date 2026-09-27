# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Small standard-library rhyven.service/1 adapter. Copy into your image.

The stdin pump remains responsive while an action or background thread runs.
Applications own durable jobs and must flush their state during shutdown.
"""
import json
import queue
import signal
import sys
import threading
import uuid

MAX_FRAME = 1_048_576


class Service:
    def __init__(self, actions, start=None, stop=None):
        self.actions, self.start, self.stop = actions, start, stop
        self.context = None
        self.stopping = threading.Event()
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending = {}
        self._jobs = queue.Queue(maxsize=1)

    def send(self, value):
        raw = json.dumps(value, separators=(",", ":")) + "\n"
        if len(raw.encode()) > MAX_FRAME:
            raise ValueError("Frame exceeds 1 MiB")
        with self._write_lock:
            sys.stdout.write(raw)
            sys.stdout.flush()

    def call(self, category, function, args):
        identity = uuid.uuid4().hex
        reply = queue.Queue(maxsize=1)
        with self._pending_lock:
            if len(self._pending) >= 16:
                raise RuntimeError("Too many callbacks")
            self._pending[identity] = reply
        try:
            self.send(dict(type="callback", id=identity, category=category,
                           function=function, args=args))
            result = reply.get(timeout=10)
            if "error" in result:
                raise RuntimeError(json.dumps(result["error"]))
            return result["result"]
        finally:
            with self._pending_lock:
                self._pending.pop(identity, None)

    def _work(self):
        while not self.stopping.is_set():
            try:
                message = self._jobs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                action = self.actions[message["function"]]
                result = action(message["args"], message["context"], self)
                self.send(dict(type="response", id=message["id"], result=result))
            except Exception as error:
                self.send(dict(type="response", id=message["id"],
                               error=dict(code="app_error", message=str(error))))

    def run(self):
        def shutdown(_signal, _frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        worker = threading.Thread(target=self._work, daemon=True)
        started = False
        try:
            while True:
                line = sys.stdin.buffer.readline(MAX_FRAME + 1)
                if not line:
                    break
                if len(line) > MAX_FRAME or not line.endswith(b"\n"):
                    raise ValueError("Invalid input frame")
                message = json.loads(line)
                kind = message.get("type")
                if kind == "initialize":
                    if self.context is not None or message["protocol"] != "rhyven.service/1":
                        raise ValueError("Invalid initialization")
                    self.context = message["context"]
                    if self.start:
                        self.start(self)
                    started = True
                    worker.start()
                    self.send(dict(type="ready", protocol="rhyven.service/1"))
                elif kind == "ping":
                    self.send(dict(type="pong"))
                elif kind == "callback_result":
                    with self._pending_lock:
                        reply = self._pending.get(message["id"])
                    if reply:
                        reply.put_nowait(message)
                elif kind == "call" and self.context is not None:
                    self._jobs.put_nowait(message)
                else:
                    raise ValueError("Unknown service message")
        finally:
            self.stopping.set()
            if started and self.stop:
                self.stop(self)
