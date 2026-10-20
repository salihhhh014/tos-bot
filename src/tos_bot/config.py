from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings сам подхватит .env, руками dotenv грузить не надо
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    # ключи называем OPENAI_*, но это любой OpenAI-совместимый гейт.
    # по умолчанию — Groq + Qwen (id модели сверь в их консоли)
    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="qwen/qwen3.8-27b", alias="OPENAI_MODEL")
    openai_base_url: str | None = Field(
        default="https://api.groq.com/openai/v1", alias="OPENAI_BASE_URL"
    )

    # запасной провайдер на случай 429/падения основного. пусто = выключен.
    # например Groq: base https://api.groq.com/openai/v1, модель смотри в их консоли
    fallback_api_key: SecretStr = Field(default=SecretStr(""), alias="FALLBACK_API_KEY")
    fallback_base_url: str = Field(default="", alias="FALLBACK_BASE_URL")
    fallback_model: str = Field(default="", alias="FALLBACK_MODEL")

    # пусто = пускать всех, иначе "123,456"
    allowed_user_ids: str = Field(default="", alias="ALLOWED_USER_IDS")

    max_doc_chars: int = Field(default=60_000, alias="MAX_DOC_CHARS")
    max_file_mb: int = Field(default=10, alias="MAX_FILE_MB")
    url_fetch_timeout_sec: int = Field(default=15, alias="URL_FETCH_TIMEOUT_SEC")

    # сколько кусков длинного документа разбирать параллельно.
    # бесплатные тиры режут токены в минуту — параллельность выше 2 их сносит в 429
    chunk_concurrency: int = Field(default=2, alias="CHUNK_CONCURRENCY")

    # мягкий дневной лимит разборов на юзера. 0 = без лимита
    daily_limit_per_user: int = Field(default=30, alias="DAILY_LIMIT_PER_USER")
    quota_db_path: str = Field(default="data/quota.db", alias="QUOTA_DB_PATH")

    # OCR сканов. Если задан OCR_API_KEY, по умолчанию используется Mistral API.
    # Если ключ пуст — пробуем OPENAI_* (сработает, только если это Mistral).
    # OCR_BASE_URL нужен, только если у вас свой прокси/эндпоинт Mistral.
    ocr_enabled: bool = Field(default=True, alias="OCR_ENABLED")
    ocr_model: str = Field(default="mistral-ocr-latest", alias="OCR_MODEL")
    ocr_api_key: SecretStr = Field(default=SecretStr(""), alias="OCR_API_KEY")
    ocr_base_url: str = Field(default="", alias="OCR_BASE_URL")
    ocr_timeout_sec: int = Field(default=90, alias="OCR_TIMEOUT_SEC")

    # кэш готовых разборов: сколько держать и как долго (часов)
    cache_max_entries: int = Field(default=200, alias="CACHE_MAX_ENTRIES")
    cache_ttl_hours: int = Field(default=168, alias="CACHE_TTL_HOURS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def allowed_ids(self) -> set[int]:
        out: set[int] = set()
        for part in self.allowed_user_ids.split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out


def load_config() -> Settings:
    # валидация падает сразу, если нет токена — так и должно быть
    return Settings()  # type: ignore[call-arg]


def redact(value: str) -> str:
    # для логов: светим только хвост, остальное прячем
    if len(value) <= 8:
        return "***"
    return "***" + value[-4:]
