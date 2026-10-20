import time

from tos_bot.services.cache import ReportCache, doc_key


def test_key_ignores_whitespace():
    # ключ считаем уже от нормализованного текста (это делает Pipeline.normalize),
    # поэтому одинаковые документы с разными переносами дают один ключ
    raw_a = " ".join(["пункт 1. Штраф."] * 50)
    raw_b = "пункт  1.\nШтраф.\n" + "\n".join(["пункт 1. Штраф."] * 49)

    def norm(s: str) -> str:
        return " ".join(s.split())

    assert doc_key(norm(raw_a), "m") == doc_key(norm(raw_b), "m")


def test_key_separates_models():
    assert doc_key("x" * 300, "small") != doc_key("x" * 300, "large")


def test_put_get_roundtrip():
    c = ReportCache(max_entries=10, ttl_sec=60)
    assert c.get("k") is None
    c.put("k", "report")
    assert c.get("k") == "report"


def test_ttl_expires():
    c = ReportCache(max_entries=10, ttl_sec=0)
    c.put("k", "report")
    time.sleep(0.01)
    assert c.get("k") is None


def test_lru_evicts_oldest():
    c = ReportCache(max_entries=2, ttl_sec=60)
    c.put("a", "1")
    c.put("b", "2")
    c.put("c", "3")
    assert c.get("a") is None
    assert c.get("b") == "2"
    assert c.get("c") == "3"


def test_get_refreshes_lru():
    c = ReportCache(max_entries=2, ttl_sec=60)
    c.put("a", "1")
    c.put("b", "2")
    c.get("a")  # теперь самый старый — b
    c.put("c", "3")
    assert c.get("b") is None
    assert c.get("a") == "1"
