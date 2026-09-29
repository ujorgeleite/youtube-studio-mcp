"""Estado da sessão local. O que importa é persistido no `project.json`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from analysis.pipeline import AnalysisMonitor, load_inventory
from core.project import Project
from core.schema import Inventory
from core.serial import read_json, write_json

PAGES = ("Material", "Análise", "Histórias", "Revisão", "Entrega")
MATERIAL, ANALYSIS, STORIES, REVIEW, DELIVERY = range(5)
LAST_PROJECT = Path(__file__).resolve().parents[1] / ".state" / "ultimo.json"


@dataclass
class Studio:
    project: Project | None = None
    page: int = MATERIAL
    monitor: AnalysisMonitor | None = None
    analyzing: bool = False
    catalog_errors: dict[str, str] = field(default_factory=dict)
    inventory_cache: Inventory | None = None
    delivery: dict = field(default_factory=dict)

    @property
    def busy(self) -> bool:
        return self.analyzing or bool(self.delivery.get("running"))

    @property
    def inventory(self) -> Inventory | None:
        if self.inventory_cache is None and self.project is not None:
            self.inventory_cache = load_inventory(self.project)
        return self.inventory_cache

    def use(self, project: Project) -> None:
        self.project = project
        self.inventory_cache = None
        write_json(LAST_PROJECT, {"folder": project.folder, "output_dir": project.output_dir})

    def restore_last(self) -> None:
        last = read_json(LAST_PROJECT)
        if self.project is None and last and Path(last.get("folder", "")).is_dir():
            self.project = Project.open(last["folder"], last.get("output_dir"))
            if self.project.report:
                self.page = STORIES


STUDIO = Studio()
