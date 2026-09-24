from pathlib import Path

from smartcut.render import keep_intervals, render_with_handles
from smartcut.schema import Cut, CutPlan


def test_keep_intervals_converts_cuts_to_renderable_segments():
    plan = CutPlan("video.mp4", 10, "colab", cuts=[Cut(2, 3, "pausa"), Cut(7, 8, "retake")])
    assert keep_intervals(plan) == [
        {"start_s": 0, "end_s": 2},
        {"start_s": 3, "end_s": 7},
        {"start_s": 8, "end_s": 10},
    ]


def test_render_places_prefixed_video_and_plan_in_type_folders(tmp_path, monkeypatch):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    def fake_render(payload, destination, on_progress):
        destination = Path(destination)
        destination.mkdir(parents=True)
        assert payload["render_options"]["output_prefix"] == "processed_"
        video = destination / "processed_video__sem-silencios.mp4"
        plan = destination / "processed_video__plano-silencios.json"
        video.write_bytes(b"mp4"); plan.write_text("{}")
        return video, plan

    monkeypatch.setattr("smartcut.render.render_plan", fake_render)
    output, plan_path = render_with_handles(CutPlan(str(source), 10, "colab"), tmp_path / "result")
    assert output == tmp_path / "result" / "videos" / "processed_video__sem-silencios.mp4"
    assert plan_path == tmp_path / "result" / "plans" / "processed_video__plano-silencios.json"
    assert plan_path.is_file()
