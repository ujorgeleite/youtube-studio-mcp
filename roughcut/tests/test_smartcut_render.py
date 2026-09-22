from smartcut.render import keep_intervals
from smartcut.schema import Cut, CutPlan


def test_keep_intervals_converts_cuts_to_renderable_segments():
    plan = CutPlan("video.mp4", 10, "colab", cuts=[Cut(2, 3, "pausa"), Cut(7, 8, "retake")])
    assert keep_intervals(plan) == [
        {"start_s": 0, "end_s": 2},
        {"start_s": 3, "end_s": 7},
        {"start_s": 8, "end_s": 10},
    ]
