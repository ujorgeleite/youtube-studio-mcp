from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Interval:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    def as_dict(self) -> dict[str, float]:
        return {"start_s": round(self.start_s, 3), "end_s": round(self.end_s, 3)}


@dataclass
class SilenceSettings:
    noise_db: float = -35.0
    min_silence_s: float = 0.35
    padding_before_s: float = 0.08
    padding_after_s: float = 0.15
    dialogue_merge_gap_s: float = 2.5
    cautious_internal_threshold_s: float = 1.2
    cautious_preserved_pause_s: float = 0.35


@dataclass
class VideoAnalysis:
    source: str
    duration_s: float
    silences: list[Interval]
    waveform: list[float] = field(default_factory=list)
    settings: SilenceSettings = field(default_factory=SilenceSettings)

    def as_dict(self) -> dict:
        return {
            "version": 1,
            "source": self.source,
            "duration_s": round(self.duration_s, 3),
            "settings": asdict(self.settings),
            "silences": [item.as_dict() for item in self.silences],
            "waveform": self.waveform,
        }

