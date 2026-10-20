from __future__ import annotations

import html
import logging
from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from openai import RateLimitError

from tos_bot.services.analyzer import Pipeline
from tos_bot.services.docstore import DocStore, Prefs
from tos_bot.services.quotes import find_literal
from tos_bot.utils.telegram import answer_long

log = logging.getLogger(__name__)

TG_LIMIT = 4000


class QuoteStates(StatesGroup):
    waiting_topic = State()


def quote_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать пункт дословно", callback_data="quote:ask")]
        ]
    )


def register_quote_handlers(
    r: Router,
    pipe: Pipeline,
    store: DocStore,
    prefs: Prefs,
    guard: Callable[[Message], Awaitable[bool]],
    take_quota: Callable[[Message], Awaitable[bool]],
    refund_quota: Callable[[Message], Awaitable[None]],
) -> None:
    @r.callback_query(F.data == "quote:ask")
    async def on_quote_ask(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        docs = store.list(cb.from_user.id)
        if not docs:
            await cb.message.answer("Сначала кинь документ — показывать нечего.")  # type: ignore[union-attr]
            return
        if len(docs) == 1:
            await state.set_state(QuoteStates.waiting_topic)
            await state.update_data(doc_idx=0)
            await cb.message.answer(  # type: ignore[union-attr]
                "Про какой пункт показать? Напиши тему одной фразой, например: возврат денег"
            )
            return
        # документов несколько — пусть выберет, иначе цитата будет не из того
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=d.label or f"документ {i + 1}", callback_data=f"quote:doc:{i}"
                    )
                ]
                for i, d in enumerate(docs)
            ]
        )
        await cb.message.answer("В каком документе искать?", reply_markup=kb)  # type: ignore[union-attr]

    @r.callback_query(F.data.startswith("quote:doc:"))
    async def on_quote_doc(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        docs = store.list(cb.from_user.id)
        try:
            idx = int((cb.data or "").split(":")[-1])
            docs[idx]
        except (ValueError, IndexError):
            await cb.message.answer("Такого документа уже нет. Разбери его заново.")  # type: ignore[union-attr]
            return
        await state.set_state(QuoteStates.waiting_topic)
        await state.update_data(doc_idx=idx)
        await cb.message.answer(  # type: ignore[union-attr]
            "Про какой пункт показать? Напиши тему одной фразой, например: возврат денег"
        )

    @r.message(QuoteStates.waiting_topic)
    async def on_topic(msg: Message, state: FSMContext) -> None:
        data = await state.get_data()
        await state.clear()
        if not await guard(msg):
            return
        topic = (msg.text or "").strip()
        if len(topic) < 3:
            await msg.answer(
                "Слишком коротко. Напиши тему, например: передача данных третьим лицам"
            )
            return
        user_id = msg.from_user.id if msg.from_user else 0
        docs = store.list(user_id)
        idx = data.get("doc_idx", len(docs) - 1)
        if not docs or idx >= len(docs):
            await msg.answer("Документы потерялись (перезапуск сбросил память). Кинь еще раз.")
            return
        doc = docs[idx]

        # точное вхождение — бесплатно, в модель не ходим
        if (hit := find_literal(doc.text, topic)) is not None:
            await msg.answer(f"Дословно из документа:\n\n<code>{html.escape(hit)}</code>")
            return

        # не нашлось буквально — просит модель вытянуть цитату. это уже за квоту
        if not await take_quota(msg):
            return
        status = await msg.answer("Ищу пункт…")
        try:
            lang = await prefs.get_lang(user_id)
            quote = await pipe.extract(doc.text, topic, lang)
        except RateLimitError:
            log.warning("extract rate-limited")
            await refund_quota(msg)
            await status.edit_text(
                "Модель уперлась в свой лимит (429). Подожди минуту — попытка не засчитана."
            )
            return
        except Exception:
            log.exception("extract failed")
            await refund_quota(msg)
            await status.edit_text(
                "Упал на стороне модели, попробуй чуть позже. Попытка не засчитана."
            )
            return
        if quote is None:
            tail = " Но помни: я видел только начало документа." if doc.truncated else ""
            await status.edit_text(f"В документе про это ничего нет.{tail}")
            return
        await status.delete()
        await answer_long(
            msg, f"Дословно из документа:\n\n<code>{html.escape(quote)}</code>", limit=TG_LIMIT
        )
