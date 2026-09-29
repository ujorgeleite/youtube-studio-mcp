"""Estado persistido de um projeto: escolhas da pessoa sobrevivem a recarregar a página."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .schema import StoryReport, Take
from .serial import from_data, read_json, write_json

STAGE_PENDING = "pendente"
STAGE_MEDIA = "midia"
STAGE_SPEECH = "fala"
STAGE_VISION = "visao"
STAGE_READY = "pronto"
STAGE_FAILED = "falhou"
ANALYSIS_STAGES = (STAGE_MEDIA, STAGE_SPEECH, STAGE_VISION)


def default_output_dir(folder: str | Path) -> Path:
    source = Path(folder).expanduser().resolve()
    return source.parent / f"{source.name}__videocut"


@dataclass
class Layout:
    """Pastas de trabalho dentro da saída; originais nunca são escritos."""

    root: Path

    @property
    def project_file(self) -> Path:
        return self.root / "project.json"

    @property
    def cache(self) -> Path:
        return self.root / ".cache"

    @property
    def work(self) -> Path:
        return self.root / ".work"

    @property
    def thumbnails(self) -> Path:
        return self.work / "thumbs"

    @property
    def frames(self) -> Path:
        return self.work / "frames"

    @property
    def audio(self) -> Path:
        return self.work / "audio"

    @property
    def proxies(self) -> Path:
        return self.work / "proxies"

    @property
    def analysis(self) -> Path:
        return self.root / "analise"

    @property
    def deliveries(self) -> Path:
        return self.root / "entregas"

    def delivery(self, proposal_id: str, video_id: str) -> Path:
        return self.deliveries / f"proposta-{proposal_id}__{video_id}".lower()


@dataclass
class TakeStatus:
    stage: str = STAGE_PENDING
    fraction: float = 0.0
    error: str | None = None
    seconds: float = 0.0


@dataclass
class ReviewState:
    order: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    protected: list[str] = field(default_factory=list)
    active: str | None = None


@dataclass
class RenderRecord:
    video_id: str
    status: str
    seconds: float = 0.0
    duration_s: float = 0.0
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass
class Project:
    folder: str
    output_dir: str
    intention: str = ""
    format: str = "auto"
    model: str = ""
    target_minutes: float | None = None
    takes: list[Take] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    status: dict[str, TakeStatus] = field(default_factory=dict)
    report: StoryReport | None = None
    chosen: str | None = None
    review: dict[str, ReviewState] = field(default_factory=dict)
    renders: dict[str, RenderRecord] = field(default_factory=dict)
    updated_at: str = ""
    version: int = 1

    @property
    def layout(self) -> Layout:
        return Layout(Path(self.output_dir))

    @property
    def selected_takes(self) -> list[Take]:
        chosen = set(self.selected)
        return [take for take in self.takes if take.id in chosen]

    def take(self, take_id: str) -> Take | None:
        return next((take for take in self.takes if take.id == take_id), None)

    def save(self) -> Path:
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        return write_json(self.layout.project_file, self)

    @classmethod
    def open(cls, folder: str | Path, output_dir: str | Path | None = None) -> "Project":
        root = Path(output_dir).expanduser().resolve() if output_dir else default_output_dir(folder)
        data = read_json(Layout(root).project_file)
        if data is not None:
            project = from_data(cls, data)
            project.output_dir = str(root)
            return project
        return cls(folder=str(Path(folder).expanduser().resolve()), output_dir=str(root))
