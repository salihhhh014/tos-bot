from __future__ import annotations

import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import Message


class ThrottleMiddleware(BaseMiddleware):
    """Простой антифлуд в памяти: один юзер — не чаще delay_sec."""

    def __init__(self, delay_sec: float = 1.0) -> None:
        self.delay = delay_sec
        self._last: dict[int, float] = defaultdict(float)

    async def __call__(self, handler, event: Message, data: dict):  # type: ignore[no-untyped-def]
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        if now - self._last[user_id] < self.delay:
            return None  # молча дропаем, без спама
        self._last[user_id] = now
        return await handler(event, data)
