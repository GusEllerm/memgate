"""Local OpenAI-compatible gateway to the ALCF inference service.

Every memory system, benchmark script and judge points its OpenAI base URL at
this gateway instead of at ALCF. The gateway:

- caps concurrent upstream requests at 6 across everything we run (the limit
  agreed for the shared endpoint; lower values are allowed, higher are refused);
- routes each request to the ALCF cluster that serves its model;
- injects a current Globus token, refreshing it on expiry or a 401;
- retries transient upstream failures (502/503/504, connection errors) with
  backoff, releasing its slot while it waits;
- writes one JSON line per request (run, system, model, status, attempts,
  queue wait, upstream time, token usage) for cost and reproducibility.

Run it with:

    uv run smbench-gateway            # listens on http://127.0.0.1:8411/v1

Clients may send any API key. Optional headers X-Run-Id and X-System label the
request in the log; they are not forwarded upstream.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from aiohttp import ClientError, ClientSession, ClientTimeout, web

MAX_CONCURRENCY = 6

ALCF = "https://inference-api.alcf.anl.gov/resource_server"
ROUTES: dict[str, str] = {
    "openai/gpt-oss-120b": f"{ALCF}/sophia/vllm/v1",
    "openai/gpt-oss-20b": f"{ALCF}/sophia/vllm/v1",
    "nvidia/nemotron-3-super-120b": f"{ALCF}/sophia/vllm/v1",
    "nemotron-3-ultra": f"{ALCF}/minerva/api/v1",
}

PROXIED_PATHS = ("chat/completions", "completions", "responses", "embeddings")
RETRY_STATUSES = {502, 503, 504}


class TokenCache:
    """Caches the ALCF access token; `fetch` refreshes it (blocking, so run in a thread)."""

    def __init__(self, fetch: Callable[[], str], ttl_s: float = 60.0):
        self._fetch = fetch
        self._ttl_s = ttl_s
        self._token: str | None = None
        self._at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        async with self._lock:
            if self._token is None or time.monotonic() - self._at > self._ttl_s:
                self._token = await asyncio.to_thread(self._fetch)
                self._at = time.monotonic()
            return self._token

    def invalidate(self) -> None:
        self._token = None


@dataclass
class Stats:
    in_flight: int = 0
    waiting: int = 0
    completed: int = 0
    failed: int = 0
    max_in_flight: int = 0


class RequestLog:
    def __init__(self, path: Path | None):
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict) -> None:
        if self._path is None:
            return
        with self._path.open("a") as f:
            f.write(json.dumps(record) + "\n")


STATS_KEY = web.AppKey("stats", Stats)
SESSION_KEY = web.AppKey("session", ClientSession)


def _usage(data: bytes) -> tuple[int | None, int | None]:
    try:
        usage = json.loads(data).get("usage") or {}
    except (ValueError, AttributeError):
        return None, None
    return usage.get("prompt_tokens", usage.get("input_tokens")), usage.get(
        "completion_tokens", usage.get("output_tokens")
    )


def _error(status: int, message: str) -> web.Response:
    return web.json_response({"error": {"message": message, "type": "gateway_error"}}, status=status)


def create_app(
    *,
    routes: dict[str, str] | None = None,
    token_fetch: Callable[[], str] | None = None,
    max_concurrency: int = MAX_CONCURRENCY,
    log_path: Path | None = None,
    max_attempts: int = 4,
    backoff_base_s: float = 2.0,
    upstream_timeout_s: float = 600.0,
) -> web.Application:
    if not 1 <= max_concurrency <= MAX_CONCURRENCY:
        raise ValueError(f"max_concurrency must be between 1 and {MAX_CONCURRENCY}")
    if token_fetch is None:
        from smbench.alcf.auth import get_access_token as token_fetch

    routes = dict(ROUTES if routes is None else routes)
    token = TokenCache(token_fetch)
    slots = asyncio.Semaphore(max_concurrency)
    stats = Stats()
    log = RequestLog(log_path)

    async def upstream_session(app: web.Application):
        app[SESSION_KEY] = ClientSession(timeout=ClientTimeout(total=upstream_timeout_s))
        yield
        await app[SESSION_KEY].close()

    async def proxy(request: web.Request) -> web.StreamResponse:
        path = request.match_info["path"]
        if path not in PROXIED_PATHS:
            return _error(404, f"unsupported path /v1/{path}; supported: {', '.join(PROXIED_PATHS)}")
        raw = await request.read()
        try:
            body = json.loads(raw)
        except ValueError:
            return _error(400, "request body is not valid JSON")
        model = body.get("model")
        base = routes.get(model)
        if base is None:
            return _error(400, f"unknown model {model!r}; known: {', '.join(sorted(routes))}")

        record = {
            "ts": time.time(),
            "run_id": request.headers.get("X-Run-Id"),
            "system": request.headers.get("X-System"),
            "model": model,
            "path": path,
            "stream": bool(body.get("stream")),
        }
        attempts, queue_wait_s, upstream_s, last_error = 0, 0.0, 0.0, None
        session = request.app[SESSION_KEY]

        while True:
            attempts += 1
            retry, backoff = False, True
            stats.waiting += 1
            t_wait = time.monotonic()
            async with slots:
                stats.waiting -= 1
                queue_wait_s += time.monotonic() - t_wait
                stats.in_flight += 1
                stats.max_in_flight = max(stats.max_in_flight, stats.in_flight)
                t_up = time.monotonic()
                try:
                    headers = {"Authorization": f"Bearer {await token.get()}", "Content-Type": "application/json"}
                    async with session.post(f"{base}/{path}", data=raw, headers=headers) as up:
                        if up.status == 401 and attempts < max_attempts:
                            token.invalidate()
                            last_error, retry, backoff = "401 from upstream; refreshed token", True, False
                        elif up.status in RETRY_STATUSES and attempts < max_attempts:
                            last_error = f"{up.status}: {(await up.text())[:300]}"
                            retry = True
                        elif record["stream"] and up.status == 200:
                            resp = web.StreamResponse(
                                status=200,
                                headers={"Content-Type": up.headers.get("Content-Type", "text/event-stream")},
                            )
                            await resp.prepare(request)
                            async for chunk in up.content.iter_any():
                                await resp.write(chunk)
                            await resp.write_eof()
                            upstream_s += time.monotonic() - t_up
                            stats.completed += 1
                            log.write(record | {"status": 200, "attempts": attempts,
                                                "queue_wait_s": round(queue_wait_s, 3),
                                                "upstream_s": round(upstream_s, 3)})
                            return resp
                        else:
                            data = await up.read()
                            upstream_s += time.monotonic() - t_up
                            prompt_tokens, completion_tokens = _usage(data)
                            ok = up.status < 400
                            stats.completed += ok
                            stats.failed += not ok
                            log.write(record | {
                                "status": up.status, "attempts": attempts,
                                "queue_wait_s": round(queue_wait_s, 3), "upstream_s": round(upstream_s, 3),
                                "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                                "error": None if ok else data[:300].decode(errors="replace"),
                            })
                            return web.Response(
                                body=data, status=up.status,
                                headers={"Content-Type": up.headers.get("Content-Type", "application/json")},
                            )
                except (ClientError, asyncio.TimeoutError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempts >= max_attempts:
                        stats.failed += 1
                        log.write(record | {"status": 502, "attempts": attempts,
                                            "queue_wait_s": round(queue_wait_s, 3), "error": last_error})
                        return _error(502, f"upstream failed after {attempts} attempts: {last_error}")
                    retry = True
                finally:
                    if retry:
                        upstream_s += time.monotonic() - t_up
                    stats.in_flight -= 1
            if retry and backoff:
                # Wait outside the semaphore so a retrying request doesn't hold a slot.
                await asyncio.sleep(backoff_base_s * 2 ** (attempts - 1) * random.uniform(0.8, 1.2))

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"max_concurrency": max_concurrency, "models": sorted(routes), **asdict(stats)})

    async def models(_: web.Request) -> web.Response:
        return web.json_response({"object": "list", "data": [{"id": m, "object": "model"} for m in sorted(routes)]})

    app = web.Application(client_max_size=64 * 1024**2)
    app.cleanup_ctx.append(upstream_session)
    app[STATS_KEY] = stats
    app.router.add_get("/health", health)
    app.router.add_get("/v1/models", models)
    app.router.add_post("/v1/{path:.+}", proxy)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Rate-limited local gateway to the ALCF inference service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8411)
    parser.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY,
                        help=f"concurrent upstream requests (1-{MAX_CONCURRENCY})")
    parser.add_argument("--log", type=Path, default=Path("results/gateway/requests.jsonl"))
    args = parser.parse_args()
    app = create_app(max_concurrency=args.max_concurrency, log_path=args.log)
    print(f"ALCF gateway on http://{args.host}:{args.port}/v1 (max {args.max_concurrency} concurrent), log {args.log}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
