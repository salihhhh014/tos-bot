from __future__ import annotations

import logging
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.types import Message
from openai import RateLimitError

from tos_bot.config import Settings
from tos_bot.handlers.quote import quote_button, register_quote_handlers
from tos_bot.services.analyzer import Pipeline
from tos_bot.services.docstore import DocStore, Prefs
from tos_bot.services.documents import (
    extract_from_telegram_file,
    extract_from_telegram_photo,
)
from tos_bot.services.ocr import ocr_available
from tos_bot.services.quota import Quota
from tos_bot.services.urls import URLS, fetch_url_text
from tos_bot.utils.telegram import answer_long

log = logging.getLogger(__name__)

# телеграм режет сообщения на 4096, держим запас
TG_LIMIT = 4000


def analyze_router(cfg: Settings) -> Router:
    r = Router()
    pipe = Pipeline(cfg)
    quota = Quota(cfg.quota_db_path, cfg.daily_limit_per_user)
    prefs = Prefs(cfg.quota_db_path)
    store = DocStore()

    # белый список юзеров, если задан. пусто = всем можно
    allowed = cfg.allowed_ids()
    if not allowed:
        log.warning("ALLOWED_USER_IDS не задан — бот открыт всем пользователям")
    if cfg.ocr_enabled and not ocr_available(cfg):
        log.warning("OCR включён, но ключ Mistral не задан — сканы и фото будут недоступны")

    async def guard(msg: Message) -> bool:
        if allowed and (msg.from_user is None or msg.from_user.id not in allowed):
            await msg.answer("Нет доступа.")
            return False
        return True

    async def user_lang(msg: Message) -> str:
        return await prefs.get_lang(msg.from_user.id if msg.from_user else 0)

    async def refund_quota(msg: Message) -> None:
        await quota.refund(msg.from_user.id if msg.from_user else 0)

    async def fail(msg: Message, status: Message, rate_limited: bool) -> None:
        # модель не ответила — юзер не виноват, попытку возвращаем
        await refund_quota(msg)
        if rate_limited:
            await status.edit_text(
                "Модель уперлась в свой лимит (429). Подожди минуту и кинь еще раз — "
                "попытка не засчитана."
            )
        else:
            await status.edit_text(
                "Упал на стороне модели, попробуй чуть позже. Попытка не засчитана."
            )

    async def take_quota(msg: Message) -> bool:
        # квоту жжем только за реальный разбор, а не за мусорные сообщения.
        # поэтому вызываем после всех валидаций, прямо перед моделью
        user_id = msg.from_user.id if msg.from_user else 0
        ok, left = await quota.check_and_hit(user_id)
        if not ok:
            await msg.answer(
                f"На сегодня лимит исчерпан ({cfg.daily_limit_per_user}/день). Заглядывай завтра."
            )
            return False
        if left <= 5 and left >= 0:
            await msg.answer(f"Принято. На сегодня осталось: {left}.")
        return True

    def cut_note() -> str:
        return (
            f"\n\n<i>Документ длиннее {cfg.max_doc_chars} символов: разобрано начало, "
            "хвост модель не видела. Проверьте его глазами.</i>"
        )

    async def finish(
        msg: Message,
        report: str,
        body: str,
        label: str,
        truncated: bool,
        status: Message | None = None,
    ) -> None:
        # общий финал: документ в память (для кнопки цитат), отчет кусками, кнопка в конце
        if status is not None:
            await status.delete()
        user_id = msg.from_user.id if msg.from_user else 0
        store.save(user_id, label, body, truncated)
        text = report + (cut_note() if truncated else "")
        await answer_long(msg, text, reply_markup=quote_button(), limit=TG_LIMIT)

    async def answer_cached(
        msg: Message, status: Message, text: str, label: str, lang: str
    ) -> bool:
        # уже разбирали такой документ — отдаем из кэша, квоту не трогаем
        body, truncated = pipe.prepare(text)
        if (hit := pipe.lookup(body, lang)) is None:
            return False
        await finish(msg, hit, body, label, truncated, status)
        return True

    register_quote_handlers(r, pipe, store, prefs, guard, take_quota, refund_quota)

    @r.message(F.document)
    async def on_document(msg: Message) -> None:
        if not await guard(msg):
            return
        label = (msg.document.file_name if msg.document else None) or "файл"
        status = await msg.answer("Забираю файл, читаю…")
        try:
            text, via_ocr = await extract_from_telegram_file(msg.bot, msg, cfg)
        except ValueError as e:
            await status.edit_text(f"Не смог прочитать файл: {e}")
            return
        lang = await user_lang(msg)
        if await answer_cached(msg, status, text, label, lang):
            return
        if not await take_quota(msg):
            await status.delete()
            return
        await status.edit_text(
            "Скан распознан, спрашиваю модель…" if via_ocr else "Файл прочитал, спрашиваю модель…"
        )
        try:
            report = await pipe.run(text, lang)
        except RateLimitError:
            log.warning("analyze rate-limited (document)")
            await fail(msg, status, rate_limited=True)
            return
        except Exception:
            log.exception("analyze failed (document)")
            await fail(msg, status, rate_limited=False)
            return
        body, truncated = pipe.prepare(text)
        await finish(msg, report, body, label, truncated, status)

    @r.message(F.photo)
    async def on_photo(msg: Message) -> None:
        if not await guard(msg):
            return
        status = await msg.answer("Распознаю изображение…")
        try:
            text, _ = await extract_from_telegram_photo(msg.bot, msg, cfg)
        except ValueError as e:
            await status.edit_text(f"Не смог прочитать фото: {e}")
            return
        lang = await user_lang(msg)
        if await answer_cached(msg, status, text, "фото", lang):
            return
        if not await take_quota(msg):
            await status.delete()
            return
        await status.edit_text("Фото распознано, спрашиваю модель…")
        try:
            report = await pipe.run(text, lang)
        except RateLimitError:
            log.warning("analyze rate-limited (photo)")
            await fail(msg, status, rate_limited=True)
            return
        except Exception:
            log.exception("analyze failed (photo)")
            await fail(msg, status, rate_limited=False)
            return
        body, truncated = pipe.prepare(text)
        await finish(msg, report, body, "фото", truncated, status)

    @r.message(F.text & F.func(lambda m: URLS.search(m.text or "")))
    async def on_url(msg: Message) -> None:
        if not await guard(msg):
            return
        url = URLS.search(msg.text or "").group(0)  # type: ignore[union-attr]
        label = urlparse(url).hostname or "ссылка"
        status = await msg.answer("Качаю страницу…")
        try:
            text = await fetch_url_text(url, timeout_sec=cfg.url_fetch_timeout_sec)
        except ValueError as e:
            await status.edit_text(f"Не смог забрать ссылку: {e}")
            return
        lang = await user_lang(msg)
        if await answer_cached(msg, status, text, label, lang):
            return
        if not await take_quota(msg):
            await status.delete()
            return
        await status.edit_text("Страницу забрал, спрашиваю модель…")
        try:
            report = await pipe.run(text, lang)
        except RateLimitError:
            log.warning("analyze rate-limited (url)")
            await fail(msg, status, rate_limited=True)
            return
        except Exception:
            log.exception("analyze failed (url)")
            await fail(msg, status, rate_limited=False)
            return
        body, truncated = pipe.prepare(text)
        await finish(msg, report, body, label, truncated, status)

    @r.message(F.text)
    async def on_text(msg: Message) -> None:
        if not await guard(msg):
            return
        text = (msg.text or "").strip()
        body, truncated = pipe.prepare(text)
        if len(body) < 200:
            # короткие "привет" не тащим в модель, но и не молчим
            await msg.answer(
                "Текст слишком короткий для разбора (нужно от 200 символов). "
                "Пришли документ файлом, ссылкой или текстом подлиннее."
            )
            return
        lang = await user_lang(msg)
        if (hit := pipe.lookup(body, lang)) is not None:
            await finish(msg, hit, body, "текст из чата", truncated)
            return
        if not await take_quota(msg):
            return
        status = await msg.answer("Принял текст, разбираю…")
        try:
            report = await pipe.run(text, lang)
        except RateLimitError:
            log.warning("analyze rate-limited (text)")
            await fail(msg, status, rate_limited=True)
            return
        except Exception:
            log.exception("analyze failed (text)")
            await fail(msg, status, rate_limited=False)
            return
        await finish(msg, report, body, "текст из чата", truncated, status)

    return r
