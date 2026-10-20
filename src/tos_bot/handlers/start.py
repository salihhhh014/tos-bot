from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from tos_bot.config import Settings
from tos_bot.handlers.analyze import analyze_router
from tos_bot.services.docstore import Prefs


def build_router(cfg: Settings) -> Router:
    root = Router()
    root.include_router(build_start_router(cfg))
    root.include_router(analyze_router(cfg))
    return root


def build_start_router(cfg: Settings) -> Router:
    r = Router()
    prefs = Prefs(cfg.quota_db_path)

    @r.message(CommandStart())
    async def cmd_start(msg: Message) -> None:
        await msg.answer(
            "Пришли мне ToS / оферту / политику конфиденциальности — "
            "файлом (pdf, docx, txt, фото скана), ссылкой или просто текстом.\n\n"
            "Верну: о чём документ, ключевые риски и подводные камни. "
            "Это не юрконсультация, только разбор текста."
        )

    @r.message(Command("help"))
    async def cmd_help(msg: Message) -> None:
        await msg.answer(
            "Как пользоваться:\n"
            "1. Кинь файл до 10 МБ (pdf, docx, txt) или фото скана\n"
            "2. Или ссылку на документ\n"
            "3. Или вставь текст сообщением\n\n"
            "Длинные документы режу на куски и собираю общий вывод.\n"
            "После разбора будет кнопка «Показать пункт дословно» — проверь любой тезис по тексту.\n\n"
            "Команды: /lang — язык ответа, /privacy — что происходит с документом, "
            "/cancel — сбросить текущий диалог.\n\n"
            "Это не юридическая консультация: перед подписанием важного документа "
            "покажите его юристу."
        )

    @r.message(Command("ping"))
    async def cmd_ping(msg: Message) -> None:
        await msg.answer("pong")

    @r.message(Command("privacy"))
    async def cmd_privacy(msg: Message) -> None:
        await msg.answer(
            "Что происходит с твоим документом:\n"
            "— текст уходит в Groq (Qwen) для анализа; скан или фото сначала распознаёт Mistral OCR;\n"
            "— это чужие серверы, без них бот не работает;\n"
            "— файлы не сохраняю, разбираю в памяти;\n"
            "— готовые разборы до недели лежат в кэше в памяти сервера;\n"
            "— в логах документы и токены не светятся;\n"
            "— рестарт стирает память и кэш.\n\n"
            "Не присылай документы с паспортными данными и всем, что не готов показать наружу. "
            "Бот не заменяет юриста."
        )

    @r.message(Command("cancel"))
    async def cmd_cancel(msg: Message, state: FSMContext) -> None:
        await state.clear()
        await msg.answer("Диалог сброшен. Пришли документ, ссылку или текст — начнём заново.")

    @r.message(Command("lang"))
    async def cmd_lang(msg: Message) -> None:
        user_id = msg.from_user.id if msg.from_user else 0
        cur = await prefs.get_lang(user_id)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=("✓ " if cur == "ru" else "") + "Всегда по-русски",
                        callback_data="lang:ru",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=("✓ " if cur == "doc" else "") + "На языке документа",
                        callback_data="lang:doc",
                    )
                ],
            ]
        )
        await msg.answer("На каком языке отвечать?", reply_markup=kb)

    @r.callback_query(F.data.startswith("lang:"))
    async def on_lang(cb: CallbackQuery) -> None:
        await cb.answer()
        lang = (cb.data or "").split(":")[-1]
        if lang not in ("ru", "doc"):
            return
        await prefs.set_lang(cb.from_user.id, lang)
        await cb.message.answer(  # type: ignore[union-attr]
            "Принято: отвечаю всегда по-русски."
            if lang == "ru"
            else "Принято: отвечаю на языке документа."
        )

    return r
