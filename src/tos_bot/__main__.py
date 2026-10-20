"""Точка входа: python -m tos_bot."""

import asyncio
import logging

from tos_bot.bot import build_dispatcher, make_bot
from tos_bot.config import load_config
from tos_bot.utils.logging import setup_logging


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    bot = make_bot(cfg.bot_token)
    dp = build_dispatcher(cfg)
    log = logging.getLogger(__name__)
    log.info("bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        log.info("bot stopped")


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
