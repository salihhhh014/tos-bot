from __future__ import annotations


def find_literal(doc: str, topic: str, window: int = 400) -> str | None:
    """Точное вхождение темы в документ. Возвращаем кусок с контекстом.
    None — не нашлось, тогда уже идем в модель."""
    needle = topic.casefold().strip()
    if len(needle) < 3:
        return None
    i = doc.casefold().find(needle)
    if i < 0:
        return None
    lo = max(0, i - window)
    hi = min(len(doc), i + len(topic) + window)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(doc) else ""
    return f"{prefix}{doc[lo:hi]}{suffix}"
