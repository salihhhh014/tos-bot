from __future__ import annotations

import asyncio
import logging

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from tos_bot.config import Settings
from tos_bot.prompts.tos_audit import (
    MERGE_PROMPT,
    PART_PROMPT,
    SYSTEM_PROMPT,
    build_extract_prompt,
    build_full_prompt,
)
from tos_bot.services.cache import ReportCache, doc_key
from tos_bot.services.chunking import split_for_model
from tos_bot.services.llm import make_providers

log = logging.getLogger(__name__)

# по этим ошибкам есть смысл стучаться в запасного провайдера.
# остальное (401, 400, кривой промпт) — наша вина, ретраить некуда
RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


class Pipeline:
    """Оркестрация: нормализация -> кэш -> порезать -> спросить модель -> собрать итог."""

    def __init__(self, cfg: Settings, cache: ReportCache | None = None) -> None:
        self.cfg = cfg
        self.providers = make_providers(cfg)
        log.info("llm providers: %s", [(p.name, p.model) for p in self.providers])
        self.cache = cache or ReportCache(
            max_entries=cfg.cache_max_entries,
            ttl_sec=cfg.cache_ttl_hours * 3600,
        )

    def prepare(self, text: str) -> tuple[str, bool]:
        # один канон для ключа кэша и для модели: пробелы/переносы не влияют.
        # флаг говорит, что хвост отрезали — об этом честно пишем юзеру
        body = " ".join(text.split())
        if len(body) > self.cfg.max_doc_chars:
            return body[: self.cfg.max_doc_chars], True
        return body, False

    def lookup(self, body: str, lang: str = "ru") -> str | None:
        # готовый body (уже после prepare). None = мимо кэша
        if len(body) < 200:
            return None
        return self.cache.get(doc_key(body, self.cfg.openai_model, lang))

    def peek(self, text: str, lang: str = "ru") -> str | None:
        body, _ = self.prepare(text)
        return self.lookup(body, lang)

    async def extract(self, doc: str, topic: str, lang: str = "ru") -> str | None:
        # дословный кусок про тему. None = в документе про это ничего нет
        raw = await self._ask(build_extract_prompt(doc, topic, lang))
        if raw.strip().upper() in {"НЕТ", "NO", "NONE"}:
            return None
        return raw.strip() or None

    async def _ask(self, user_prompt: str) -> str:
        last: Exception | None = None
        for p in self.providers:
            try:
                resp = await p.client.chat.completions.create(
                    model=p.model,
                    temperature=0,  # важно: иначе начнет додумывать
                    max_tokens=1500,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return text
                last = ValueError(f"provider {p.name} returned empty response")
            except RETRYABLE as e:
                # 429/таймаут/обрыв — пробуем следующего, юзер ничего не заметит
                log.warning("provider %s failed (%s), trying next", p.name, type(e).__name__)
                last = e
        raise last or RuntimeError("no llm providers configured")

    async def run(self, text: str, lang: str = "ru") -> str:
        body, _ = self.prepare(text)
        if len(body) < 200:
            return "Текста маловато для разбора. Кинь полный документ."

        key = doc_key(body, self.cfg.openai_model, lang)
        if (hit := self.cache.get(key)) is not None:
            log.info("cache hit")
            return hit

        chunks = split_for_model(body)
        if len(chunks) == 1:
            report = await self._ask(build_full_prompt(chunks[0], lang))
            self.cache.put(key, report)
            return report

        # куски разбираем с лимитом параллельности — бережем TPM бесплатного тира
        sem = asyncio.Semaphore(max(1, self.cfg.chunk_concurrency))

        async def one(idx: int, ch: str) -> str:
            async with sem:
                return await self._ask(PART_PROMPT.format(idx=idx + 1, total=len(chunks), chunk=ch))

        drafts = await asyncio.gather(*[one(i, c) for i, c in enumerate(chunks)])
        merged = MERGE_PROMPT.format(drafts="\n\n---\n\n".join(drafts))
        # merge идет уже без SYSTEM? нет — системный всегда тот же, формат держим
        report = await self._ask(merged)
        self.cache.put(key, report)
        return report
