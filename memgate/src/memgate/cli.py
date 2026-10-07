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
    sock = None
    if args.socket:
        sock = Path(args.socket).resolve()
        if len(str(sock).encode()) > 100:
            print(f"socket path too long for the operating system ({len(str(sock))} bytes, at most 100): {sock}",
                  file=sys.stderr)
            return 2
        sock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        st = sock.parent.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            print(f"refusing to serve on {sock}: its directory must be private (0700) and owned by this user "
                  f"(it is {oct(st.st_mode & 0o777)}). The directory is what proves the server's identity to "
                  "the client.", file=sys.stderr)
            return 2
        if sock.is_socket():
            sock.unlink()                                  # a stale socket from an earlier run
        elif sock.exists():
            print(f"refusing to serve on {sock}: something that isn't a socket is there", file=sys.stderr)
            return 2
    elif args.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
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
    registry_is_url = registry.startswith(("postgresql://", "postgres://"))
    if not registry_is_url:
        Path(registry).parent.mkdir(parents=True, exist_ok=True)
    # Hindsight applies the first .env it finds walking up from its working directory, over the
    # environment. Start it in a private directory whose own .env is empty, so nothing is found.
    workdir = Path(args.workdir or (Path.cwd() / ".memgate-serve" if registry_is_url else Path(registry).resolve().parent / ".memgate-serve"))
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
        "MEMGATE_REGISTRY": registry if registry_is_url else str(Path(registry).resolve()),
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
        "HINDSIGHT_API_EMBEDDINGS_PROVIDER": args.embeddings_provider,
        "HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL": args.embedder,
        "HINDSIGHT_API_EMBEDDINGS_ONNX_MODEL_ID": args.embedder,
        # Hindsight's onnx defaults (mean pooling, E5 prefixes) suit intfloat/e5; the bge family wants CLS
        # pooling and no prefixes, so the onnx provider gives the same vectors as the local one for bge.
        "HINDSIGHT_API_EMBEDDINGS_ONNX_POOLING": "cls" if "bge" in args.embedder.lower() else "mean",
        "HINDSIGHT_API_EMBEDDINGS_ONNX_QUERY_PREFIX": "" if "bge" in args.embedder.lower() else "query: ",
        "HINDSIGHT_API_EMBEDDINGS_ONNX_PASSAGE_PREFIX": "" if "bge" in args.embedder.lower() else "passage: ",
        "HINDSIGHT_API_RERANKER_PROVIDER": args.reranker,
        "HINDSIGHT_API_LLM_TRACE_ENABLED": "false",     # traces would hold memory content outside the partitions
        "HINDSIGHT_API_AUDIT_LOG_ENABLED": "false",
        "HINDSIGHT_API_OTEL_TRACES_ENABLED": "false",
        # Hindsight logs the start of every recall query at INFO: conversation text in the server's log.
        # The validator also redacts queries from whatever is logged (RedactQueries), at any level.
        "HINDSIGHT_API_LOG_LEVEL": args.hindsight_log_level,
        "MEMGATE_SERVE_MIN_CLIENT": args.min_client_version or "",
    }
    if args.embeddings_provider == "onnx" and args.reranker == "local":
        print("memgate: --embeddings-provider onnx with --reranker local still needs torch (the local reranker is a "
              "sentence-transformers cross-encoder); use --reranker flashrank or rrf for a torch-free server", file=sys.stderr)
    if args.min_client_version:
        from memgate import __version__
        from memgate.context import release
        if release(args.min_client_version) is None or release(args.min_client_version) > release(__version__):
            print(f"--min-client-version must be a release no newer than this server ({__version__}), "
                  f"not {args.min_client_version!r}", file=sys.stderr)
            return 2
    if args.hindsight_log_level in ("info", "debug", "trace"):
        print(f"memgate: Hindsight log level {args.hindsight_log_level}: its log will hold memory and query text "
              "(queries redacted); treat it as labelled data", file=sys.stderr)
    env.update(forced)
    env["MEMGATE_SERVE_KEYS"] = ",".join(sorted(forced))
    env["MEMGATE_SERVE_FINGERPRINT"] = serve_fingerprint(env, list(forced))
    where = f"unix:{sock}" if sock else f"http://{args.host}:{args.port}"
    print(f"memgate: Hindsight with the validator on {where} "
          f"(scope {args.scope}, database {redact_db_url(args.db)})", flush=True)
    os.chdir(workdir)
    if sock:
        # Hindsight's own launcher has no socket option; its ASGI app under uvicorn is the documented
        # alternative (and what it runs itself with several workers). No TCP port is opened.
        python = Path(binary).parent / "python"
        python = str(python) if python.exists() else sys.executable
        os.execve(python, [python, "-m", "uvicorn", "hindsight_api.server:app", "--uds", str(sock), "--ws", "wsproto",
                           "--timeout-keep-alive", "30", "--timeout-graceful-shutdown", "5"], env)
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


def _memory(args):
    """A HindsightMemory for the operator commands, from the same settings the host uses."""
    from memgate.adapters.hindsight import HindsightMemory
    from memgate.context import Gate
    for name in ("MEMGATE_WORLD", "MEMGATE_REGISTRY", "MEMGATE_SECRET"):
        if not _env(name):
            print(f"this command needs {name} (the same values the server was started with)", file=sys.stderr)
            return None
    if not args.bank:
        print("this command needs --bank (or MEMGATE_BANK): the host's shared partition name", file=sys.stderr)
        return None
    return HindsightMemory(Gate.from_env(), bank=args.bank, base_url=args.url, partition_url=args.partition_url, check_version=True)


def cmd_inspect(args) -> int:
    """What memgate holds for an agent (or the deployment): counts, timestamps, and the agent's personal items."""
    import json
    mem = _memory(args)
    if mem is None:
        return 2
    out = {"handshake": mem.check_version(), "capabilities": mem.capabilities.__dict__, "stats": mem.stats(args.agent)}
    personal = mem.personal(args.agent) if args.agent else []
    if args.agent:
        out["personal"] = [{**i.__dict__, **({} if args.text else {"text": f"({len(i.text)} chars; --text shows it)"})} for i in personal]
    if args.json:
        print(json.dumps(out, indent=1, default=str))
        return 0
    for part, st in out["stats"].items():
        if not st.get("exists", True):
            print(f"{part}: (no such partition yet)")
            continue
        print(f"{part}: pending {st.get('pending', 0)}, last consolidation {st.get('last_consolidation') or '-'}")
        for ls, c in (st.get("label_sets") or {}).items():
            print(f"  {ls}: {c['memories']} memories, {c['observations']} observations, {c['documents']} writes, last {c['last_write'] or '-'}")
    if args.agent:
        print(f"{args.agent}'s personal memory ({len(personal)} items" + ("" if args.text else "; --text shows the text") + "):")
        known = mem.gate.registry.all()
        for i in personal:
            cls = known[i.label_set].classes if i.label_set in known else set()
            tag = f" [{', '.join(sorted(cls))}]" if cls else ""
            body = i.text[:160] if args.text else f"({len(i.text)} chars)"
            print(f"  {i.write_id}  {i.when or '-'}{tag}  {i.kind}: {body}")
    return 0


def cmd_attach_sources(args) -> int:
    """Give personal items carried out before 0.7.0 their source location, from a host-supplied mapping
    {write_id: location} (e.g. CHORUS's lineage table). Each item is re-written under {self:A, class?, src:S}
    with the same text, as a write made at S, and the unsourced copy is forgotten. The source seal then
    applies to it like any other carry-out."""
    import json
    mem = _memory(args)
    if mem is None:
        return 2
    mapping = json.loads(Path(args.mapping).read_text())
    if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
        print("the mapping must be a JSON object {write_id: location}", file=sys.stderr)
        return 2
    done, skipped = 0, []
    for old_id, src in mapping.items():
        try:
            n = mem.attach_source(args.agent, old_id, src, dry_run=args.dry_run)
        except (PermissionError, KeyError, ValueError) as e:
            skipped.append(f"{old_id}: {e}")
            continue
        done += n
    for line in skipped:
        print(f"skipped {line}", file=sys.stderr)
    print(f"{'would attach' if args.dry_run else 'attached'} sources to {done} write(s); {len(skipped)} skipped")
    return 0 if not skipped else 1


def cmd_inspect_location(args) -> int:
    """A location's view (0.8.0): every item in its conversation sets, with participants; agents' notes are not shown."""
    import json
    mem = _memory(args)
    if mem is None:
        return 2
    try:
        items = mem.location(args.location)
    except KeyError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([{**i.__dict__, **({} if args.text else {"text": f"({len(i.text)} chars; --text shows it)"})} for i in items],
                         indent=1, default=str))
        return 0
    print(f"{args.location}'s memory ({len(items)} items" + ("" if args.text else "; --text shows the text") + "):")
    for i in items:
        body = i.text[:160] if args.text else f"({len(i.text)} chars)"
        print(f"  {i.write_id}  {i.when or '-'} [{', '.join(i.participants)}]  {i.kind}: {body}")
    return 0


def cmd_forget_location(args) -> int:
    """Delete a location's memory (0.8.0): its conversation sets with what was derived from them, and the private
    notes bound to it. The tree owner's request, relayed by the host."""
    mem = _memory(args)
    if mem is None:
        return 2
    if not args.yes:
        print("forget-location is a hard delete of everything the place remembers; add --yes to confirm", file=sys.stderr)
        return 2
    try:
        counts = mem.forget_location(args.location)
    except KeyError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    print(f"forgotten at {args.location}: {counts['writes']} write(s) in {counts['sets']} conversation set(s), "
          f"{counts['derived']} derived item(s), {counts['notes']} note(s)")
    return 0


def cmd_forget(args) -> int:
    """Delete one item of an agent's personal memory by write ID (the owner's request, relayed by the host)."""
    mem = _memory(args)
    if mem is None:
        return 2
    if not args.yes:
        print("forget is a hard delete; add --yes to confirm", file=sys.stderr)
        return 2
    try:
        existed = mem.forget(args.agent, args.write_id)
    except PermissionError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as e:                   # HindsightError, VersionMismatch, connection errors
        print(f"failed: {e}", file=sys.stderr)
        return 1
    print(f"{'forgotten' if existed else 'not found'}: {args.write_id}")
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
    s.add_argument("--socket", default=_env("MEMGATE_SOCKET"),
                   help="serve on this Unix socket instead of a port (its directory must be private, 0700); "
                        "clients then use the address unix:<path>")
    s.add_argument("--port", type=int, default=int(_env("MEMGATE_PORT", "8889")))
    s.add_argument("--db", default=_env("MEMGATE_DB", "pg0://memgate"),
                   help="Hindsight database URL (pg0://name is an embedded Postgres)")
    s.add_argument("--llm-provider", default=_env("MEMGATE_LLM_PROVIDER", "openai"))
    s.add_argument("--llm-base-url", default=_env("MEMGATE_LLM_BASE_URL", "http://127.0.0.1:8411/v1"))
    s.add_argument("--llm-model", default=_env("MEMGATE_LLM_MODEL", "openai/gpt-oss-120b"))
    s.add_argument("--llm-max-concurrent", type=int, default=int(_env("MEMGATE_LLM_MAX_CONCURRENT", "6")))
    s.add_argument("--embedder", default=_env("MEMGATE_EMBEDDER", "BAAI/bge-small-en-v1.5"),
                   help="the embedding model (a sentence-transformers model for the local provider, a Hugging Face "
                        "repo with an onnx/model.onnx export for onnx)")
    s.add_argument("--embeddings-provider", choices=["local", "onnx"], default=_env("MEMGATE_EMBEDDINGS_PROVIDER", "local"),
                   help="local (sentence-transformers, needs torch) or onnx (onnxruntime, no torch; the slim image)")
    s.add_argument("--reranker", choices=["local", "rrf", "flashrank"], default=_env("MEMGATE_RERANKER", "local"),
                   help="Hindsight's reranker: local (a cross-encoder, needs torch), rrf (no reranking: retrieval "
                        "order as is) or flashrank (a small ONNX reranker, no torch)")
    s.add_argument("--scope", choices=["all", "shared", "partitions"], default=_env("MEMGATE_SERVE_SCOPE", "all"),
                   help="which banks this server holds: all (default), shared (no high-assurance partitions), or "
                        "partitions (only them, for a separate high-assurance server)")
    s.add_argument("--world-check-interval", type=float, default=float(_env("MEMGATE_WORLD_CHECK_S", "1.0")),
                   help="seconds between checks of the world file for changes (0 = every decision)")
    s.add_argument("--workdir", default=_env("MEMGATE_SERVE_DIR"),
                   help="Hindsight's working directory (default: .memgate-serve beside the registry); it holds "
                        "an empty .env so Hindsight never loads another one")
    s.add_argument("--hindsight-log-level", choices=["critical", "error", "warning", "info", "debug", "trace"],
                   default=_env("MEMGATE_HINDSIGHT_LOG_LEVEL", "warning"),
                   help="Hindsight's log level (default warning: at info and below Hindsight logs memory and "
                        "query text, which is labelled data)")
    s.add_argument("--min-client-version", default=_env("MEMGATE_SERVE_MIN_CLIENT"),
                   help="refuse clients older than this memgate release, or sending no version (catches stale "
                        "workers); clients newer than the server are always refused")
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

    for name, fn, help_ in (("inspect", cmd_inspect, "counts, timestamps and an agent's personal items (admin; never agents)"),
                            ("forget", cmd_forget, "delete one item of an agent's personal memory by write id (hard delete)"),
                            ("inspect-location", cmd_inspect_location, "list a location's conversation memory, with participants (0.8.0)"),
                            ("forget-location", cmd_forget_location, "delete a location's conversation memory and the notes bound to it (hard delete, 0.8.0)"),
                            ("attach-sources", cmd_attach_sources,
                             "give pre-0.7.0 personal items their source location from a {write_id: location} JSON file (re-writes each, forgets the old copy)")):
        o = sub.add_parser(name, help=help_)
        if name.endswith("-location"):
            o.add_argument("location")
        else:
            o.add_argument("agent", nargs="?" if name == "inspect" else None)
        if name == "forget-location":
            o.add_argument("--yes", action="store_true", help="confirm the hard delete")
        elif name == "forget":
            o.add_argument("write_id")
            o.add_argument("--yes", action="store_true", help="confirm the hard delete")
        elif name == "attach-sources":
            o.add_argument("mapping", help="JSON file: {write_id: source location}")
            o.add_argument("--dry-run", action="store_true", help="report what would be re-written, write nothing")
        elif name in ("inspect", "inspect-location"):
            o.add_argument("--json", action="store_true")
            o.add_argument("--text", action="store_true", help="show the items' text (memory text is labelled data: off by default)")
        o.add_argument("--url", default=_env("MEMGATE_URL", f"http://127.0.0.1:{_env('MEMGATE_PORT', '8889')}"))
        o.add_argument("--partition-url", help="the high-assurance partition server, in a split deployment")
        o.add_argument("--bank", default=_env("MEMGATE_BANK"), help="the host's shared partition name")
        o.set_defaults(func=fn)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
