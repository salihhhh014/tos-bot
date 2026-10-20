from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from tos_bot.config import Settings


@dataclass
class Provider:
    name: str
    client: AsyncOpenAI
    model: str


def _client(api_key: str, base_url: str | None) -> AsyncOpenAI:
    kwargs: dict = {"api_key": api_key, "timeout": 60.0, "max_retries": 2}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)


def make_providers(cfg: Settings) -> list[Provider]:
    """Основной + опциональный запасной. OCR всегда ходит в основной (Mistral)."""
    providers = [
        Provider(
            name="primary",
            client=_client(cfg.openai_api_key.get_secret_value(), cfg.openai_base_url),
            model=cfg.openai_model,
        )
    ]
    fb_key = cfg.fallback_api_key.get_secret_value()
    if fb_key and cfg.fallback_base_url and cfg.fallback_model:
        providers.append(
            Provider(
                name="fallback",
                client=_client(fb_key, cfg.fallback_base_url),
                model=cfg.fallback_model,
            )
        )
    return providers
