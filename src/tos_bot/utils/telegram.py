from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup, Message

TAG_RE = re.compile(r"</?(?:b|i|u|s|code|pre)[^>]*>", re.IGNORECASE)


def split_html(text: str, limit: int = 4000) -> list[str]:
    """Режем ответ модели под лимит телеги, по возможности по переносам."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > limit and cur:
            out.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        out.append(cur)
    return out


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text)


async def answer_long(
    msg: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    limit: int = 4000,
) -> None:
    """Шлем длинный HTML-текст кусками. Если кусок не влез в разметку
    (разрез попал внутрь тега) — телега вернет 400, тогда шлем как есть,
    без тегов. Лучше голый текст, чем ничего."""
    chunks = split_html(text, limit)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await msg.answer(chunk, reply_markup=markup)
        except TelegramBadRequest:
            await msg.answer(strip_tags(chunk), reply_markup=markup)
