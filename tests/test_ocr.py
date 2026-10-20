import asyncio
from types import SimpleNamespace

import pytest

import tos_bot.services.documents as docs
from tos_bot.services.ocr import (
    DEFAULT_MISTRAL_BASE,
    ocr_available,
    ocr_creds,
    ocr_document,
    pages_to_text,
)


def ocr_cfg(**kw):
    base = {"ocr_enabled": True, "ocr_model": "m", "ocr_timeout_sec": 5}
    base.update(kw)
    return SimpleNamespace(**base)


def test_pages_to_text():
    data = {"pages": [{"markdown": "стр1"}, {"markdown": ""}, {"markdown": "стр2"}]}
    assert pages_to_text(data) == "стр1\n\nстр2"


def test_pages_to_text_empty():
    assert pages_to_text({}) == ""
    assert pages_to_text({"pages": []}) == ""


def test_txt_passthrough():
    text, via_ocr = asyncio.run(docs.extract_bytes(b"a" * 500, ".txt", ocr_cfg()))
    assert via_ocr is False
    assert len(text) == 500


def test_docx_short_raises(monkeypatch):
    monkeypatch.setattr(docs, "_docx_to_text", lambda raw: "коротко")
    with pytest.raises(ValueError):
        asyncio.run(docs.extract_bytes(b"x", ".docx", ocr_cfg()))


def test_scan_pdf_falls_back_to_ocr(monkeypatch):
    monkeypatch.setattr(docs, "_pdf_to_text", lambda raw: "  \n ")

    async def fake_ocr(cfg, raw, ext):
        assert ext == ".pdf"
        return "распознанный текст " * 20

    monkeypatch.setattr(docs, "ocr_document", fake_ocr)
    text, via_ocr = asyncio.run(docs.extract_bytes(b"pdf-bytes", ".pdf", ocr_cfg()))
    assert via_ocr is True
    assert "распознанный" in text


def test_scan_with_disabled_ocr_raises(monkeypatch):
    monkeypatch.setattr(docs, "_pdf_to_text", lambda raw: "")
    with pytest.raises(ValueError, match="OCR выключен"):
        asyncio.run(docs.extract_bytes(b"pdf-bytes", ".pdf", ocr_cfg(ocr_enabled=False)))


def test_photo_goes_straight_to_ocr(monkeypatch):
    called = {}

    async def fake_ocr(cfg, raw, ext):
        called["ext"] = ext
        return "текст с фото " * 20

    monkeypatch.setattr(docs, "ocr_document", fake_ocr)
    text, via_ocr = asyncio.run(docs.extract_bytes(b"img", ".jpg", ocr_cfg()))
    assert via_ocr is True
    assert called["ext"] == ".jpg"
    assert "фото" in text


def test_ocr_refuses_non_mistral_base():
    from pydantic import SecretStr

    cfg = SimpleNamespace(
        ocr_api_key=SecretStr(""),
        ocr_base_url="",
        openai_api_key=SecretStr("gsk-x"),
        openai_base_url="https://api.groq.com/openai/v1",
        ocr_model="m",
        ocr_timeout_sec=5,
    )
    with pytest.raises(ValueError, match="только Mistral"):
        asyncio.run(ocr_document(cfg, b"img", ".jpg"))


def test_ocr_creds_prefers_own():
    from pydantic import SecretStr

    cfg = SimpleNamespace(
        ocr_api_key=SecretStr("ocr-key"),
        ocr_base_url="https://ocr-base",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://chat-base",
    )
    assert ocr_creds(cfg) == ("ocr-key", "https://ocr-base")


def test_ocr_creds_falls_back_to_chat():
    from pydantic import SecretStr

    cfg = SimpleNamespace(
        ocr_api_key=SecretStr(""),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://chat-base/",
    )
    assert ocr_creds(cfg) == ("chat-key", "https://chat-base")


def test_ocr_key_alone_selects_mistral():
    from pydantic import SecretStr

    cfg = SimpleNamespace(
        ocr_api_key=SecretStr("mistral-key"),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://api.groq.com/openai/v1",
    )
    assert ocr_creds(cfg) == ("mistral-key", DEFAULT_MISTRAL_BASE)


def test_ocr_available_requires_mistral_key():
    from pydantic import SecretStr

    enabled = SimpleNamespace(
        ocr_enabled=True,
        ocr_api_key=SecretStr("mistral-key"),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://api.groq.com/openai/v1",
    )
    assert ocr_available(enabled) is True

    no_key = SimpleNamespace(
        ocr_enabled=True,
        ocr_api_key=SecretStr(""),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://api.groq.com/openai/v1",
    )
    assert ocr_available(no_key) is False

    disabled = SimpleNamespace(
        ocr_enabled=False,
        ocr_api_key=SecretStr("mistral-key"),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://api.groq.com/openai/v1",
    )
    assert ocr_available(disabled) is False
