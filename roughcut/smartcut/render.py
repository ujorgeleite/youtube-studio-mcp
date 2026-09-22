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
    payload = {
        "source": plan.source,
        "duration_s": plan.duration_s,
        "keep": keep_intervals(plan),
        "render_options": {"always_render": True},
    }
    return render_plan(payload, output_dir, on_progress)
