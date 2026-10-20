from tos_bot.prompts.tos_audit import build_extract_prompt
from tos_bot.services.docstore import DocStore
from tos_bot.services.quotes import find_literal

DOC = "Пункт 5. Возврат денег возможен в течение 14 дней. " * 20


def test_literal_found_with_context():
    hit = find_literal(DOC, "возврат денег")
    assert hit is not None
    assert "Возврат денег" in hit


def test_literal_case_insensitive():
    assert find_literal(DOC, "ВОЗВРАТ ДЕНЕГ") is not None


def test_literal_missing():
    assert find_literal(DOC, "передача данных марсианам") is None


def test_literal_too_short():
    assert find_literal(DOC, "а") is None


def test_literal_edges_no_crash():
    assert find_literal("коротко возврат денег конец", "возврат денег") is not None


def test_docstore_roundtrip():
    s = DocStore()
    assert s.list(1) == []
    s.save(1, "договор.pdf", "doc")
    docs = s.list(1)
    assert len(docs) == 1
    assert docs[0].label == "договор.pdf"
    assert docs[0].text == "doc"


def test_docstore_keeps_last_three():
    s = DocStore(max_docs=3)
    for i in range(5):
        s.save(1, f"doc{i}", f"text{i}")
    assert [d.label for d in s.list(1)] == ["doc2", "doc3", "doc4"]


def test_docstore_dedupes_same_text():
    s = DocStore()
    s.save(1, "a.pdf", "same")
    s.save(1, "b.pdf", "same")
    docs = s.list(1)
    assert len(docs) == 1
    assert docs[0].label == "b.pdf"


def test_docstore_isolates_users():
    s = DocStore()
    s.save(1, "a", "x")
    assert s.list(2) == []


def test_extract_prompt_has_doc_and_topic():
    p = build_extract_prompt("текст документа", "возврат")
    assert "текст документа" in p
    assert "возврат" in p
    assert "НЕТ" in p
