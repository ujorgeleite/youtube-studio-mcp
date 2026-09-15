import json

from youtube_studio_mcp.pillars import load_pillars
from youtube_studio_mcp.service import PillarService

VIDEOS = [
    {"id": "v1"},
    {"id": "v2"},
    {"id": "v3"},
    {"id": "v4"},  # not in the pillar map
]

PILLARS = {
    "v1": {"pilar": "imigracao"},
    "v2": {"pilar": "imigracao"},
    "v3": {"pilar": "holanda"},
}

# Per-video watch time and average view duration (retention proxy).
METRICS = {
    "v1": {"estimatedMinutesWatched": 100, "averageViewDuration": 200},
    "v2": {"estimatedMinutesWatched": 300, "averageViewDuration": 100},
    "v3": {"estimatedMinutesWatched": 50, "averageViewDuration": 90},
    "v4": {"estimatedMinutesWatched": 500, "averageViewDuration": 400},
}


def _service():
    return PillarService(
        list_videos=lambda: VIDEOS,
        video_metrics=lambda vid, s, e: METRICS[vid],
        load_pillars=lambda: PILLARS,
        default_range=lambda: ("2026-08-01", "2026-08-28"),
    )


def test_groups_by_pillar_and_ranks_by_watch_time():
    result = _service().analyze()

    # imigracao = 100 + 300 = 400; não classificado (v4) = 500; holanda = 50.
    assert [b["pilar"] for b in result["ranking"]] == ["não classificado", "imigracao", "holanda"]
    assert [b["minutos_assistidos"] for b in result["ranking"]] == [500, 400, 50]


def test_counts_videos_per_pillar_including_unclassified():
    result = _service().analyze()
    assert result["videos_por_pilar"] == {"não classificado": 1, "imigracao": 2, "holanda": 1}


def test_average_retention_per_pillar():
    ranking = {b["pilar"]: b for b in _service().analyze()["ranking"]}
    # imigracao: mean(200, 100) = 150
    assert ranking["imigracao"]["retencao_media_segundos"] == 150
    assert ranking["holanda"]["retencao_media_segundos"] == 90


def test_uses_default_range_when_dates_omitted():
    assert _service().analyze()["periodo"] == {"inicio": "2026-08-01", "fim": "2026-08-28"}


def test_load_pillars_missing_file_returns_empty(tmp_path):
    assert load_pillars(tmp_path / "nope.json") == {}


def test_load_pillars_reads_map(tmp_path):
    path = tmp_path / "pilares.json"
    path.write_text(json.dumps({"abc": {"pilar": "pedro", "formato": "short", "seo": True}}))
    assert load_pillars(path)["abc"]["pilar"] == "pedro"
