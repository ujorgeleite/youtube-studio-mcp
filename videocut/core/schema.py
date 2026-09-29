"""Modelo do domínio: fatos observados nos takes, propostas editoriais e plano de montagem.

Fatos (transcrição, observação visual) nunca carregam interpretação; propostas só
citam fatos por meio de `Evidence`, que o validador confere contra o inventário.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SPEECH = "fala"
ACTION = "acao"
BROLL = "apoio"
PROBLEM = "problema"
MOMENT_KINDS = (SPEECH, ACTION, BROLL, PROBLEM)

BEAT_ROLES = ("gancho", "contexto", "desenvolvimento", "mensagem", "conclusao", "apoio")
CRITERIA = {
    "mensagem": "Mensagem central",
    "abertura": "Abertura",
    "desenvolvimento": "Desenvolvimento",
    "encerramento": "Encerramento",
    "cobertura_visual": "Cobertura visual",
    "independencia": "Vídeos independentes",
}
CRITERION_OK, CRITERION_REVIEW, CRITERION_MISSING = "ok", "revisar", "falta"

VERDICT_SINGLE = "um_video"
VERDICT_MULTIPLE = "varios_videos"
VERDICT_INSUFFICIENT = "falta_material"


@dataclass
class Take:
    id: str
    path: str
    name: str
    duration_s: float
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = True
    thumbnail: str | None = None
    proxy: str | None = None

    @property
    def analysis_path(self) -> str:
        """Proxy da câmera (.LRF) para ver e analisar; o render sempre usa `path`."""
        return self.proxy or self.path


@dataclass(frozen=True)
class Word:
    start_s: float
    end_s: float
    text: str
    confidence: float | None = None


@dataclass
class Sentence:
    start_s: float
    end_s: float
    text: str


@dataclass
class Transcript:
    take_id: str
    language: str = "pt"
    words: list[Word] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)

    def text_between(self, start_s: float, end_s: float) -> str:
        return " ".join(word.text for word in self.words if word.start_s >= start_s - 0.05 and word.end_s <= end_s + 0.05)


@dataclass
class VisualObservation:
    take_id: str
    start_s: float
    end_s: float
    description: str
    action: str = ""
    setting: str = ""
    shot: str = ""
    subjects: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    interest: float = 0.5
    usable_as_broll: bool = False
    detail_pass: bool = False


@dataclass
class Moment:
    """Trecho contínuo de um take com o que foi dito e o que aparece."""

    id: str
    take_id: str
    start_s: float
    end_s: float
    kind: str
    speech: str = ""
    visual: str = ""
    issues: list[str] = field(default_factory=list)
    interest: float = 0.5

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Inventory:
    takes: list[Take] = field(default_factory=list)
    transcripts: dict[str, Transcript] = field(default_factory=dict)
    observations: list[VisualObservation] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    def take(self, take_id: str) -> Take | None:
        return next((take for take in self.takes if take.id == take_id), None)


@dataclass
class Evidence:
    take_id: str
    start_s: float
    end_s: float
    quote: str = ""
    observation: str = ""


@dataclass
class Overlay:
    """Imagem de apoio sobre a fala do bloco; `at_s` é relativo ao início do bloco."""

    take_id: str
    start_s: float
    end_s: float
    at_s: float = 0.0

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Beat:
    id: str
    title: str
    role: str
    take_id: str
    start_s: float
    end_s: float
    reason: str = ""
    audio: str = SPEECH
    overlays: list[Overlay] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    chapter: str = ""

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class StoryVideo:
    id: str
    title: str
    message: str = ""
    beats: list[Beat] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return sum(beat.duration_s for beat in self.beats)


@dataclass
class Criterion:
    key: str
    status: str
    detail: str = ""
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def label(self) -> str:
        return CRITERIA.get(self.key, self.key)


@dataclass
class Gap:
    description: str
    suggestion: str = ""


@dataclass
class Proposal:
    id: str
    title: str
    summary: str = ""
    recommended: bool = False
    partial: bool = False
    videos: list[StoryVideo] = field(default_factory=list)
    criteria: list[Criterion] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def multiple(self) -> bool:
        return len(self.videos) > 1

    @property
    def review_points(self) -> int:
        return sum(1 for criterion in self.criteria if criterion.status != CRITERION_OK) + len(self.gaps)


@dataclass
class StoryReport:
    verdict: str
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    intention_check: str = ""
    proposals: list[Proposal] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)

    def proposal(self, proposal_id: str) -> Proposal | None:
        return next((proposal for proposal in self.proposals if proposal.id == proposal_id), None)


@dataclass
class OutputFormat:
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    sample_rate: int = 48000
    audio_fade_s: float = 0.08


@dataclass
class VideoClip:
    take_id: str
    source_in: float
    source_out: float
    timeline_in: float
    beat_id: str
    broll: bool = False

    @property
    def duration_s(self) -> float:
        return self.source_out - self.source_in


@dataclass
class AudioClip:
    take_id: str
    source_in: float
    source_out: float
    timeline_in: float
    beat_id: str
    role: str = SPEECH
    gain_db: float = 0.0
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0

    @property
    def duration_s(self) -> float:
        return self.source_out - self.source_in


@dataclass
class EditPlan:
    """Decisão de montagem executável: imagem e áudio em faixas independentes."""

    proposal_id: str
    video_id: str
    title: str
    sources: dict[str, str] = field(default_factory=dict)
    format: OutputFormat = field(default_factory=OutputFormat)
    video: list[VideoClip] = field(default_factory=list)
    audio: list[AudioClip] = field(default_factory=list)
    version: int = 1

    @property
    def main_track(self) -> list[VideoClip]:
        return [clip for clip in self.video if not clip.broll]

    @property
    def broll_track(self) -> list[VideoClip]:
        return [clip for clip in self.video if clip.broll]

    @property
    def duration_s(self) -> float:
        return max((clip.timeline_in + clip.duration_s for clip in self.main_track), default=0.0)
