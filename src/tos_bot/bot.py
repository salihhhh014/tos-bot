from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from tos_bot.config import Settings
from tos_bot.handlers import build_router
from tos_bot.middlewares.throttle import ThrottleMiddleware

log = logging.getLogger(__name__)


def make_bot(token: object) -> Bot:
    raw = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
    return Bot(
        token=raw,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(cfg: Settings) -> Dispatcher:
    # MemoryStorage для FSM (диалог «показать пункт»). стейты живут в памяти —
    # рестарт их сбросит, юзер просто нажмет кнопку заново
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(ThrottleMiddleware(delay_sec=1.0))
    dp.include_router(build_router(cfg))
    return dp
