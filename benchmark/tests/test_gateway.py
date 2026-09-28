"""Gateway tests against a fake upstream; no ALCF traffic."""

from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from smbench.alcf.gateway import MAX_CONCURRENCY, STATS_KEY, create_app


class FakeUpstream:
    def __init__(self, delay_s: float = 0.05):
        self.delay_s = delay_s
        self.current = 0
        self.max_seen = 0
        self.calls = 0
        self.fail_first = 0
        self.fail_status = 503
        self.accept_token: str | None = None

    def app(self) -> web.Application:
        async def chat(request: web.Request) -> web.StreamResponse:
            self.calls += 1
            if self.accept_token and request.headers.get("Authorization") != f"Bearer {self.accept_token}":
                return web.json_response({"error": "bad token"}, status=401)
            if self.calls <= self.fail_first:
                return web.json_response({"error": "not ready"}, status=self.fail_status)
            body = await request.json()
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
            try:
                await asyncio.sleep(self.delay_s)
            finally:
                self.current -= 1
            if body.get("stream"):
                resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
                await resp.prepare(request)
                for part in ("data: a\n\n", "data: b\n\n", "data: [DONE]\n\n"):
                    await resp.write(part.encode())
                await resp.write_eof()
                return resp
            return web.json_response({"choices": [{"message": {"content": "ok"}}],
                                      "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

        app = web.Application()
        app.router.add_post("/v1/chat/completions", chat)
        return app


async def _run(fake: FakeUpstream, requests, *, token_fetch=lambda: "t", log_path=None, **kw):
    upstream = TestServer(fake.app())
    await upstream.start_server()
    gateway_app = create_app(routes={"m": str(upstream.make_url("/v1"))}, token_fetch=token_fetch,
                             log_path=log_path, backoff_base_s=0.01, **kw)
    gateway = TestServer(gateway_app)
    await gateway.start_server()
    try:
        async with ClientSession() as client:
            return await requests(client, gateway.make_url("/v1/chat/completions")), gateway_app
    finally:
        await gateway.close()
        await upstream.close()


def _chat(model="m", **extra):
    return {"model": model, "messages": [{"role": "user", "content": "hi"}], **extra}


def test_caps_concurrency_at_six(tmp_path):
    fake = FakeUpstream(delay_s=0.1)

    async def burst(client, url):
        async def one(i):
            async with client.post(url, json=_chat(), headers={"X-Run-Id": "r1", "X-System": "s"}) as r:
                return r.status
        return await asyncio.gather(*(one(i) for i in range(20)))

    statuses, app = asyncio.run(_run(fake, burst, log_path=tmp_path / "log.jsonl"))
    assert statuses == [200] * 20
    assert fake.max_seen == MAX_CONCURRENCY
    assert app[STATS_KEY].max_in_flight == MAX_CONCURRENCY
    lines = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert len(lines) == 20
    assert all(l["run_id"] == "r1" and l["prompt_tokens"] == 3 for l in lines)


def test_refuses_concurrency_above_six():
    with pytest.raises(ValueError):
        create_app(token_fetch=lambda: "t", max_concurrency=MAX_CONCURRENCY + 1)


def test_lower_concurrency_is_respected():
    fake = FakeUpstream(delay_s=0.05)

    async def burst(client, url):
        async def one(_):
            async with client.post(url, json=_chat()) as r:
                return r.status
        return await asyncio.gather(*(one(i) for i in range(8)))

    asyncio.run(_run(fake, burst, max_concurrency=2))
    assert fake.max_seen == 2


def test_retries_transient_503(tmp_path):
    fake = FakeUpstream()
    fake.fail_first = 2

    async def once(client, url):
        async with client.post(url, json=_chat()) as r:
            return r.status

    status, _ = asyncio.run(_run(fake, once, log_path=tmp_path / "log.jsonl"))
    assert status == 200
    assert json.loads((tmp_path / "log.jsonl").read_text())["attempts"] == 3


def test_gives_up_after_max_attempts():
    fake = FakeUpstream()
    fake.fail_first = 99

    async def once(client, url):
        async with client.post(url, json=_chat()) as r:
            return r.status

    status, _ = asyncio.run(_run(fake, once, max_attempts=3))
    assert status == 503
    assert fake.calls == 3


def test_refreshes_token_on_401():
    fake = FakeUpstream()
    fake.accept_token = "fresh"
    tokens = iter(["stale", "fresh"])

    async def once(client, url):
        async with client.post(url, json=_chat()) as r:
            return r.status

    status, _ = asyncio.run(_run(fake, once, token_fetch=lambda: next(tokens)))
    assert status == 200


def test_rejects_unknown_model():
    fake = FakeUpstream()

    async def once(client, url):
        async with client.post(url, json=_chat(model="nope")) as r:
            return r.status, await r.json()

    (status, body), _ = asyncio.run(_run(fake, once))
    assert status == 400
    assert "unknown model" in body["error"]["message"]
    assert fake.calls == 0


def test_streams_through():
    fake = FakeUpstream()

    async def once(client, url):
        async with client.post(url, json=_chat(stream=True)) as r:
            return r.status, await r.text()

    (status, text), _ = asyncio.run(_run(fake, once))
    assert status == 200
    assert text.endswith("data: [DONE]\n\n")
