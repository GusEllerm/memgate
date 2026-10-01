"""The command line never prints a secret."""

import pytest

from memgate import cli

SECRETS = ("hunter2", "s3cr%40t", "tok123")


@pytest.mark.parametrize("url,shown", [
    ("pg0://memgate", "pg0://memgate"),
    ("postgresql://memgate:hunter2@db:5432/memgate", "postgresql://memgate:***@db:5432/memgate"),
    ("postgresql://memgate@db/memgate", "postgresql://memgate@db/memgate"),
    ("postgresql://memgate:s3cr%40t@db/memgate", "postgresql://memgate:***@db/memgate"),
    ("postgresql://db/memgate?user=memgate&password=hunter2&sslmode=require",
     "postgresql://db/memgate?user=memgate&password=***&sslmode=require"),
    ("postgresql://u:p@db/m?sslpassword=tok123", "postgresql://u:***@db/m?sslpassword=***"),
])
def test_database_urls_are_redacted(url, shown):
    assert cli.redact_db_url(url) == shown
    assert not any(s in cli.redact_db_url(url) for s in SECRETS)


def test_serve_does_not_print_the_database_password(tmp_path, monkeypatch, capsys):
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    fake_bin = tmp_path / "hindsight-api"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("MEMGATE_SECRET", "not-printed-either")
    monkeypatch.setenv("MEMGATE_DB", "postgresql://memgate:hunter2@db:5432/memgate?sslmode=require")

    def no_exec(binary, argv, env):
        assert "hunter2" in env["HINDSIGHT_API_DATABASE_URL"]                # the child still gets the real URL
        raise SystemExit(0)
    monkeypatch.setattr(cli.os, "execve", no_exec)
    monkeypatch.chdir(tmp_path)                 # serve changes directory before starting Hindsight; restore it after
    # --db's default is read from MEMGATE_DB when the parser is built, so build it after setting the env.
    with pytest.raises(SystemExit):
        cli.main(["serve", "--world", str(world), "--registry", str(tmp_path / "r.sqlite"),
                  "--hindsight-bin", str(fake_bin)])
    out = capsys.readouterr()
    assert "hunter2" not in out.out + out.err and "not-printed-either" not in out.out + out.err
    assert "postgresql://memgate:***@db:5432/memgate" in out.out


def test_serve_refuses_a_password_in_the_query(tmp_path, monkeypatch, capsys):
    """Hindsight 0.10.1 logs a URL's query in clear, so serve won't pass one carrying a password."""
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    monkeypatch.setenv("MEMGATE_SECRET", "s")
    monkeypatch.setattr(cli.os, "execve", lambda *a: pytest.fail("must not start Hindsight"))
    rc = cli.main(["serve", "--world", str(world), "--registry", str(tmp_path / "r.sqlite"),
                   "--db", "postgresql://db/memgate?user=memgate&password=hunter2"])
    out = capsys.readouterr()
    assert rc == 2 and "user part" in out.err and "hunter2" not in out.out + out.err


def test_help_never_shows_the_database_url(monkeypatch, capsys):
    monkeypatch.setenv("MEMGATE_DB", "postgresql://memgate:hunter2@db/memgate")
    with pytest.raises(SystemExit):
        cli.main(["serve", "--help"])
    assert "hunter2" not in capsys.readouterr().out


def _serve(tmp_path, monkeypatch, extra=()):
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    fake_bin = tmp_path / "hindsight-api"
    fake_bin.write_text("#!/bin/sh\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("MEMGATE_SECRET", "s")
    seen = {}

    def no_exec(binary, argv, env):
        import os
        seen.update(cwd=os.getcwd(), env=env)
        raise SystemExit(0)
    monkeypatch.setattr(cli.os, "execve", no_exec)
    monkeypatch.chdir(tmp_path)
    try:
        rc = cli.main(["serve", "--world", str(world), "--registry", str(tmp_path / "data" / "r.sqlite"),
                       "--hindsight-bin", str(fake_bin), *extra])
    except SystemExit:
        rc = None
    return rc, seen


def test_serve_starts_hindsight_in_a_private_dir_with_an_empty_env(tmp_path, monkeypatch):
    import os
    import stat
    (tmp_path / ".env").write_text("HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=\n")   # a hostile .env where serve is run
    rc, seen = _serve(tmp_path, monkeypatch)
    workdir = tmp_path / "data" / ".memgate-serve"
    assert os.path.realpath(seen["cwd"]) == os.path.realpath(workdir)
    assert (workdir / ".env").read_text() == ""
    assert stat.S_IMODE(workdir.stat().st_mode) == 0o700 and stat.S_IMODE((workdir / ".env").stat().st_mode) == 0o600
    from memgate.context import serve_fingerprint
    keys = seen["env"]["MEMGATE_SERVE_KEYS"].split(",")
    assert "HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION" in keys and "MEMGATE_SECRET" in keys
    assert serve_fingerprint(seen["env"], keys) == seen["env"]["MEMGATE_SERVE_FINGERPRINT"]


def test_serve_refuses_a_non_empty_env_in_its_workdir(tmp_path, monkeypatch, capsys):
    workdir = tmp_path / "data" / ".memgate-serve"
    workdir.mkdir(parents=True)
    (workdir / ".env").write_text("HINDSIGHT_API_LLM_TRACE_ENABLED=true\n")
    rc, seen = _serve(tmp_path, monkeypatch)
    assert rc == 1 and not seen and "not empty" in capsys.readouterr().err


def test_serve_resolves_a_relative_hindsight_bin_before_changing_directory(tmp_path, monkeypatch):
    import os
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin" / "hindsight-api"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    world = tmp_path / "world.json"
    world.write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    monkeypatch.setenv("MEMGATE_SECRET", "s")
    monkeypatch.chdir(tmp_path)
    seen = {}

    def no_exec(binary, argv, env):
        seen["binary"] = binary
        raise SystemExit(0)
    monkeypatch.setattr(cli.os, "execve", no_exec)
    with pytest.raises(SystemExit):
        cli.main(["serve", "--world", "world.json", "--registry", "data/r.sqlite", "--hindsight-bin", "bin/hindsight-api"])
    assert os.path.isabs(seen["binary"]) and os.path.exists(seen["binary"])


def test_serve_keeps_hindsight_quiet_about_memory_text(tmp_path, monkeypatch, capsys):
    """Hindsight logs recall queries at INFO; serve forces WARNING (fingerprinted, so a .env can't raise it)."""
    _, seen = _serve(tmp_path, monkeypatch)
    assert seen["env"]["HINDSIGHT_API_LOG_LEVEL"] == "warning"
    assert "HINDSIGHT_API_LOG_LEVEL" in seen["env"]["MEMGATE_SERVE_KEYS"].split(",")
    assert "labelled data" not in capsys.readouterr().err
    _, seen = _serve(tmp_path, monkeypatch, ("--hindsight-log-level", "info"))
    assert seen["env"]["HINDSIGHT_API_LOG_LEVEL"] == "info"
    assert "labelled data" in capsys.readouterr().err                   # asked for, and said out loud
