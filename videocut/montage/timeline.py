"""Timeline editável em Final Cut Pro 7 XML (xmeml), o formato que o Filmora exporta.

A importação ("Importar Timeline XML") precisa ser validada na versão do Filmora
em uso; o MP4 continua sendo a entrega de referência.
"""

from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET

from core.schema import AudioClip, EditPlan, Take, VideoClip


def timebase(fps: float) -> tuple[int, bool]:
    rounded = round(fps)
    return rounded, not math.isclose(fps, rounded, abs_tol=0.01)


def frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


def _text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = str(value)
    return element


def _rate(parent: ET.Element, fps: float) -> None:
    base, ntsc = timebase(fps)
    rate = ET.SubElement(parent, "rate")
    _text(rate, "timebase", base)
    _text(rate, "ntsc", "TRUE" if ntsc else "FALSE")


def path_url(path: str) -> str:
    return "file://localhost" + quote(str(Path(path).resolve()))


class XmemlWriter:
    def __init__(self, plan: EditPlan, takes: dict[str, Take]):
        self.plan = plan
        self.takes = takes
        self.fps = plan.format.fps
        self.declared: set[str] = set()
        self.counter = 0

    def file_element(self, parent: ET.Element, take_id: str) -> None:
        file = ET.SubElement(parent, "file", id=f"file-{take_id}")
        if take_id in self.declared:
            return
        self.declared.add(take_id)
        take = self.takes.get(take_id)
        source = self.plan.sources[take_id]
        _text(file, "name", Path(source).name)
        _text(file, "pathurl", path_url(source))
        _rate(file, take.fps if take and take.fps else self.fps)
        _text(file, "duration", frames(take.duration_s if take else 0, self.fps))
        media = ET.SubElement(file, "media")
        video = ET.SubElement(ET.SubElement(media, "video"), "samplecharacteristics")
        _text(video, "width", take.width if take else self.plan.format.width)
        _text(video, "height", take.height if take else self.plan.format.height)
        if take is None or take.has_audio:
            audio = ET.SubElement(media, "audio")
            _text(audio, "channelcount", 2)

    def clipitem(self, track: ET.Element, clip: VideoClip | AudioClip, media_type: str) -> ET.Element:
        self.counter += 1
        item = ET.SubElement(track, "clipitem", id=f"clipitem-{self.counter}")
        _text(item, "name", Path(self.plan.sources[clip.take_id]).name)
        _text(item, "enabled", "TRUE")
        take = self.takes.get(clip.take_id)
        _text(item, "duration", frames(take.duration_s if take else clip.source_out, self.fps))
        _rate(item, self.fps)
        start = frames(clip.timeline_in, self.fps)
        _text(item, "start", start)
        _text(item, "end", start + frames(clip.duration_s, self.fps))
        _text(item, "in", frames(clip.source_in, self.fps))
        _text(item, "out", frames(clip.source_out, self.fps))
        self.file_element(item, clip.take_id)
        source = ET.SubElement(item, "sourcetrack")
        _text(source, "mediatype", media_type)
        if media_type == "audio":
            _text(source, "trackindex", 1)
        return item

    def audio_level(self, item: ET.Element, gain_db: float) -> None:
        if not gain_db:
            return
        effect = ET.SubElement(ET.SubElement(item, "filter"), "effect")
        for tag, value in (("name", "Audio Levels"), ("effectid", "audiolevels"), ("effectcategory", "audiolevels"),
                           ("effecttype", "audiolevels"), ("mediatype", "audio")):
            _text(effect, tag, value)
        parameter = ET.SubElement(effect, "parameter")
        _text(parameter, "parameterid", "level")
        _text(parameter, "name", "Level")
        _text(parameter, "value", f"{10 ** (gain_db / 20):.5f}")

    def build(self) -> ET.ElementTree:
        root = ET.Element("xmeml", version="5")
        sequence = ET.SubElement(root, "sequence", id="sequence-1")
        _text(sequence, "name", self.plan.title)
        _text(sequence, "duration", frames(self.plan.duration_s, self.fps))
        _rate(sequence, self.fps)
        media = ET.SubElement(sequence, "media")

        video = ET.SubElement(media, "video")
        characteristics = ET.SubElement(ET.SubElement(video, "format"), "samplecharacteristics")
        _rate(characteristics, self.fps)
        _text(characteristics, "width", self.plan.format.width)
        _text(characteristics, "height", self.plan.format.height)
        _text(characteristics, "pixelaspectratio", "square")
        for clips in (self.plan.main_track, self.plan.broll_track):
            if clips:
                track = ET.SubElement(video, "track")
                for clip in clips:
                    self.clipitem(track, clip, "video")

        audio = ET.SubElement(media, "audio")
        _text(audio, "numOutputChannels", 2)
        sample = ET.SubElement(ET.SubElement(audio, "format"), "samplecharacteristics")
        _text(sample, "depth", 16)
        _text(sample, "samplerate", self.plan.format.sample_rate)
        main_ids = {(clip.take_id, clip.timeline_in) for clip in self.plan.main_track}
        primary = [clip for clip in self.plan.audio if (clip.take_id, clip.timeline_in) in main_ids]
        ambient = [clip for clip in self.plan.audio if clip not in primary]
        for clips in (primary, ambient):
            if clips:
                track = ET.SubElement(audio, "track")
                for clip in clips:
                    self.audio_level(self.clipitem(track, clip, "audio"), clip.gain_db)
        return ET.ElementTree(root)


def write_xmeml(plan: EditPlan, takes: list[Take], destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    tree = XmemlWriter(plan, {take.id: take for take in takes}).build()
    ET.indent(tree)
    with target.open("wb") as handle:
        handle.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n')
        tree.write(handle, encoding="utf-8", xml_declaration=False)
    return target

