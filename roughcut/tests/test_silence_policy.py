from __future__ import annotations

import pytest

from silence.policy import build_keep_intervals, dialogue_blocks, plan_for
from silence.schema import Interval, SilenceSettings, VideoAnalysis


def _analysis(**overrides) -> VideoAnalysis:
    settings = SilenceSettings(
        padding_before_s=0.1,
        padding_after_s=0.2,
        dialogue_merge_gap_s=2.5,
        cautious_internal_threshold_s=1.2,
        cautious_preserved_pause_s=0.4,
    )
    values = {
        "source": "/raw/video.mp4",
        "duration_s": 30.0,
        "silences": [
            Interval(0.0, 5.0),
            Interval(8.0, 9.0),
            Interval(12.0, 17.0),
            Interval(20.0, 21.0),
            Interval(26.0, 30.0),
        ],
        "settings": settings,
    }
    values.update(overrides)
    return VideoAnalysis(**values)


def test_dialogues_can_start_late_and_multiple_blocks_share_one_video():
    blocks = dialogue_blocks(_analysis())
    assert [(item.start_s, item.end_s) for item in blocks] == [
        (5.0, 12.0),
        (17.0, 26.0),
    ]


def test_around_dialogues_removes_spaces_between_dialogue_blocks():
    keeps = build_keep_intervals(_analysis(), "around_dialogues")
    assert [(item.start_s, item.end_s) for item in keeps] == [
        pytest.approx((4.9, 12.2)),
        pytest.approx((16.9, 26.2)),
    ]


def test_all_silences_keeps_each_spoken_island():
    keeps = build_keep_intervals(_analysis(), "all")
    assert len(keeps) == 4
    assert (keeps[0].start_s, keeps[0].end_s) == pytest.approx((4.9, 8.2))


def test_cautious_preserves_short_pauses_and_part_of_long_pause():
    keeps = build_keep_intervals(_analysis(), "cautious")
    assert sum(item.duration_s for item in keeps) == pytest.approx(16.7)
    assert any(item.start_s <= 8.0 and item.end_s >= 9.0 for item in keeps)


def test_plan_exposes_dialogues_and_estimated_duration():
    plan = plan_for(_analysis(), "around_dialogues")
    assert [item["id"] for item in plan["dialogues"]] == ["D001", "D002"]
    assert plan["estimated_output_duration_s"] == pytest.approx(16.6)
