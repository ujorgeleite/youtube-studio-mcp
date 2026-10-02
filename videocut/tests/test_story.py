import json
from pathlib import Path

from analysis.inventory import uncovered
from core.schema import VERDICT_INSUFFICIENT, VERDICT_MULTIPLE, VERDICT_SINGLE
from story import planner
from story.adjust import shorten
from story.validate import build_report, quote_supported
from tests.story_fixtures import example_inventory


def _block(momento, papel, titulo="Bloco", **extra):
    return {"momento": momento, "papel": papel, "titulo": titulo, **extra}


def _single(blocks, **extra):
    return {"veredito": "um_video", "resumo": "adaptação", "temas": ["rotina"], "propostas": [
        {"titulo": "A adaptação acontece nos dias comuns", "recomendada": True,
         "videos": [{"titulo": "Dias comuns", "mensagem": "adaptar é aproveitar", "blocos": blocks}], **extra}]}


FULL = [
    _block("T03.02", "gancho", "Gancho", citacao="nessas coisas pequenas"),
    _block("T01.02", "contexto", "Onde começa", apoio=[{"momento": "T02.01", "inicio": "00:05", "fim": "00:09"}]),
    _block("T04.01", "desenvolvimento", "O passeio", inicio="00:30", fim="00:50"),
    _block("T05.03", "mensagem", "O que mudou", apoio=[{"momento": "T06.01"}]),
    _block("T05.05", "conclusao", "Fechamento"),
]


def test_uncovered_subtracts_speech():
    assert uncovered(0, 40, [(10, 14, "x")]) == [(0, 10), (14, 40)]
    assert uncovered(0, 12, [(1, 11, "x")]) == []


def test_inventory_separates_speech_action_broll_and_problems():
    inventory = example_inventory()
    kinds = {moment.id: moment.kind for moment in inventory.moments}
    assert kinds["T03.02"] == "fala" and kinds["T04.01"] == "acao"
    assert kinds["T02.01"] == "apoio" and kinds["T02.02"] == "problema"
    assert "coisas pequenas" in next(m for m in inventory.moments if m.id == "T03.02").speech


def test_complete_story_is_anchored_to_facts():
    report = build_report(_single(FULL), example_inventory())
    assert report.verdict == VERDICT_SINGLE and not report.rejected
    proposal = report.proposals[0]
    assert proposal.recommended and not proposal.partial
    beats = proposal.videos[0].beats
    assert [beat.role for beat in beats] == ["gancho", "contexto", "desenvolvimento", "mensagem", "conclusao"]
    assert beats[0].start_s < 18 and beats[0].end_s > 21.9
    assert beats[0].evidence[0].quote.startswith("É nessas coisas pequenas")
    assert (beats[2].start_s, beats[2].end_s, beats[2].audio) == (30, 50, "ambiente")
    assert beats[1].overlays[0].take_id == "T02" and beats[1].overlays[0].start_s == 5
    assert all(criterion.status == "ok" for criterion in proposal.criteria)
    assert proposal.videos[0].id == "a1" and beats[0].id == "a1.b01"


def test_invented_moments_and_quotes_never_reach_the_person():
    blocks = [*FULL[:3], _block("T09.01", "mensagem", "Inventado"), _block("T05.03", "mensagem", "Citação falsa", citacao="a gente ama morar aqui desde sempre")]
    report = build_report(_single(blocks), example_inventory())
    assert any("T09.01" in message for message in report.rejected)
    video = report.proposals[0].videos[0]
    assert "Inventado" not in [beat.title for beat in video.beats]
    assert any("citação sugerida não aparece" in warning for warning in report.proposals[0].warnings)
    assert "ama morar" not in video.beats[-1].evidence[0].quote


def test_times_outside_the_moment_are_clamped():
    report = build_report(_single([_block("T04.01", "gancho", inicio="00:05", fim="09:00")]), example_inventory())
    beat = report.proposals[0].videos[0].beats[0]
    assert (beat.start_s, beat.end_s) == (22, 72)


def test_missing_speech_makes_proposal_partial_and_verdict_insufficient():
    report = build_report(_single([_block("T04.01", "gancho"), _block("T06.01", "apoio")]), example_inventory())
    proposal = report.proposals[0]
    message = next(criterion for criterion in proposal.criteria if criterion.key == "mensagem")
    assert message.status == "falta" and proposal.partial
    assert report.verdict == VERDICT_INSUFFICIENT


def test_model_cannot_upgrade_a_structurally_missing_criterion():
    raw = _single(FULL[:4], criterios={"encerramento": {"status": "ok", "detalhe": "fecha bem"}})
    proposal = build_report(raw, example_inventory()).proposals[0]
    closing = next(criterion for criterion in proposal.criteria if criterion.key == "encerramento")
    assert closing.status == "revisar" and "conclusão explícita" in closing.detail


def test_two_independent_videos_and_problem_broll_warning():
    raw = {"veredito": "varios_videos", "propostas": [{"titulo": "Dois vídeos", "recomendada": True, "videos": [
        {"titulo": "Um dia no parque", "blocos": [_block("T01.02", "gancho", apoio=[{"momento": "T02.02"}]), _block("T04.01", "desenvolvimento"), _block("T03.02", "conclusao")]},
        {"titulo": "Conversa", "blocos": [_block("T05.02", "gancho"), _block("T05.03", "mensagem"), _block("T05.05", "conclusao")]},
    ]}]}
    report = build_report(raw, example_inventory())
    proposal = report.proposals[0]
    assert report.verdict == VERDICT_MULTIPLE and proposal.multiple
    assert [video.id for video in proposal.videos] == ["a1", "a2"]
    assert any(criterion.key == "independencia" for criterion in proposal.criteria)
    assert any("problema técnico" in warning for warning in proposal.warnings)


def test_quote_matching_tolerates_accents_and_punctuation():
    assert quote_supported("é nessas coisas pequenas", "É nessas coisas pequenas, que a gente")
    assert not quote_supported("a gente ama morar aqui", "É nessas coisas pequenas")


def test_empty_or_garbage_answer_means_insufficient_material():
    assert build_report({}, example_inventory()).verdict == VERDICT_INSUFFICIENT
    assert build_report({"propostas": "x"}, example_inventory()).proposals == []


def test_shorten_drops_low_priority_beats_first():
    inventory = example_inventory()
    video = build_report(_single(FULL), inventory).proposals[0].videos[0]
    shorter = shorten(video, video.duration_s - 15, inventory)
    roles = [beat.role for beat in shorter.beats]
    assert "desenvolvimento" not in roles and {"gancho", "mensagem", "conclusao"} <= set(roles)
    assert shorter.duration_s <= video.duration_s - 15
    assert len(video.beats) == 5


def test_shorten_never_removes_protected_beats():
    inventory = example_inventory()
    video = build_report(_single(FULL), inventory).proposals[0].videos[0]
    development = next(beat for beat in video.beats if beat.role == "desenvolvimento")
    shorter = shorten(video, video.duration_s - 15, inventory, protected={development.id})
    assert development.id in [beat.id for beat in shorter.beats]


def test_extend_trim_and_replace_keep_whole_sentences():
    from story.adjust import extend_beat, replace_moment, trim_beat
    inventory = example_inventory()
    beat = build_report(_single([_block("T05.02", "mensagem")]), inventory).proposals[0].videos[0].beats[0]
    assert beat.end_s < 45
    assert extend_beat(beat, inventory) and beat.end_s > 49
    assert "dia simples" in beat.evidence[0].quote
    assert trim_beat(beat, inventory) and beat.end_s < 45
    assert not trim_beat(beat, inventory)
    moment = next(m for m in inventory.moments if m.id == "T04.01")
    replace_moment(beat, moment, inventory)
    assert (beat.take_id, beat.audio, beat.start_s, beat.end_s) == ("T04", "ambiente", 22, 72)
    assert beat.evidence[0].observation == "crianças brincam no balanço"


def test_gaps_survive_when_the_model_says_nothing_can_be_assembled():
    raw = {"veredito": "falta_material", "resumo": "Só há telas de teste.", "propostas": [
        {"titulo": "Insuficiente", "parcial": True, "videos": [],
         "lacunas": [{"descricao": "Falta mensagem falada.", "sugestao": "Gravar uma fala de 30 s."}]}]}
    report = build_report(raw, example_inventory())
    assert report.verdict == "falta_material" and not report.proposals
    assert [(gap.description, gap.suggestion) for gap in report.gaps] == [("Falta mensagem falada.", "Gravar uma fala de 30 s.")]
