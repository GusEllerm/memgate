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
