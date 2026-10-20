import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import AuthenticationError, RateLimitError

from tos_bot.services.analyzer import Pipeline
from tos_bot.services.cache import ReportCache
from tos_bot.services.llm import Provider
from tos_bot.utils.telegram import strip_tags


def api_error(cls, status: int):
    req = httpx.Request("POST", "http://test/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=req), body={})


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def create(self, **kw):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


def provider(script):
    fake = FakeCompletions(script)
    client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return Provider(name="t", client=client, model="m"), fake


def make_pipe(providers):
    p = Pipeline.__new__(Pipeline)
    p.providers = providers
    p.cache = ReportCache(max_entries=10, ttl_sec=60)
    return p


def test_primary_ok_fallback_untouched():
    p1, f1 = provider(["ok"])
    p2, f2 = provider(["fallback"])
    assert asyncio.run(make_pipe([p1, p2])._ask("hi")) == "ok"
    assert f1.calls == 1
    assert f2.calls == 0


def test_429_goes_to_fallback():
    p1, _ = provider([api_error(RateLimitError, 429)])
    p2, f2 = provider(["from-fallback"])
    assert asyncio.run(make_pipe([p1, p2])._ask("hi")) == "from-fallback"
    assert f2.calls == 1


def test_all_down_raises_last():
    p1, _ = provider([api_error(RateLimitError, 429)])
    p2, _ = provider([api_error(RateLimitError, 429)])
    with pytest.raises(RateLimitError):
        asyncio.run(make_pipe([p1, p2])._ask("hi"))


def test_auth_error_no_fallback():
    p1, _ = provider([api_error(AuthenticationError, 401)])
    p2, f2 = provider(["fallback"])
    with pytest.raises(AuthenticationError):
        asyncio.run(make_pipe([p1, p2])._ask("hi"))
    assert f2.calls == 0


def test_strip_tags():
    assert strip_tags("<b>жирно</b> и <code>x</code>") == "жирно и x"
