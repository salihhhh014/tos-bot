from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Quota:
    """Дневной лимит разборов на юзера. Храним в sqlite — без редиса."""

    def __init__(self, db_path: str, daily_limit: int) -> None:
        self.db_path = db_path
        self.daily_limit = daily_limit
        self._lock = asyncio.Lock()

    def _today(self) -> str:
        return datetime.now(UTC).date().isoformat()

    def _hit_sync(self, user_id: int) -> tuple[bool, int]:
        # синхронное ядро — гоняем в to_thread, чтобы не стопорить loop
        path = Path(self.db_path)
        if str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS quota"
                "(user_id INTEGER, day TEXT, count INTEGER,"
                " PRIMARY KEY (user_id, day))"
            )
            day = self._today()
            row = con.execute(
                "SELECT count FROM quota WHERE user_id=? AND day=?", (user_id, day)
            ).fetchone()
            used = row[0] if row else 0
            if used >= self.daily_limit:
                return False, 0
            con.execute(
                "INSERT INTO quota(user_id, day, count) VALUES(?,?,1)"
                " ON CONFLICT(user_id, day) DO UPDATE SET count=count+1",
                (user_id, day),
            )
            con.commit()
            return True, self.daily_limit - used - 1
        finally:
            con.close()

    async def check_and_hit(self, user_id: int) -> tuple[bool, int]:
        # 0 в конфиге = лимит выключен
        if self.daily_limit <= 0:
            return True, -1
        async with self._lock:
            return await asyncio.to_thread(self._hit_sync, user_id)

    async def refund(self, user_id: int) -> None:
        # модель упала — попытку не засчитываем, счетчик назад
        if self.daily_limit <= 0:
            return
        async with self._lock:
            await asyncio.to_thread(self._refund_sync, user_id)

    def _refund_sync(self, user_id: int) -> None:
        path = Path(self.db_path)
        if str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS quota"
                "(user_id INTEGER, day TEXT, count INTEGER,"
                " PRIMARY KEY (user_id, day))"
            )
            con.execute(
                "UPDATE quota SET count=count-1 WHERE user_id=? AND day=? AND count>0",
                (user_id, self._today()),
            )
            con.commit()
        finally:
            con.close()
