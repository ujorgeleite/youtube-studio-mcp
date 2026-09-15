from youtube_studio_mcp.analytics import parse_video_efficiency
from youtube_studio_mcp.service import VideoEfficiencyService
from youtube_studio_mcp.youtube import duration_seconds

CANONICAL_EFFICIENCY = {
    "columnHeaders": [
        {"name": "views"},
        {"name": "estimatedMinutesWatched"},
        {"name": "averageViewDuration"},
        {"name": "averageViewPercentage"},
        {"name": "subscribersGained"},
        {"name": "subscribersLost"},
        {"name": "likes"},
        {"name": "comments"},
    ],
    "rows": [[900, 4000, 250, 55.5, 30, 4, 120, 18]],
}

VIDEOS = [
    {"id": "L1", "title": "Longo 1", "duration": "PT10M"},
    {"id": "L2", "title": "Longo 2", "duration": "PT8M"},
    {"id": "S1", "title": "Short 1", "duration": "PT30S"},
    {"id": "S2", "title": "Short 2", "duration": "PT50S"},
]

METRICS = {
    "L1": {"averageViewPercentage": 50.0, "subscribersGained": 10, "comments": 5, "likes": 100, "views": 800},
    "L2": {"averageViewPercentage": 80.0, "subscribersGained": 20, "comments": 10, "likes": 200, "views": 900},
    "S1": {"averageViewPercentage": 40.0, "subscribersGained": 2, "comments": 1, "likes": 10, "views": 300},
    "S2": {"averageViewPercentage": 90.0, "subscribersGained": 8, "comments": 4, "likes": 50, "views": 500},
}


def _service():
    return VideoEfficiencyService(
        list_videos=lambda: VIDEOS,
        video_efficiency=lambda vid, s, e: METRICS[vid],
        default_range=lambda: ("2026-08-01", "2026-08-28"),
    )


def test_duration_seconds_parses_iso8601():
    assert duration_seconds("PT7M37S") == 457
    assert duration_seconds("PT34S") == 34
    assert duration_seconds("PT40M49S") == 2449
    assert duration_seconds("PT1H2M3S") == 3723
    assert duration_seconds("") == 0


def test_parse_video_efficiency_reads_engagement_metrics():
    parsed = parse_video_efficiency(CANONICAL_EFFICIENCY)
    assert parsed["averageViewPercentage"] == 55.5
    assert parsed["likes"] == 120
    assert parsed["comments"] == 18
    assert parsed["subscribersNet"] == 26


def test_splits_into_longos_and_shorts():
    result = _service().rank()
    assert [v["id"] for v in result["categorias"]["longos"]["videos"]] == ["L2", "L1"]
    assert [v["id"] for v in result["categorias"]["shorts"]["videos"]] == ["S2", "S1"]
    assert result["categorias"]["longos"]["total"] == 2


def test_criteria_labels_and_raw_metrics_preserved():
    result = _service().rank()
    assert result["criterios"] == ["retencao", "inscritos", "comentarios", "likes"]
    top_long = result["categorias"]["longos"]["videos"][0]
    assert top_long["metrics"] == METRICS["L2"]
    assert top_long["score_eficiencia"] == 1.0
    assert result["categorias"]["longos"]["videos"][1]["score_eficiencia"] == 0.0


def test_uses_default_range_when_dates_omitted():
    assert _service().rank()["periodo"] == {"inicio": "2026-08-01", "fim": "2026-08-28"}
