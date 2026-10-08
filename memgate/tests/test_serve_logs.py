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


def test_serve_starts_on_an_empty_world_and_follows_it_when_it_fills():
    """0.8.2: a fresh deployment writes a world that lists no locations and no agents. serve starts on it and is
    healthy, refuses an unlisted agent by both locks, and picks up the populated world when the host rewrites the
    file, with no restart. No LLM: Hindsight runs without extraction (provider none)."""
    import json
    import shutil
    import tempfile
    import time
    from memgate.adapters.hindsight import HindsightMemory
    from memgate.adapters.hindsight.client import send
    from memgate.conformance import run
    from memgate.context import Context, Gate, load_world
    from memgate.registry import Registry
    base = tempfile.mkdtemp(prefix="mge", dir="/tmp")
    world = os.path.join(base, "world.json")
    spec = {"agents": [], "locations": [], "environments": [{"id": "open"}], "classes": [{"id": "unattributed", "consolidate": False}]}

    def write_world():
        tmp = world + ".tmp"
        with open(tmp, "w") as f:
            json.dump(spec, f)
        os.replace(tmp, world)
    write_world()
    registry = os.path.join(base, "registry.sqlite")
    env = dict(os.environ, MEMGATE_WORLD=world, MEMGATE_REGISTRY=registry, MEMGATE_SECRET="empty-secret",
               MEMGATE_DB=f"pg0://memgate-emptyworld-{os.getpid()}", MEMGATE_LLM_PROVIDER="none", MEMGATE_LLM_API_KEY="none",
               MEMGATE_WORLD_CHECK_S="0.5")
    memgate = Path(sys.executable).parent / "memgate"
    sock = os.path.join(base, "run", "memgate.sock")
    proc = subprocess.Popen([str(memgate), "serve", "--socket", sock], cwd=base, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(240):
            if os.path.exists(sock):
                break
            if proc.poll() is not None:
                pytest.fail("serve exited on an empty world: " + proc.stdout.read()[-2000:])
            time.sleep(1)
        else:
            pytest.fail("no socket")
        time.sleep(3)
        status, _ = send(f"unix:{sock}", "GET", "/health", None, {}, 10)
        assert status == 200
        gate = Gate(load_world(world), Registry(registry), "empty-secret", world_path=world, check_every=0.5)
        checks = {c.id: c for c in run(gate, f"unix:{sock}", wait_s=60)}
        assert checks["secret"].status == "pass" and checks["unlisted-refused"].status == "pass", checks["unlisted-refused"].detail
        assert not [c.id for c in checks.values() if c.status == "fail"]
        mem = HindsightMemory(gate, bank="emptyworld", base_url=f"unix:{sock}", check_version=True)
        with pytest.raises(PermissionError):
            mem.remember(Context("ada", "lab", ("ada",)), "too early")
        spec.update(locations=[{"id": "lab", "environment": "open"}], agents=["ada"])   # the host plants the first tree
        write_world()
        deadline, stored = time.time() + 30, None
        while time.time() < deadline and stored is None:
            try:
                stored = mem.remember(Context("ada", "lab", ("ada",)), "the first tree's first memory is kiln nine")
            except PermissionError:
                time.sleep(0.5)
        assert stored, "the populated world was not picked up"
        deadline = time.time() + 120
        while mem.pending_operations() and time.time() < deadline:
            time.sleep(1)
        assert any("kiln nine" in r.text for r in mem.recall(Context("ada", "lab", ("ada",)), "kiln nine"))
        assert proc.poll() is None                                                        # never restarted
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(Path.home() / ".pg0" / "instances" / f"memgate-emptyworld-{os.getpid()}", ignore_errors=True)   # ~50 MB each
