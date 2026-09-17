"""Testa as operações puras da prévia/edição da cut-list."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cockpit import preview  # noqa: E402


def _cut_list() -> dict:
    return {
        "roughcut": [
            {"beat": "cold_open", "clips": [{"clip_id": "C01", "in": "00:00:00", "out": "00:00:02"}]},
            {"beat": "broll_slot", "clips": [], "broll_suggestion": "drone"},
            {"beat": "encerramento", "clips": [{"clip_id": "C03", "in": "0", "out": "1"}]},
        ]
    }


def test_used_and_leftover():
    cut = _cut_list()
    clip_map = {"C01": "/a", "C02": "/b", "C03": "/c"}

    assert preview.used_clip_ids(cut) == {"C01", "C03"}
    assert preview.leftover_clips(cut, clip_map) == ["C02"]


def test_player_segments_skips_broll():
    segments = preview.player_segments(_cut_list())

    assert [s["clip_id"] for s in segments] == ["C01", "C03"]
    assert segments[0]["in"] == "00:00:00"


def test_move_beat_swaps_and_clamps():
    cut = _cut_list()

    preview.move_beat(cut, 0, 1)
    assert [b["beat"] for b in cut["roughcut"]] == ["broll_slot", "cold_open", "encerramento"]

    preview.move_beat(cut, 0, -1)  # já no topo: no-op
    assert cut["roughcut"][0]["beat"] == "broll_slot"


def test_remove_beat():
    cut = _cut_list()

    preview.remove_beat(cut, 1)

    assert [b["beat"] for b in cut["roughcut"]] == ["cold_open", "encerramento"]


def test_insert_clip_appends_and_positions():
    cut = _cut_list()

    preview.insert_clip(cut, "C02", "00:00:00", "00:00:04")
    assert cut["roughcut"][-1]["clips"][0]["clip_id"] == "C02"

    preview.insert_clip(cut, "C05", "00:00:00", "00:00:03", position=0)
    assert cut["roughcut"][0]["clips"][0]["clip_id"] == "C05"
    assert preview.leftover_clips(cut, {"C05": "/x"}) == []
