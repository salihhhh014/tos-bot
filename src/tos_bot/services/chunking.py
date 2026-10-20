from __future__ import annotations


def split_for_model(text: str, chunk_size: int = 12_000, overlap: int = 500) -> list[str]:
    """Режем по абзацам, чтобы пункт договора не рвать пополам."""
    paras = [" ".join(p.split()) for p in text.split("\n")]
    paras = [p for p in paras if p]
    if not paras:
        return []
    if sum(len(p) + 1 for p in paras) <= chunk_size:
        return ["\n".join(paras)]

    chunks: list[str] = []
    cur = ""
    for p in paras:
        # один абзац-простыня без переносов — режем жестко, с нахлестом
        while len(p) > chunk_size:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:chunk_size])
            p = p[chunk_size - overlap :]
        if len(cur) + len(p) + 1 > chunk_size and cur:
            chunks.append(cur)
            # хвост предыдущего тащим дальше — не теряем контекст на стыке
            cur = cur[-overlap:] + "\n" + p if overlap else p
        else:
            cur = (cur + "\n" + p) if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks
