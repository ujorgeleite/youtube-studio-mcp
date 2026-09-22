from __future__ import annotations

from rapidfuzz.fuzz import ratio

from .schema import Word


def sentence_ranges(words: list[Word]) -> list[tuple[int, int, str]]:
    """Agrupa palavras por pontuação, preservando os índices para revisão."""
    ranges: list[tuple[int, int, str]] = []
    start = 0
    for index, word in enumerate(words):
        if word.text.rstrip().endswith((".", "!", "?", "…")):
            ranges.append((start, index, " ".join(item.text for item in words[start:index + 1])))
            start = index + 1
    if start < len(words):
        ranges.append((start, len(words) - 1, " ".join(item.text for item in words[start:])))
    return ranges


def detect_retakes(words: list[Word], similarity: float = 88.0) -> list[dict]:
    """Marca takes repetidos próximos; mantém sempre o último para revisão."""
    sentences = sentence_ranges(words)
    results = []
    for prior, current in zip(sentences, sentences[1:]):
        score = ratio(prior[2].lower(), current[2].lower())
        if score < similarity:
            continue
        start, end = words[prior[0]].start_s, words[prior[1]].end_s
        results.append({
            "start_s": round(start, 3), "end_s": round(end, 3),
            "kept_take_start_s": round(words[current[0]].start_s, 3),
            "text": prior[2], "kept_text": current[2], "similarity": round(score, 1),
            "reason": "retake_repetido", "selected": True,
        })
    return results
