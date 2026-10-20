from __future__ import annotations

import logging
import re

SECRET_RE = re.compile(r"(sk-[A-Za-z0-9-_]{4})[A-Za-z0-9-_]+|(\d{5,}:)[\w-]+")


class RedactFilter(logging.Filter):
    # режем токены в логах, проект же опенсорс — логи тоже могут утечь
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        record.msg = SECRET_RE.sub(r"\1***", msg)
        record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for handler in logging.root.handlers:
        handler.addFilter(RedactFilter())
