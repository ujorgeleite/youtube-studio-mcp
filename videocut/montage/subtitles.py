"""Legendas da montagem: palavras dos takes reposicionadas na timeline final."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.safety import write_text
from core.schema import SPEECH, EditPlan, Transcript

MAX_CUE_CHARS = 42
MAX_CUE_S = 3.5


@dataclass
class Cue:
    start_s: float
    end_s: float
    text: str


def timeline_words(plan: EditPlan, transcripts: dict[str, Transcript]) -> list[tuple[float, float, str]]:
    words = []
    for clip in plan.audio:
        transcript = transcripts.get(clip.take_id)
        if clip.role != SPEECH or transcript is None:
            continue
        for word in transcript.words:
            if word.start_s >= clip.source_in - 0.05 and word.end_s <= clip.source_out + 0.05:
                start = clip.timeline_in + max(0.0, word.start_s - clip.source_in)
                end = clip.timeline_in + min(clip.duration_s, word.end_s - clip.source_in)
                words.append((round(start, 3), round(end, 3), word.text))
    return sorted(words)


def build_cues(words: list[tuple[float, float, str]]) -> list[Cue]:
    cues: list[Cue] = []
    current: list[tuple[float, float, str]] = []

    def close() -> None:
        if current:
            cues.append(Cue(current[0][0], current[-1][1], " ".join(text for _, _, text in current)))
            current.clear()

    for word in words:
        text = " ".join(item[2] for item in [*current, word])
        if current and (len(text) > MAX_CUE_CHARS or word[1] - current[0][0] > MAX_CUE_S or word[0] - current[-1][1] > 0.7):
            close()
        current.append(word)
        if word[2].endswith((".", "!", "?", "…")):
            close()
    close()
    return cues


def _srt_time(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(plan: EditPlan, transcripts: dict[str, Transcript], destination: str | Path) -> Path:
    blocks = [f"{number}\n{_srt_time(cue.start_s)} --> {_srt_time(cue.end_s)}\n{cue.text}\n"
              for number, cue in enumerate(build_cues(timeline_words(plan, transcripts)), start=1)]
    return write_text(destination, "\n".join(blocks))
