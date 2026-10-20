from __future__ import annotations

import asyncio
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredDoc:
    label: str  # что показать в кнопке: имя файла, домен, "текст из чата"
    text: str  # уже нормализованный текст (возможно, обрезанный)
    truncated: bool  # хвост отрезали лимитом — честно скажем при цитатах


class DocStore:
    """Последние документы каждого юзера — для кнопки «показать пункт».
    В памяти: на Render диск эфемерный, после рестарта юзер разберет заново."""

    def __init__(self, max_users: int = 100, max_docs: int = 3) -> None:
        self.max_users = max_users
        self.max_docs = max_docs
        self._docs: OrderedDict[int, list[StoredDoc]] = OrderedDict()

    def save(self, user_id: int, label: str, text: str, truncated: bool = False) -> None:
        docs = [d for d in self._docs.get(user_id, []) if d.text != text]
        docs.append(StoredDoc(label=label[:40], text=text, truncated=truncated))
        self._docs[user_id] = docs[-self.max_docs :]
        self._docs.move_to_end(user_id)
        while len(self._docs) > self.max_users:
            self._docs.popitem(last=False)

    def list(self, user_id: int) -> list[StoredDoc]:
        return list(self._docs.get(user_id, []))


class Prefs:
    """Настройки юзера (пока только язык ответа). Та же sqlite, таблица своя."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()

    def _ensure(self, con: sqlite3.Connection) -> None:
        con.execute("CREATE TABLE IF NOT EXISTS prefs(user_id INTEGER PRIMARY KEY, lang TEXT)")

    async def get_lang(self, user_id: int) -> str:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, user_id)

    def _get_sync(self, user_id: int) -> str:
        path = Path(self.db_path)
        if str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            self._ensure(con)
            row = con.execute("SELECT lang FROM prefs WHERE user_id=?", (user_id,)).fetchone()
        finally:
            con.close()
        return row[0] if row and row[0] in ("ru", "doc") else "ru"

    async def set_lang(self, user_id: int, lang: str) -> None:
        if lang not in ("ru", "doc"):
            raise ValueError("язык либо ru, либо doc")
        async with self._lock:
            await asyncio.to_thread(self._set_sync, user_id, lang)

    def _set_sync(self, user_id: int, lang: str) -> None:
        path = Path(self.db_path)
        if str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        try:
            self._ensure(con)
            con.execute(
                "INSERT INTO prefs(user_id, lang) VALUES(?,?)"
                " ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang",
                (user_id, lang),
            )
            con.commit()
        finally:
            con.close()
