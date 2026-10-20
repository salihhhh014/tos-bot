from __future__ import annotations

import base64

import httpx

from tos_bot.config import Settings

MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def pages_to_text(data: dict) -> str:
    pages = data.get("pages") or []
    return "\n".join(p.get("markdown") or "" for p in pages).strip()


DEFAULT_MISTRAL_BASE = "https://api.mistral.ai/v1"


def ocr_creds(cfg: Settings) -> tuple[str, str]:
    # ключ/бейз OCR: свои, если заданы, иначе те же, что у основного чата.
    # если задан только OCR_API_KEY — считаем, что это Mistral.
    key = cfg.ocr_api_key.get_secret_value() or cfg.openai_api_key.get_secret_value()
    if cfg.ocr_base_url:
        base = cfg.ocr_base_url
    elif cfg.ocr_api_key.get_secret_value():
        base = DEFAULT_MISTRAL_BASE
    else:
        base = cfg.openai_base_url or ""
    return key, base.rstrip("/")


def ocr_available(cfg: Settings) -> bool:
    if not cfg.ocr_enabled:
        return False
    key, base = ocr_creds(cfg)
    return bool(key) and "mistral" in base


async def ocr_document(cfg: Settings, raw: bytes, ext: str) -> str:
    """Скан/фото -> текст. OCR-эндпоинт есть только у Mistral —
    у Groq/Qwen его нет, это не наш каприз, а их API."""
    mime = MIME[ext]
    key, base = ocr_creds(cfg)
    if not getattr(cfg, "ocr_enabled", True):
        raise ValueError("OCR выключен (OCR_ENABLED=0), сканы и фото не читаю")
    if not key:
        raise ValueError("OCR включён, но не задан OCR_API_KEY (ключ Mistral)")
    if "mistral" not in base:
        raise ValueError(
            "OCR умеет только Mistral. Задай OCR_API_KEY (ключ Mistral) "
            "или OCR_BASE_URL=https://api.mistral.ai/v1 или выключи OCR_ENABLED=0"
        )
    payload = {
        "model": cfg.ocr_model,
        "document": {
            "type": "document_url",
            "document_url": f"data:{mime};base64,{base64.b64encode(raw).decode()}",
        },
    }
    url = base + "/ocr"
    try:
        async with httpx.AsyncClient(
            timeout=cfg.ocr_timeout_sec,
            headers={"Authorization": f"Bearer {key}"},
        ) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            text = pages_to_text(resp.json())
    except httpx.HTTPError as e:
        raise ValueError(f"OCR не сработал: {e}") from e
    if len(text) < 50:
        raise ValueError("OCR почти ничего не нашел — может, фото нечитаемо")
    return text
