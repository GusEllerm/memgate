"""memgate's command line.

    memgate serve --world world.json --registry registry.sqlite   # Hindsight with memgate's validator
    memgate check-world world.json                                 # is this world file usable?
    memgate conformance --url http://127.0.0.1:8889               # does a live deployment enforce the rules?

Settings also come from the environment: MEMGATE_WORLD, MEMGATE_REGISTRY, MEMGATE_SECRET (the shared
secret between memgate and the validator; `serve` and `conformance` need it), and for `serve` the
MEMGATE_LLM_* variables for the model Hindsight extracts memories with.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sys
from pathlib import Path

from memgate.context import HEADERS, serve_fingerprint


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


_SECRET_PARAMS = {"password", "pass", "passwd", "pwd", "sslpassword", "secret", "token", "api_key", "apikey"}


def _secret_in_query(url: str) -> bool:
    from urllib.parse import parse_qsl, urlsplit
    try:
        return any(k.lower() in _SECRET_PARAMS for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True))
    except ValueError:
        return False


def redact_db_url(url: str) -> str:
    """A database URL safe to print: any password in the user part or the query is replaced by ***."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unprintable database URL>"
    netloc = parts.netloc
    if "@" in netloc:
        userinfo, host = netloc.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{host}" if ":" in userinfo else f"{user}@{host}"
    query = parts.query
    if query:
        query = urlencode([(k, "***" if k.lower() in _SECRET_PARAMS else v) for k, v in parse_qsl(query, keep_blank_values=True)],
                          safe="*")
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def cmd_check_world(args) -> int:
    from memgate.worldcheck import check_world_file
    errors = check_world_file(args.world)
    for e in errors:
        print(f"error: {e}")
    if not errors:
        from memgate.context import load_world
        w = load_world(args.world)
        ha = sorted(l for l in w.locations if w.high_assurance(l))
        print(f"ok: {len(w.environments)} environments, {len(w.locations)} locations "
              f"({len(ha)} high assurance), {len(w.agents)} agents")
    return 1 if errors else 0


def cmd_serve(args) -> int:
    from memgate.worldcheck import check_world_file
    world = args.world or _env("MEMGATE_WORLD")
    registry = args.registry or _env("MEMGATE_REGISTRY")
    if not world or not registry:
        print("serve needs --world and --registry (or MEMGATE_WORLD and MEMGATE_REGISTRY)", file=sys.stderr)
        return 2
    errors = check_world_file(world)
    if errors:
        print("the world file has problems (memgate check-world):\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if _secret_in_query(args.db):
        print("refusing a database URL with a password in its query (e.g. ?password=...): Hindsight 0.10.1 logs "
              "the query in clear at startup. Put the password in the user part instead "
              "(postgresql://user:password@host/db), which Hindsight masks.", file=sys.stderr)
        return 2
    secret = _env("MEMGATE_SECRET")
    if args.secret_file:
        secret = Path(args.secret_file).read_text().strip()
    if not secret:
        print("serve needs the shared secret: MEMGATE_SECRET or --secret-file "
              f"(generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))')", file=sys.stderr)
        return 2
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
        print(f"refusing to bind {args.host}: the memory store should only be reachable by memgate's host "
              "(pass --allow-remote if it sits behind the host's own network controls)", file=sys.stderr)
        return 2
    binary = args.hindsight_bin or shutil.which("hindsight-api", path=str(Path(sys.executable).parent)) \
        or shutil.which("hindsight-api")
    if not binary:
        print("hindsight-api not found: install memgate with the hindsight extra (pip install 'memgate[hindsight]')",
              file=sys.stderr)
        return 2
    binary = str(Path(binary).resolve())            # before the chdir below, so a relative path still works
    Path(registry).parent.mkdir(parents=True, exist_ok=True)
    # Hindsight applies the first .env it finds walking up from its working directory, over the
    # environment. Start it in a private directory whose own .env is empty, so nothing is found.
    workdir = Path(args.workdir or Path(registry).resolve().parent / ".memgate-serve")
    workdir.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    dotenv = workdir / ".env"
    if not dotenv.exists():
        dotenv.touch(mode=0o600)
    if dotenv.stat().st_size:
        print(f"refusing to start: {dotenv} is not empty. Hindsight would load it over memgate's settings; "
              "memgate serve keeps that file empty on purpose.", file=sys.stderr)
        return 1
    env = dict(os.environ)
    forced = {
        "MEMGATE_WORLD": str(Path(world).resolve()),
        "MEMGATE_REGISTRY": str(Path(registry).resolve()),
        "MEMGATE_SECRET": secret,
        "MEMGATE_SERVE_SCOPE": args.scope,
        "MEMGATE_WORLD_CHECK_S": str(args.world_check_interval),
        "HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION": "memgate.adapters.hindsight.validator:MemgateValidator",
        "HINDSIGHT_API_EXTENSION_PASSTHROUGH_HEADERS": ",".join(HEADERS),
        "HINDSIGHT_API_DATABASE_URL": args.db,
        "HINDSIGHT_API_HOST": args.host,
        "HINDSIGHT_API_PORT": str(args.port),
        "HINDSIGHT_API_LLM_PROVIDER": args.llm_provider,
        "HINDSIGHT_API_LLM_BASE_URL": args.llm_base_url,
        "HINDSIGHT_API_LLM_API_KEY": _env("MEMGATE_LLM_API_KEY", "none"),
        "HINDSIGHT_API_LLM_MODEL": args.llm_model,
        "HINDSIGHT_API_LLM_MAX_CONCURRENT": str(args.llm_max_concurrent),
        "HINDSIGHT_API_LLM_TIMEOUT": "300",
        "HINDSIGHT_API_EMBEDDINGS_PROVIDER": "local",
        "HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL": args.embedder,
        "HINDSIGHT_API_LLM_TRACE_ENABLED": "false",     # traces would hold memory content outside the partitions
        "HINDSIGHT_API_AUDIT_LOG_ENABLED": "false",
        "HINDSIGHT_API_OTEL_TRACES_ENABLED": "false",
    }
    env.update(forced)
    env["MEMGATE_SERVE_KEYS"] = ",".join(sorted(forced))
    env["MEMGATE_SERVE_FINGERPRINT"] = serve_fingerprint(env, list(forced))
    print(f"memgate: Hindsight with the validator on http://{args.host}:{args.port} "
          f"(scope {args.scope}, database {redact_db_url(args.db)})", flush=True)
    os.chdir(workdir)
    os.execve(binary, [binary], env)
    return 0  # not reached


def cmd_conformance(args) -> int:
    from memgate.conformance import report, run
    from memgate.context import Gate
    for name in ("MEMGATE_WORLD", "MEMGATE_REGISTRY", "MEMGATE_SECRET"):
        if not _env(name):
            print(f"conformance needs {name} (the same values the server was started with)", file=sys.stderr)
            return 2
    checks = run(Gate.from_env(), args.url, wait_s=args.wait, partition_url=args.partition_url)
    if args.json:
        import json
        print(json.dumps([c.__dict__ for c in checks], indent=1))
    else:
        print(report(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0


def cmd_secret(args) -> int:
    print(secrets.token_urlsafe(32))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memgate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check-world", help="validate a world file")
    c.add_argument("world")
    c.set_defaults(func=cmd_check_world)

    s = sub.add_parser("serve", help="run Hindsight with memgate's validator (the memory store memgate talks to)")
    s.add_argument("--world")
    s.add_argument("--registry")
    s.add_argument("--secret-file", help="file holding the shared secret (else MEMGATE_SECRET)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--allow-remote", action="store_true", help="allow binding a non-loopback address")
    s.add_argument("--port", type=int, default=int(_env("MEMGATE_PORT", "8889")))
    s.add_argument("--db", default=_env("MEMGATE_DB", "pg0://memgate"),
                   help="Hindsight database URL (pg0://name is an embedded Postgres)")
    s.add_argument("--llm-provider", default=_env("MEMGATE_LLM_PROVIDER", "openai"))
    s.add_argument("--llm-base-url", default=_env("MEMGATE_LLM_BASE_URL", "http://127.0.0.1:8411/v1"))
    s.add_argument("--llm-model", default=_env("MEMGATE_LLM_MODEL", "openai/gpt-oss-120b"))
    s.add_argument("--llm-max-concurrent", type=int, default=int(_env("MEMGATE_LLM_MAX_CONCURRENT", "6")))
    s.add_argument("--embedder", default=_env("MEMGATE_EMBEDDER", "BAAI/bge-small-en-v1.5"))
    s.add_argument("--scope", choices=["all", "shared", "partitions"], default=_env("MEMGATE_SERVE_SCOPE", "all"),
                   help="which banks this server holds: all (default), shared (no high-assurance partitions), or "
                        "partitions (only them, for a separate high-assurance server)")
    s.add_argument("--world-check-interval", type=float, default=float(_env("MEMGATE_WORLD_CHECK_S", "1.0")),
                   help="seconds between checks of the world file for changes (0 = every decision)")
    s.add_argument("--workdir", default=_env("MEMGATE_SERVE_DIR"),
                   help="Hindsight's working directory (default: .memgate-serve beside the registry); it holds "
                        "an empty .env so Hindsight never loads another one")
    s.add_argument("--hindsight-bin")
    s.set_defaults(func=cmd_serve)

    k = sub.add_parser("conformance", help="check a live deployment enforces the rules (canaries, then cleans up)")
    k.add_argument("--url", default=f"http://127.0.0.1:{_env('MEMGATE_PORT', '8889')}")
    k.add_argument("--partition-url", help="the high-assurance partition server, in a split deployment")
    k.add_argument("--wait", type=float, default=900, help="seconds to wait for Hindsight's background work")
    k.add_argument("--json", action="store_true")
    k.set_defaults(func=cmd_conformance)

    g = sub.add_parser("secret", help="print a new random shared secret")
    g.set_defaults(func=cmd_secret)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
