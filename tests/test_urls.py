import asyncio
import ipaddress

import httpx
import pytest

from tos_bot.services import urls


def public_dns(monkeypatch):
    def fake(host: str):
        if host == "example.com":
            return [ipaddress.ip_address("93.184.216.34")]
        return [ipaddress.ip_address("127.0.0.1")]

    monkeypatch.setattr(urls, "_resolve_host_ips", fake)


def test_validate_rejects_private_and_bad_schemes():
    for url in (
        "http://127.0.0.1/doc",
        "http://10.0.0.1/doc",
        "http://192.168.1.1/doc",
        "http://localhost/doc",
        "http://example.com:8080/doc",
        "file:///etc/passwd",
        "https://user:pass@example.com/doc",
    ):
        with pytest.raises(ValueError):
            urls._validate_url(url)


def test_validate_accepts_public_http(monkeypatch):
    public_dns(monkeypatch)
    assert urls._validate_url("https://example.com/doc") == "https://example.com/doc"


def test_fetch_follows_safe_redirect(monkeypatch):
    public_dns(monkeypatch)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/doc"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><article><p>" + ("Договор " * 80) + "</p></article></body></html>",
        )

    text = asyncio.run(
        urls.fetch_url_text(
            "https://example.com/start",
            transport=httpx.MockTransport(handler),
        )
    )
    assert "Договор" in text
    assert calls == ["https://example.com/start", "https://example.com/doc"]


def test_fetch_blocks_redirect_to_private(monkeypatch):
    public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    with pytest.raises(ValueError, match="внутренний адрес"):
        asyncio.run(
            urls.fetch_url_text(
                "https://example.com/doc",
                transport=httpx.MockTransport(handler),
            )
        )


def test_fetch_rejects_binary_content(monkeypatch):
    public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    with pytest.raises(ValueError, match="content-type"):
        asyncio.run(
            urls.fetch_url_text(
                "https://example.com/doc.pdf",
                transport=httpx.MockTransport(handler),
            )
        )


def test_fetch_reports_http_status(monkeypatch):
    public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(ValueError, match="404"):
        asyncio.run(
            urls.fetch_url_text(
                "https://example.com/missing",
                transport=httpx.MockTransport(handler),
            )
        )


def test_fetch_limits_redirects(monkeypatch):
    public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    with pytest.raises(ValueError, match="редиректов"):
        asyncio.run(
            urls.fetch_url_text(
                "https://example.com/loop",
                transport=httpx.MockTransport(handler),
            )
        )
