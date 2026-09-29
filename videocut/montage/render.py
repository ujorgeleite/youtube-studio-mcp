"""Render por segmento: cada bloco vira um MP4 normalizado, depois concatenado sem recodificar."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from core.cache import fingerprint
from core.schema import AudioClip, EditPlan, OutputFormat, VideoClip
from media.probe import MediaError, run_ffmpeg

Progress = Callable[[float, str], None]


@dataclass
class Segment:
    beat_id: str
    main: VideoClip
    overlays: list[VideoClip]
    audio: list[AudioClip]

    @property
    def duration_s(self) -> float:
        return self.main.duration_s


def segments(plan: EditPlan) -> list[Segment]:
    result = []
    for main in plan.main_track:
        result.append(Segment(
            main.beat_id, main,
            [clip for clip in plan.broll_track if clip.beat_id == main.beat_id],
            [clip for clip in plan.audio if clip.beat_id == main.beat_id],
        ))
    return result


def video_encoder() -> list[str]:
    """VideoToolbox acelera muito no Mac; libx264 é o fallback portátil."""
    if sys.platform == "darwin" and _has_encoder("h264_videotoolbox"):
        return ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-allow_sw", "1"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19"]


def _has_encoder(name: str) -> bool:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return name in proc.stdout


NTSC_RATES = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}


def frame_rate(fps: float) -> str:
    return NTSC_RATES.get(round(fps, 3), f"{fps:g}")


def _fit(fmt: OutputFormat) -> str:
    return (f"fps={frame_rate(fmt.fps)},scale={fmt.width}:{fmt.height}:force_original_aspect_ratio=decrease,"
            f"pad={fmt.width}:{fmt.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")


def _audio_chain(clip: AudioClip, fmt: OutputFormat, offset_s: float) -> str:
    parts = [f"aresample={fmt.sample_rate}", "aformat=sample_fmts=fltp:channel_layouts=stereo", "asetpts=PTS-STARTPTS"]
    if clip.gain_db:
        parts.append(f"volume={clip.gain_db}dB")
    if clip.fade_in_s:
        parts.append(f"afade=t=in:st=0:d={clip.fade_in_s}")
    if clip.fade_out_s:
        parts.append(f"afade=t=out:st={max(0.0, clip.duration_s - clip.fade_out_s):.3f}:d={clip.fade_out_s}")
    if offset_s > 0:
        delay = int(round(offset_s * 1000))
        parts.append(f"adelay={delay}|{delay}")
    return ",".join(parts)


def segment_command(segment: Segment, plan: EditPlan, destination: Path, encoder: list[str]) -> list[str]:
    fmt = plan.format
    inputs: list[str] = []
    graph: list[str] = []

    def add_input(clip: VideoClip | AudioClip) -> int:
        inputs.extend(["-ss", f"{clip.source_in:.3f}", "-t", f"{clip.duration_s:.3f}", "-i", plan.sources[clip.take_id]])
        return len(inputs) // 6 - 1

    main_index = add_input(segment.main)
    graph.append(f"[{main_index}:v]setpts=PTS-STARTPTS,{_fit(fmt)}[v0]")
    current = "v0"
    for number, overlay in enumerate(segment.overlays, start=1):
        index = add_input(overlay)
        offset = overlay.timeline_in - segment.main.timeline_in
        graph.append(f"[{index}:v]setpts=PTS-STARTPTS+{offset:.3f}/TB,{_fit(fmt)}[o{number}]")
        graph.append(f"[{current}][o{number}]overlay=eof_action=pass:enable='between(t,{offset:.3f},{offset + overlay.duration_s:.3f})'[v{number}]")
        current = f"v{number}"

    audio_labels = []
    for number, clip in enumerate(segment.audio):
        is_main = clip.take_id == segment.main.take_id and abs(clip.timeline_in - segment.main.timeline_in) < 1e-3
        index = main_index if is_main else add_input(clip)
        offset = clip.timeline_in - segment.main.timeline_in
        graph.append(f"[{index}:a]{_audio_chain(clip, fmt, offset)}[a{number}]")
        audio_labels.append(f"[a{number}]")
    silence_index = len(inputs) // 6
    inputs.extend(["-f", "lavfi", "-t", f"{segment.duration_s:.3f}", "-i", f"anullsrc=r={fmt.sample_rate}:cl=stereo"])
    audio_labels.append(f"[{silence_index}:a]")
    graph.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:normalize=0:duration=longest,atrim=end={segment.duration_s:.3f}[aout]")

    return [
        *inputs, "-filter_complex", ";".join(graph), "-map", f"[{current}]", "-map", "[aout]",
        "-t", f"{segment.duration_s:.3f}", *encoder, "-r", frame_rate(fmt.fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", str(fmt.sample_rate), "-ac", "2",
        "-movflags", "+faststart", str(destination),
    ]


def segment_key(segment: Segment, plan: EditPlan, encoder: list[str]) -> str:
    """Só posições relativas ao bloco entram na chave: reordenar reaproveita os segmentos."""
    origin = segment.main.timeline_in
    clips = [replace(clip, timeline_in=round(clip.timeline_in - origin, 3), beat_id="")
             for clip in [segment.main, *segment.overlays, *segment.audio]]
    return fingerprint(clips, [plan.sources[clip.take_id] for clip in clips], plan.format, encoder)


def render_plan(plan: EditPlan, destination: str | Path, work_dir: str | Path, progress: Progress | None = None) -> Path:
    """Renderiza em pasta temporária e só substitui o MP4 final quando tudo deu certo."""
    if not plan.main_track:
        raise MediaError("o plano não tem blocos para renderizar")
    report = progress or (lambda fraction, message: None)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(work_dir) / "segments"
    cache.mkdir(parents=True, exist_ok=True)
    encoder = video_encoder()
    parts = segments(plan)
    total = sum(part.duration_s for part in parts) or 1.0
    done = 0.0
    files = []
    for number, part in enumerate(parts, start=1):
        report(done / total * 0.95, f"Montando bloco {number}/{len(parts)}")
        file = cache / f"{segment_key(part, plan, encoder)}.mp4"
        if not file.is_file():
            partial = file.with_name(f".{file.name}")
            run_ffmpeg(segment_command(part, plan, partial, encoder), error=f"falha ao montar o bloco {number}")
            partial.replace(file)
        files.append(file)
        done += part.duration_s
    report(0.96, "Unindo blocos")
    listing = cache / f"{target.stem}.concat.txt"
    listing.write_text("".join(f"file '{file.as_posix()}'\n" for file in files), encoding="utf-8")
    temporary = target.with_name(f".{target.name}")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(temporary)],
               error="falha ao unir os blocos")
    temporary.replace(target)
    report(1.0, "Montagem concluída")
    return target
