from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

URLS = re.compile(r"https?://[^\s<>\"]+")

MAX_HTML_BYTES = 2_000_000
MAX_TEXT_CHARS = 80_000
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_host_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        raise ValueError("домен не резолвится") from exc

    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError):
            continue
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise ValueError("домен не резолвится")
    return ips


def _validate_url(url: str) -> str:
    """Проверяет схему, порт, учётные данные и публичность всех IP домена."""
    url = url.strip().rstrip(").,")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("некорректная ссылка") from exc

    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise ValueError("нужна публичная http(s)-ссылка")
    if parsed.username or parsed.password:
        raise ValueError("ссылки с логином/паролем не поддерживаются")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("некорректный порт в ссылке") from exc
    if port not in ALLOWED_PORTS:
        raise ValueError("разрешены только порты 80 и 443")

    host = parsed.hostname.lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ValueError("ссылка ведёт на внутренний адрес")

    ips = _resolve_host_ips(host)
    if not all(_is_public_ip(ip) for ip in ips):
        raise ValueError("ссылка ведёт на внутренний адрес")
    return url


async def fetch_url_text(
    url: str,
    timeout_sec: int = 15,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Скачивает публичную html/text-страницу с проверкой каждого редиректа."""

    current = _validate_url(url)

    headers = {"User-Agent": "tos-bot/0.1 (+document analysis)"}
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            follow_redirects=False,
            headers=headers,
            transport=transport,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise ValueError("редирект без адреса")
                        current = _validate_url(urljoin(current, location))
                        continue

                    resp.raise_for_status()
                    ctype = resp.headers.get("content-type", "").lower()
                    if "html" not in ctype and "text" not in ctype:
                        raise ValueError(f"не тяну такой content-type: {ctype or 'не указан'}")

                    buf = bytearray()
                    async for chunk in resp.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) >= MAX_HTML_BYTES:
                            break
                    raw = bytes(buf[:MAX_HTML_BYTES])
                    break
            else:
                raise ValueError(f"слишком много редиректов (больше {MAX_REDIRECTS})")
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"сайт ответил ошибкой {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"не удалось скачать страницу: {type(exc).__name__}") from exc

    html = raw.decode("utf-8", errors="replace")
    text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    text = text.strip()
    if len(text) < 200:
        raise ValueError("на странице почти нет текста (может, нужен JS)")
    return text[:MAX_TEXT_CHARS]
