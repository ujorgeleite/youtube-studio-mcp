from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Word:
    start_s: float
    end_s: float
    text: str
    confidence: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SpeechRegion:
    start_s: float
    end_s: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Cut:
    start_s: float
    end_s: float
    reason: str
    protected: bool = False
    transcript_before: str = ""
    transcript_after: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CutPlan:
    source: str
    duration_s: float
    preset: str
    words: list[Word] = field(default_factory=list)
    cuts: list[Cut] = field(default_factory=list)
    protected_pauses: list[SpeechRegion] = field(default_factory=list)
    retakes: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "version": 2,
            "source": self.source,
            "duration_s": self.duration_s,
            "preset": self.preset,
            "words": [word.as_dict() for word in self.words],
            "cuts": [cut.as_dict() for cut in self.cuts],
            "protected_pauses": [pause.as_dict() for pause in self.protected_pauses],
            "retakes": self.retakes,
        }
