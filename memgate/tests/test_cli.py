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
