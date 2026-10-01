"""The Unix-socket transport: clients reach a server on a socket, and refuse a socket anyone else could
have created (that is how the server proves who it is: no port to squat)."""

import asyncio
import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading

import pytest

from memgate.adapters.hindsight.client import AsyncHindsightMemory, HindsightMemory, check_socket, socket_path
from memgate.context import Gate


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        _Handler.seen.append((self.path, self.headers.get("x-memgate-secret")))
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def address_string(self):
        return "unix"

    def log_message(self, *a):
        pass


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


@pytest.fixture
def server():
    d = tempfile.mkdtemp(prefix="mg", dir="/tmp")           # short: socket paths are limited to ~104 bytes
    os.chmod(d, 0o700)
    path = os.path.join(d, "memgate.sock")
    srv = _UnixHTTPServer(path, _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Handler.seen.clear()
    yield d, path
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(d, ignore_errors=True)


def test_addresses():
    assert socket_path("unix:/tmp/x/memgate.sock") == "/tmp/x/memgate.sock"
    assert socket_path("unix:///tmp/x/memgate.sock") == "/tmp/x/memgate.sock"
    assert socket_path("http://127.0.0.1:8889") is None


def test_sync_client_over_a_socket(server, world, registry):
    d, path = server
    mem = HindsightMemory(Gate(world, registry, "the-secret"), bank="b", base_url=f"unix:{path}", timeout=5)
    assert mem._call("GET", "/v1/default/banks/b/stats", None, role="admin") == {"ok": True}
    assert _Handler.seen == [("/v1/default/banks/b/stats", "the-secret")]


def test_async_client_over_a_socket(server, world, registry):
    pytest.importorskip("httpx")
    d, path = server

    async def go():
        async with AsyncHindsightMemory(Gate(world, registry, "the-secret"), bank="b", base_url=f"unix:{path}") as mem:
            return await mem._call("GET", "/v1/default/banks/b/stats", None, role="admin")
    assert asyncio.run(go()) == {"ok": True}
    assert _Handler.seen == [("/v1/default/banks/b/stats", "the-secret")]


def test_a_socket_in_a_shared_directory_is_refused(server, world, registry):
    d, path = server
    os.chmod(d, 0o755)                                      # others could have created what's in it
    mem = HindsightMemory(Gate(world, registry, "the-secret"), bank="b", base_url=f"unix:{path}", timeout=5)
    with pytest.raises(PermissionError, match="private"):
        mem._call("GET", "/v1/default/banks/b/stats", None, role="admin")
    assert _Handler.seen == []                              # the secret never left
    os.chmod(d, 0o700)


def test_something_that_is_not_a_socket_is_refused(tmp_path):
    d = tempfile.mkdtemp(prefix="mg", dir="/tmp")
    os.chmod(d, 0o700)
    fake = os.path.join(d, "memgate.sock")
    open(fake, "w").close()
    with pytest.raises(PermissionError, match="not a socket"):
        check_socket(fake)
    shutil.rmtree(d)


def test_serve_on_a_socket_runs_uvicorn_with_no_port(tmp_path, monkeypatch):
    from memgate import cli
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    fake_bin = tmp_path / "hindsight-api"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("MEMGATE_SECRET", "s")
    monkeypatch.chdir(tmp_path)
    d = tempfile.mkdtemp(prefix="mg", dir="/tmp")
    shutil.rmtree(d)                                        # serve creates it, private
    seen = {}

    def no_exec(binary, argv, env):
        seen.update(argv=argv)
        raise SystemExit(0)
    monkeypatch.setattr(cli.os, "execve", no_exec)
    with pytest.raises(SystemExit):
        cli.main(["serve", "--world", str(world), "--registry", str(tmp_path / "r.sqlite"), "--hindsight-bin", str(fake_bin),
                  "--socket", f"{d}/memgate.sock"])
    assert seen["argv"][1:5] == ["-m", "uvicorn", "hindsight_api.server:app", "--uds"]
    assert seen["argv"][5].endswith("/memgate.sock") and "--port" not in seen["argv"] and "--host" not in seen["argv"]
    assert os.stat(d).st_mode & 0o777 == 0o700
    os.chmod(d, 0o755)                                      # a shared directory: refused
    rc = cli.main(["serve", "--world", str(world), "--registry", str(tmp_path / "r.sqlite"), "--hindsight-bin", str(fake_bin),
                   "--socket", f"{d}/memgate.sock"])
    assert rc == 2
    shutil.rmtree(d)
