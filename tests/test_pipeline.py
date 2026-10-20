import asyncio
from types import SimpleNamespace

from tos_bot.prompts.tos_audit import build_extract_prompt, build_full_prompt
from tos_bot.services.analyzer import Pipeline
from tos_bot.services.cache import ReportCache, doc_key
from tos_bot.services.docstore import Prefs


def make_pipe(**kw):
    # клиент не трогаем — для prepare/lookup сеть не нужна
    p = Pipeline.__new__(Pipeline)
    p.cfg = SimpleNamespace(max_doc_chars=1000, openai_model="m", **kw)
    p.cache = ReportCache(max_entries=10, ttl_sec=60)
    return p


def test_prepare_short_not_truncated():
    body, cut = make_pipe().prepare("текст " * 10)
    assert cut is False
    assert body == " ".join(("текст " * 10).split())


def test_prepare_long_truncated():
    body, cut = make_pipe().prepare("слово " * 5000)
    assert cut is True
    assert len(body) == 1000


def test_lookup_separates_langs():
    p = make_pipe()
    body, _ = p.prepare("документ " * 100)
    p.cache.put(doc_key(body, "m", "ru"), "ru-report")
    assert p.lookup(body, "ru") == "ru-report"
    assert p.lookup(body, "doc") is None


def test_full_prompt_lang():
    assert "русский" in build_full_prompt("doc")
    assert "язык документа" in build_full_prompt("doc", "doc")


def test_extract_prompt_lang():
    assert "русский" in build_extract_prompt("doc", "topic")
    assert "язык документа" in build_extract_prompt("doc", "topic", "doc")


def test_prefs_default_ru(tmp_path):
    pf = Prefs(str(tmp_path / "p.db"))
    assert asyncio.run(pf.get_lang(1)) == "ru"


def test_prefs_roundtrip(tmp_path):
    pf = Prefs(str(tmp_path / "p.db"))
    asyncio.run(pf.set_lang(1, "doc"))
    assert asyncio.run(pf.get_lang(1)) == "doc"
    asyncio.run(pf.set_lang(1, "ru"))
    assert asyncio.run(pf.get_lang(1)) == "ru"


def test_prefs_rejects_garbage(tmp_path):
    import pytest

    pf = Prefs(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        asyncio.run(pf.set_lang(1, "de"))
