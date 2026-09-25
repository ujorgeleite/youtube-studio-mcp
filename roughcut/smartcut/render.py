from __future__ import annotations

from pathlib import Path

from silence.render import render_plan

from .schema import CutPlan


def keep_intervals(plan: CutPlan) -> list[dict[str, float]]:
    cursor = 0.0
    keeps = []
    for cut in sorted(plan.cuts, key=lambda item: item.start_s):
        if cut.start_s > cursor:
            keeps.append({"start_s": cursor, "end_s": cut.start_s})
        cursor = max(cursor, cut.end_s)
    if cursor < plan.duration_s:
        keeps.append({"start_s": cursor, "end_s": plan.duration_s})
    return keeps


def render_with_handles(plan: CutPlan, output_dir: str | Path, on_progress=None):
    """MP4 de revisão com cortes precisos; JSON do plano permanece a fonte de verdade."""
    root = Path(output_dir)
    payload = {
        "source": plan.source,
        "duration_s": plan.duration_s,
        "keep": keep_intervals(plan),
        "render_options": {"always_render": True, "output_prefix": "processed_"},
    }
    output, render_plan_path = render_plan(payload, root / "videos", on_progress)
    plans_dir = root / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    final_plan_path = plans_dir / render_plan_path.name
    render_plan_path.replace(final_plan_path)
    return output, final_plan_path
