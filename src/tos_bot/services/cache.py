from __future__ import annotations

import hashlib
import time
from collections import OrderedDict


def doc_key(normalized_text: str, model: str, lang: str = "ru") -> str:
    # модель и язык входят в ключ — сменил одно, старые разборы не подсунутся
    return hashlib.sha256(f"{model}:{lang}:{normalized_text}".encode()).hexdigest()


class ReportCache:
    """Кэш готовых разборов в памяти. На Render диск эфемерный,
    поэтому файлы для кэша не годятся — держим в процессе."""

    def __init__(self, max_entries: int = 200, ttl_sec: int = 7 * 24 * 3600) -> None:
        self.max_entries = max_entries
        self.ttl = ttl_sec
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, key: str) -> str | None:
        hit = self._items.get(key)
        if hit is None:
            return None
        expires, report = hit
        if time.monotonic() >= expires:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return report

    def put(self, key: str, report: str) -> None:
        self._items[key] = (time.monotonic() + self.ttl, report)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
