from __future__ import annotations

import re

from .config import CutRules
from .schema import Cut, SpeechRegion, Word

SENTENCE_END = re.compile(r"[.!?…][\"”')\]]*$")


def _overlaps_protected(start: float, end: float, protected: list[SpeechRegion]) -> bool:
    return any(start < item.end_s and end > item.start_s for item in protected)


def cuts_from_words(words: list[Word], rules: CutRules, protected: list[SpeechRegion] | None = None) -> list[Cut]:
    """Só remove tempo entre palavras e mantém a pausa editorial configurada."""
    protected = protected or []
    candidates: list[Cut] = []
    for previous, following in zip(words, words[1:]):
        gap = following.start_s - previous.end_s
        after_sentence = bool(SENTENCE_END.search(previous.text))
        threshold = rules.pause_after_sentence_s if after_sentence else rules.pause_within_sentence_s
        if gap <= threshold:
            continue
        retained = rules.pause_after_sentence_s if after_sentence else rules.breath_padding_s
        start = previous.end_s + retained / 2
        end = following.start_s - retained / 2
        if end <= start or _overlaps_protected(start, end, protected):
            continue
        candidates.append(Cut(start, end, "fim_de_frase" if after_sentence else "pausa_na_frase", transcript_before=previous.text, transcript_after=following.text))

    accepted: list[Cut] = []
    last_keep_start = 0.0
    for cut in candidates:
        if cut.start_s - last_keep_start < rules.min_segment_s:
            continue
        accepted.append(cut)
        last_keep_start = cut.end_s
    return accepted
