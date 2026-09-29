"""Configurações: prompts editáveis, skills, agentes e registro de chamadas."""
import json
from pathlib import Path

import pytest

from analysis.vlm import RecordingModel
from core import extensions, settings
from core.config import load_yaml
from core.extensions import AGENTS, SKILLS, skills_text
from core.schema import Beat, Evidence, StoryVideo
from story import agents
from story.chronology import base_cut
from story.planner import chapter_prompt, outline_prompt
from tests.test_planner import day_inventory


def test_every_default_prompt_is_valid_with_its_required_variables():
    for item in settings.EDITABLES:
        assert settings.validate(item.key, settings.read_default(item.key)) == [], item.key


def test_validation_blocks_missing_unknown_and_broken_variables():
    text = settings.read_default("capitulo")
    assert any("{momentos}" in error for error in settings.validate("capitulo", text.replace("{momentos}", "")))
    assert any("{inventado}" in error for error in settings.validate("capitulo", text + " {inventado}"))
    assert any("Chaves" in error for error in settings.validate("capitulo", text + " { quebrado"))
    assert settings.validate("canal", "- lista\n") == ["O arquivo precisa ser um mapa (chave: valor)."]


def test_saved_edits_win_over_defaults_and_can_be_restored():
    original = settings.read_default("capitulo")
    edited = original.replace("Você edita um capítulo", "Você é um editor rigoroso que edita um capítulo")
    assert settings.save("capitulo", edited) == []
    assert settings.is_customized("capitulo") and settings.read("capitulo") == edited
    inventory = day_inventory()
    cut = base_cut(inventory)
    assert "editor rigoroso" in chapter_prompt("V", {"titulo": "C", "papel": "x"}, 1, 1, cut.speech, None)
    assert settings.save("capitulo", "sem variáveis") != [] and settings.read("capitulo") == edited
    settings.restore_default("capitulo")
    assert not settings.is_customized("capitulo") and settings.read("capitulo") == original
    assert len(settings.history("capitulo")) == 2


def test_yaml_edits_apply_without_restarting():
    assert "regras" in load_yaml("canal.yaml")
    assert settings.save("canal", "canal: Outro canal\nregras:\n  - Só uma regra.\n") == []
    assert load_yaml("canal.yaml")["canal"] == "Outro canal"
    prompt = outline_prompt(day_inventory(), base_cut(day_inventory()))
    assert "Outro canal" in prompt and "Só uma regra." in prompt


def test_builtin_skills_and_agents_load_with_frontmatter():
    assert {"vlog-rapido", "tutorial", "humor-familia"} <= {skill.key for skill in SKILLS.all()}
    assert {"titulos-descricao", "revisor-ritmo", "checagem-nomes"} <= {agent.key for agent in AGENTS.all()}
    tutorial = SKILLS.get("tutorial")
    assert tutorial.builtin and tutorial.stages == ("capitulos", "capitulo") and "passos" in tutorial.body
    for agent in AGENTS.all():
        assert agents.unknown_variables(agent.body) == [], agent.key


def test_active_skills_enter_only_their_stages():
    assert skills_text([], "capitulo") == "(nenhuma skill ativa)"
    assert "Vlog rápido" in skills_text(["vlog-rapido"], "capitulo")
    assert skills_text(["vlog-rapido"], "capitulos") == "(nenhuma skill ativa)"
    inventory = day_inventory()
    assert "Tutorial" in outline_prompt(inventory, base_cut(inventory), skills=["tutorial"])


def test_user_skills_override_builtins_and_can_be_removed():
    SKILLS.save("Tutorial", "minha versão", "- Siga meu jeito.", key="tutorial", etapas=["capitulo"])
    mine = SKILLS.get("tutorial")
    assert not mine.builtin and mine.body == "- Siga meu jeito." and mine.stages == ("capitulo",)
    created = SKILLS.save("Cortes secos", "", "- Corte seco sempre.")
    assert created.key == "cortes-secos" and SKILLS.get("cortes-secos")
    assert SKILLS.remove("tutorial") and SKILLS.get("tutorial").builtin
    with pytest.raises(ValueError):
        SKILLS.save("", "", "")


def test_agent_prompt_carries_the_montage_sequence_and_saves_markdown(tmp_path: Path):
    video = StoryVideo("a1", "Dia no IKEA", "a estante", [
        Beat("b1", "Abre", "gancho", "T01", 0, 5, evidence=[Evidence("T01", 0, 5, "Bom dia, vamos ao IKEA")]),
        Beat("b2", "Loja", "conclusao", "T02", 10, 20, evidence=[Evidence("T02", 10, 20, "", "corredores cheios")]),
    ])
    agent = AGENTS.get("titulos-descricao")
    prompt = agents.agent_prompt(agent, video, None, "vlog do dia")
    assert "01 · 00:00 · gancho · Bom dia, vamos ao IKEA" in prompt and "02 · 00:05 · conclusao · [imagem] corredores cheios" in prompt
    assert "{" not in prompt.split("Sequência montada")[1]

    class Model:
        name = "fake"

        def generate(self, prompt, images=None, max_tokens=700):
            return "1. **Um dia no IKEA**"

    path = agents.run_agent(agent, Model(), video, None, "", tmp_path)
    assert path.name == "titulos-descricao__a1.md" and "Um dia no IKEA" in path.read_text()
    assert agents.results(tmp_path, "a1") == [path]


def test_recording_model_logs_prompt_answer_and_stage(tmp_path: Path):
    class Model:
        name = "fake"

        def generate(self, prompt, images=None, max_tokens=700):
            return "{\"ok\": true}"

        def release(self):
            pass

    log = tmp_path / "registro" / "run.jsonl"
    recording = RecordingModel(Model(), log, lambda: "Planejando capítulo 1/2")
    recording.generate("pedido", [Path("/x/frame.jpg")])
    record = json.loads(log.read_text().splitlines()[0])
    assert (record["etapa"], record["prompt"], record["resposta"], record["imagens"]) == ("Planejando capítulo 1/2", "pedido", "{\"ok\": true}", ["frame.jpg"])


def test_pipeline_logs_every_call_and_runs_agents(media_dir, tmp_path, monkeypatch):
    from analysis import pipeline
    from core.project import Project
    from media.catalog import catalog_folder
    from tests.test_pipeline import ScriptedModel
    from analysis.speech import group_sentences
    from core.schema import Transcript, Word

    monkeypatch.setattr("analysis.vision.sampling", lambda: {"broad_every_s": 3, "broad_max_frames": 2, "frames_per_call": 2,
                                                              "detail_windows_per_take": 0, "detail_frames_per_window": 2})
    words = [Word(0.5, 1.0, "Hoje"), Word(1.1, 1.6, "passeamos"), Word(1.7, 2.1, "no"), Word(2.2, 2.8, "parque.")]
    monkeypatch.setattr(pipeline, "transcribe_take", lambda take_id, *a, **k: Transcript(take_id, words=words, sentences=group_sentences(words)))
    monkeypatch.setattr(pipeline, "release_model", lambda: None)
    project = Project.open(media_dir, tmp_path / "out")
    project.takes, _ = catalog_folder(media_dir, project.layout.thumbnails)
    project.selected = [take.id for take in project.takes]
    report = pipeline.Analysis(project, model_factory=ScriptedModel).run()
    logs = list((project.layout.analysis / "registro").glob("*.jsonl"))
    assert len(logs) == 1 and len(logs[0].read_text().splitlines()) >= 3
    project.chosen = report.proposals[0].id
    outputs = pipeline.Analysis(project, model_factory=ScriptedModel).run_agents(["revisor-ritmo"], report.proposals[0].videos[0].id)
    assert outputs[0].parent.name == "agentes" and outputs[0].is_file()
