# ToS Bot — читаем мелкий шрифт за тебя

[![CI](https://github.com/salihhhh014/tos-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/salihhhh014/tos-bot/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Telegram-бот для быстрого разбора **ToS, оферт и политик конфиденциальности**.
Принимает PDF, DOCX, TXT, фото скана, ссылку или текст и возвращает:

- о чём документ;
- ключевые риски и подводные камни;
- оценку 1–5;
- кнопку **«Показать пункт дословно»** — любой тезис можно сверить с исходником.

Бот не заменяет юриста и прямо пишет об этом в каждом ответе.

Демо-бот: [@tos_reader_bot](https://t.me/tos_reader_bot) — отвечает, пока запущен воркер
(локально или на Render).

Подробный разбор задачи и решения: [docs/CASE_STUDY.md](docs/CASE_STUDY.md).

## Стек

- Python 3.12, aiogram 3
- Groq + Qwen как основной OpenAI-совместимый провайдер
- опциональный fallback-провайдер на случай 429/сбоя
- Mistral OCR для сканов и фото
- SQLite для квот и языковых настроек
- pytest + ruff + GitHub Actions

## Что под капотом

- **Map-reduce для длинных документов.** Текст режется на куски, каждый разбирается отдельно,
  затем результаты склеиваются в один отчёт.
- **Кэш по sha256.** Повторный документ не тратит токены.
- **Дневная квота на пользователя.** Защита от случайного и злонамеренного расхода API.
- **Fallback-провайдер.** 429 и сетевые ошибки не роняют разбор.
- **Дословные цитаты.** Точное совпадение ищется в тексте бесплатно, без модели.
- **SSRF-защита.** Проверка схемы, порта, DNS-ответов и каждого редиректа.
- **Redaction логов.** Токены не попадают в логи.
- **Graceful shutdown.** Сессия Telegram закрывается корректно.

## Команды

| Команда | Что делает |
|---|---|
| `/start` | приветствие и краткая инструкция |
| `/help` | как пользоваться |
| `/lang` | язык ответа: русский или язык документа |
| `/privacy` | какие данные и куда уходят |
| `/cancel` | сбросить текущий диалог |
| `/ping` | проверка, что бот жив |

## Пример работы

```text
Пользователь: [отправляет offer.pdf]

Бот:
О чём документ
Договор публичной оферты на оказание услуг...

Главное за 30 секунд
• Исполнитель может менять условия в одностороннем порядке.
• Возврат возможен только до начала оказания услуги.
• Споры рассматриваются по месту регистрации исполнителя.

Оценка: 3/5

[ Показать пункт дословно ]
```

## Запуск

Нужен Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

В `.env` минимум:

```dotenv
BOT_TOKEN=...
OPENAI_API_KEY=...          # ключ Groq (или другого OpenAI-совместимого API)
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=qwen/qwen3.8-27b
```

Запуск:

```powershell
.\.venv\Scripts\python.exe -m tos_bot
```

или после установки:

```powershell
tos-bot
```

## OCR для сканов и фото

Обычные PDF/DOCX/TXT и ссылки работают без OCR. Сканы и фото требуют Mistral:

```dotenv
OCR_ENABLED=1
OCR_API_KEY=mistral-...
# OCR_BASE_URL можно не задавать — по умолчанию https://api.mistral.ai/v1
```

Если ключа нет:

- бот продолжит разбирать текстовые документы;
- на скан или фото ответит понятной ошибкой;
- полностью отключить OCR можно через `OCR_ENABLED=0`.

## Настройки

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BOT_TOKEN` | — | токен от @BotFather |
| `OPENAI_API_KEY` | — | ключ основного LLM-провайдера |
| `OPENAI_BASE_URL` | Groq | OpenAI-совместимый endpoint |
| `OPENAI_MODEL` | `qwen/qwen3.8-27b` | id модели |
| `FALLBACK_*` | пусто | запасной провайдер |
| `ALLOWED_USER_IDS` | пусто | белый список Telegram ID через запятую; пусто = все |
| `MAX_DOC_CHARS` | `60000` | сколько символов документа анализировать |
| `MAX_FILE_MB` | `10` | максимальный размер файла |
| `URL_FETCH_TIMEOUT_SEC` | `15` | таймаут загрузки ссылки |
| `CHUNK_CONCURRENCY` | `2` | параллельных кусков длинного документа |
| `DAILY_LIMIT_PER_USER` | `30` | разборов в день; `0` = без лимита |
| `QUOTA_DB_PATH` | `data/quota.db` | SQLite с квотами и настройками |
| `CACHE_MAX_ENTRIES` | `200` | размер кэша |
| `CACHE_TTL_HOURS` | `168` | время жизни кэша |
| `OCR_ENABLED` | `1` | включить распознавание сканов |
| `OCR_MODEL` | `mistral-ocr-latest` | модель OCR |
| `OCR_API_KEY` | пусто | ключ Mistral |
| `OCR_BASE_URL` | Mistral | свой endpoint OCR |
| `OCR_TIMEOUT_SEC` | `90` | таймаут OCR |
| `LOG_LEVEL` | `INFO` | уровень логов |

## Архитектура

```text
src/tos_bot/
  __main__.py        # вход, polling, graceful shutdown
  config.py          # настройки из env (pydantic-settings)
  bot.py             # Bot + Dispatcher + MemoryStorage
  handlers/
    start.py         # /start /help /lang /privacy /cancel /ping
    analyze.py       # файлы / фото / ссылки / текст
    quote.py         # FSM-диалог «показать пункт дословно»
  middlewares/
    throttle.py      # антифлуд
  services/
    analyzer.py      # prepare -> кэш -> chunk -> LLM -> merge
    llm.py           # OpenAI-совместимые клиенты + fallback
    ocr.py           # Mistral OCR
    documents.py     # pdf / docx / txt / jpg / png + фото Telegram
    urls.py          # безопасная загрузка страниц (SSRF)
    chunking.py      # нарезка длинных документов
    quota.py         # дневной лимит (SQLite)
    cache.py         # in-memory кэш отчётов
    docstore.py      # последние документы + язык (SQLite)
    quotes.py        # дословный поиск
  prompts/
    tos_audit.py     # системный промпт и промпты цитат
  utils/
    telegram.py      # нарезка под лимит 4096
    logging.py       # redaction секретов
```

Поток разбора:

```text
пользователь -> хендлер (валидация) -> prepare -> кэш -> квота
-> chunk -> LLM (temperature=0) -> merge -> ответ + кнопка цитаты
```

Поток цитаты:

```text
кнопка -> выбор документа -> тема -> точный поиск (бесплатно)
-> не найдено: LLM (за квоту) -> дословный фрагмент или «нет в документе»
```

## Промпт и галлюцинации

Промпт лежит в `src/tos_bot/prompts/tos_audit.py`:

- только текст из `<document>`;
- нет в тексте — «в документе нет информации»;
- цитаты только дословно;
- `temperature=0`;
- мусорный текст — честно сказать;
- в конце — дисклеймер «не юрконсультация».

Даже с этим модель может ошибаться. Поэтому главная защита — кнопка дословной цитаты.

## Ограничения

- PDF/DOCX/TXT/MD/JPG/PNG до 10 МБ; PDF до 100 страниц.
- Анализируются первые `MAX_DOC_CHARS` символов; если документ длиннее, бот предупреждает.
- Сканы и фото распознаёт Mistral OCR — символы, суммы и сроки нужно сверять с оригиналом.
- Кнопка цитат помнит последние 3 документа и только пока процесс жив.
- Страницы с JS (SPA, закрытые кабинеты) не загружаются.
- Язык ответа по умолчанию русский; `/lang` переключает на язык документа.
- Квота и настройки в SQLite. На Render free-плане диск эфемерный — счётчики обнулятся
  после рестарта. Для строгого учёта нужен Persistent Disk или внешняя БД.

## Безопасность

- секреты только в `.env`; в репозитории только `.env.example`;
- токены в логах затираются, полный текст документов не логируется;
- файлы проверяются по расширению и размеру, разбираются в памяти;
- ссылки: только http(s), порты 80/443, все DNS-ответы должны быть публичными,
  каждый редирект проверяется отдельно, лимит 5 редиректов, 2 МБ, таймаут 15 секунд;
- цитаты экранируются через `html.escape`;
- антифлуд 1 секунда на пользователя;
- опциональный белый список `ALLOWED_USER_IDS`;
- дневная квота; при ошибке модели попытка возвращается;
- зависимости ставятся из `pyproject.toml`, dev-инструменты — `ruff`, `pytest`, `pytest-cov`.

## Тесты и CI

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\ruff.exe format --check src tests
```

GitHub Actions прогоняет линтер и тесты на каждый push и pull request.

## Docker

```bash
docker build -t tos-bot .
docker run --rm --env-file .env tos-bot
```

Для сохранения квоты при перезапуске подключите volume:

```bash
docker run --rm --env-file .env -v tos-data:/app/data tos-bot
```

## Деплой на Render

В репозитории есть `render.yaml`. Нужен **Background Worker** (бот работает на polling).

- Build Command: `pip install -e .`
- Start Command: `python -m tos_bot`
- `PYTHON_VERSION=3.12.9`
- секреты `BOT_TOKEN`, `OPENAI_API_KEY`, `OCR_API_KEY` — в Environment, не в коде
- `ALLOWED_USER_IDS` — свой Telegram ID, если не хотите пускать всех

Free-план: `data/quota.db` обнулится при редеплое. Для строгого учёта добавьте
Persistent Disk (пример закомментирован в `render.yaml`) или внешнюю БД.

## Лицензия

MIT. См. [LICENSE](LICENSE).
