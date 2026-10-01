"""memgate serve, end to end with Hindsight: a database password never reaches the output, even when
the database can't be reached. Needs Hindsight installed (run in its environment); starts a real
server against an unreachable Postgres and reads everything it prints."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("hindsight_api")

SENTINEL = "SENTINELpw9731"


def test_a_failed_database_connection_never_prints_the_password(tmp_path):
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    env = dict(os.environ, MEMGATE_WORLD=str(world), MEMGATE_REGISTRY=str(tmp_path / "r.sqlite"), MEMGATE_SECRET="s",
               MEMGATE_DB=f"postgresql://memgate:{SENTINEL}@127.0.0.1:1/memgate", MEMGATE_LLM_API_KEY="none",
               MEMGATE_LLM_BASE_URL="http://127.0.0.1:9/v1")
    memgate = Path(sys.executable).parent / "memgate"
    try:
        run = subprocess.run([str(memgate), "serve", "--port", "18896"], env=env, capture_output=True, text=True, timeout=120)
        output = run.stdout + run.stderr
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or b"").decode(errors="replace") + (e.stderr or b"").decode(errors="replace")
    assert "memgate: Hindsight with the validator" in output          # it really started
    assert SENTINEL not in output


def test_a_hostile_env_file_cannot_disable_the_validator(tmp_path):
    """A .env where serve is started (and above Hindsight's working directory) tries to drop the validator
    and swap the secret. memgate serve starts Hindsight in a private dir with an empty .env, so it can't."""
    import time
    import urllib.error
    import urllib.request
    hostile = ("HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=\nMEMGATE_SECRET=evil\n"
               "HINDSIGHT_API_LLM_TRACE_ENABLED=true\n")
    (tmp_path / ".env").write_text(hostile)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".env").write_text(hostile)                  # directly above the workdir
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    env = dict(os.environ, MEMGATE_WORLD=str(world), MEMGATE_REGISTRY=str(tmp_path / "data" / "r.sqlite"),
               MEMGATE_SECRET="the-real-secret", MEMGATE_DB=f"pg0://memgate-envtest-{os.getpid()}",
               MEMGATE_LLM_API_KEY="gateway", MEMGATE_LLM_BASE_URL=os.environ.get("MEMGATE_LLM_BASE_URL", "http://127.0.0.1:8411/v1"))
    memgate = Path(sys.executable).parent / "memgate"
    proc = subprocess.Popen([str(memgate), "serve", "--port", "18897"], cwd=tmp_path, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(180):
            try:
                urllib.request.urlopen("http://127.0.0.1:18897/health", timeout=2)
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail("serve exited: " + proc.stdout.read()[-2000:])
                time.sleep(1)
        else:
            pytest.fail("serve did not come up")

        def status(headers):
            req = urllib.request.Request("http://127.0.0.1:18897/v1/default/banks", headers=headers)
            try:
                return urllib.request.urlopen(req, timeout=10).status
            except urllib.error.HTTPError as e:
                return e.code
        req = urllib.request.Request("http://127.0.0.1:18897/v1/default/banks/x", method="PUT", data=b'{"name":"x"}',
                                     headers={"Content-Type": "application/json"})
        try:
            code = urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 403                                   # the validator is loaded: no secret, refused
        req = urllib.request.Request("http://127.0.0.1:18897/v1/default/banks/x", method="PUT", data=b'{"name":"x"}',
                                     headers={"Content-Type": "application/json", "x-memgate-secret": "evil",
                                              "x-memgate-role": "admin"})
        try:
            code = urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 403                                   # and the hostile secret is not the one in force
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_conformance_over_a_unix_socket():
    """memgate serve --socket with a real Hindsight: no port, and every conformance check passes over the socket."""
    import json
    import shutil
    import tempfile
    import time
    from memgate.conformance import run
    from memgate.context import Gate, load_world
    from memgate.registry import Registry
    base = tempfile.mkdtemp(prefix="mgs", dir="/tmp")            # short path: socket paths are limited
    sock_dir = os.path.join(base, "run")
    world = os.path.join(base, "world.json")
    with open(world, "w") as f:
        json.dump({"environments": [{"id": "campus"}, {"id": "studio", "carry_out": ["opinion", "skill"]}],
                   "locations": [{"id": "lab", "environment": "campus"}, {"id": "cafe", "environment": "campus"},
                                 {"id": "gallery", "environment": "studio"},
                                 {"id": "vault", "environment": "campus", "high_assurance": True}],
                   "agents": ["ada", "bo", "cy"]}, f)
    registry = os.path.join(base, "registry.sqlite")
    env = dict(os.environ, MEMGATE_WORLD=world, MEMGATE_REGISTRY=registry, MEMGATE_SECRET="socket-secret",
               MEMGATE_DB=f"pg0://memgate-socktest-{os.getpid()}", MEMGATE_LLM_API_KEY="gateway",
               MEMGATE_LLM_BASE_URL=os.environ.get("MEMGATE_LLM_BASE_URL", "http://127.0.0.1:8411/v1"))
    memgate = Path(sys.executable).parent / "memgate"
    sock = os.path.join(sock_dir, "memgate.sock")
    proc = subprocess.Popen([str(memgate), "serve", "--socket", sock], cwd=base, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(240):
            if os.path.exists(sock):
                break
            if proc.poll() is not None:
                pytest.fail("serve exited: " + proc.stdout.read()[-2000:])
            time.sleep(1)
        else:
            pytest.fail("no socket")
        time.sleep(3)
        assert os.stat(sock_dir).st_mode & 0o777 == 0o700
        checks = run(Gate(load_world(world), Registry(registry), "socket-secret"), f"unix:{sock}", wait_s=600)
        failed = [c.__dict__ for c in checks if c.status == "fail"]
        assert not failed, failed
        assert sum(c.status == "pass" for c in checks) >= 13
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(base, ignore_errors=True)
