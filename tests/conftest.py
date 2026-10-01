"""Shared fixtures: the jig on sys.path, and a loopback HTTP server standing in for Jev.

The stub is a real ``http.server`` on 127.0.0.1, so every test drives the jig's real httpx2 client
over real HTTP; only the remote service is stood in for.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "jev-judge" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

Reply = tuple[int, Any, dict[str, str]]


@dataclass
class JevStub:
    """What the loopback Jev saw, and how it answers the n-th request (1-based)."""

    url: str = ""
    seen: list[dict[str, Any]] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    reply: Callable[[dict[str, Any], int], Reply] = lambda body, n: (500, {}, {})
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, body: dict[str, Any], headers: dict[str, str]) -> int:
        with self._lock:
            self.seen.append(body)
            self.headers.append(headers)
            return len(self.seen)


def _handler_for(stub: JevStub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # http.server dispatches on this exact name
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            n = stub.record(body, {k.lower(): v for k, v in self.headers.items()})
            status, payload, extra = stub.reply(body, n)
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for name, value in extra.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler


@pytest.fixture
def jev() -> Iterator[JevStub]:
    stub = JevStub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(stub))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                              daemon=True)
    thread.start()
    stub.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield stub
    server.shutdown()
    server.server_close()
