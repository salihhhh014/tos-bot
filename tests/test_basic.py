from tos_bot.services.chunking import split_for_model
from tos_bot.utils.telegram import split_html


def test_split_short():
    assert split_for_model("a" * 100) == ["a" * 100]


def test_split_long_keeps_overlap():
    text = "абзац. " * 5000
    chunks = split_for_model(text, chunk_size=1000, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 1500 for c in chunks)


def test_telegram_split():
    text = "a\n" * 5000
    parts = split_html(text, 4000)
    assert len(parts) > 1
    assert all(len(p) <= 4000 for p in parts)
