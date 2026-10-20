import asyncio
from types import SimpleNamespace

import pytest

import tos_bot.services.documents as docs


class FakeBot:
    def __init__(self, payload: bytes = b"image-bytes") -> None:
        self.payload = payload
        self.file_id = None

    async def get_file(self, file_id: str):
        self.file_id = file_id
        return SimpleNamespace(file_path="photos/file.jpg")

    async def download_file(self, path: str, destination) -> None:
        destination.write(self.payload)


def cfg(**kw):
    base = {"max_file_mb": 10, "ocr_enabled": True}
    base.update(kw)
    return SimpleNamespace(**base)


def test_photo_uses_ocr(monkeypatch):
    async def fake_ocr(cfg_, raw, ext):
        assert ext == ".jpg"
        assert raw == b"image-bytes"
        return "текст со скриншота " * 20

    monkeypatch.setattr(docs, "ocr_document", fake_ocr)
    msg = SimpleNamespace(
        photo=[
            SimpleNamespace(file_id="small", file_size=10),
            SimpleNamespace(file_id="big", file_size=10),
        ]
    )
    bot = FakeBot()
    text, via_ocr = asyncio.run(docs.extract_from_telegram_photo(bot, msg, cfg()))
    assert via_ocr is True
    assert "скриншота" in text
    assert bot.file_id == "big"


def test_photo_size_limit():
    msg = SimpleNamespace(photo=[SimpleNamespace(file_id="big", file_size=11 * 1024 * 1024)])
    with pytest.raises(ValueError, match="больше"):
        asyncio.run(docs.extract_from_telegram_photo(FakeBot(), msg, cfg(max_file_mb=10)))


def test_photo_without_ocr_key_is_clear(monkeypatch):
    from pydantic import SecretStr

    real_cfg = SimpleNamespace(
        max_file_mb=10,
        ocr_enabled=True,
        ocr_api_key=SecretStr(""),
        ocr_base_url="",
        openai_api_key=SecretStr("chat-key"),
        openai_base_url="https://api.groq.com/openai/v1",
        ocr_model="m",
        ocr_timeout_sec=5,
    )
    msg = SimpleNamespace(photo=[SimpleNamespace(file_id="big", file_size=10)])
    with pytest.raises(ValueError, match="OCR"):
        asyncio.run(docs.extract_from_telegram_photo(FakeBot(), msg, real_cfg))
