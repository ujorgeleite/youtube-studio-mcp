import threading

from analysis.vlm import ThermalGuardedModel
from core.thermal import LongRunConfig, ThermalGovernor, ThermalReading


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def governor(readings, enabled=True, **config):
    clock = Clock()
    sequence = iter(readings)
    last = {"value": None}

    def reader():
        last["value"] = next(sequence, last["value"])
        return last["value"]

    settings = LongRunConfig(**{"poll_s": 10, "max_wait_min": 5, **config})
    return ThermalGovernor(enabled=enabled, config=settings, reader=reader, sleep=clock.sleep, clock=clock), clock


def test_reading_label_and_hottest():
    reading = ThermalReading(1, 71.2, 88.6)
    assert reading.hottest_c == 88.6
    assert reading.label == "CPU 71 °C · GPU 89 °C · razoável"
    assert ThermalReading().label == "temperatura indisponível"


def test_cool_mac_never_pauses():
    gov, clock = governor([ThermalReading(0, 60, 65)])
    gov.wait_if_hot()
    assert gov.pauses == 0 and clock.now == 0


def test_hot_mac_pauses_until_below_the_resume_threshold():
    readings = [ThermalReading(1, 90, 96), ThermalReading(1, 88, 90), ThermalReading(1, 80, 82), ThermalReading(1, 76, 79)]
    gov, clock = governor(readings)
    gov.wait_if_hot()
    assert gov.pauses == 1 and clock.now == 30
    assert gov.paused_total_s == 30 and gov.paused_since is None
    assert gov.summary() == "1 pausa(s) para esfriar · 0 min 30 s no total"


def test_macos_serious_state_pauses_even_without_temperature():
    gov, clock = governor([ThermalReading(2), ThermalReading(2), ThermalReading(1)])
    gov.wait_if_hot()
    assert clock.now == 20


def test_disabled_governor_only_reads():
    gov, clock = governor([ThermalReading(3, 99, 99)], enabled=False)
    gov.wait_if_hot()
    assert gov.pauses == 0 and gov.last.state == 3


def test_max_wait_continues_with_warning():
    gov, clock = governor([ThermalReading(2, 97, 97)], max_wait_min=1)
    gov.wait_if_hot()
    assert clock.now >= 60 and "não esfriou em 1 min" in gov.warning


def test_cancel_interrupts_the_pause():
    cancel = threading.Event()
    gov, clock = governor([ThermalReading(2, 97, 97)])
    gov.cancel = cancel
    cancel.set()
    gov.wait_if_hot()
    assert clock.now == 0 and gov.pauses == 1


def test_readings_are_throttled_between_calls():
    calls = []
    gov = ThermalGovernor(reader=lambda: calls.append(1) or ThermalReading(0), clock=lambda: 100.0)
    gov.refresh()
    gov.refresh()
    assert len(calls) == 1


def test_guarded_model_waits_before_each_generation():
    events = []

    class Model:
        name = "m"

        def generate(self, prompt, images=None, max_tokens=700):
            events.append("gera")
            return "{}"

        def release(self):
            events.append("libera")

    class Gate:
        def wait_if_hot(self):
            events.append("espera")

    guarded = ThermalGuardedModel(Model(), Gate())
    guarded.generate("p")
    guarded.release()
    assert events == ["espera", "gera", "libera"] and guarded.name == "m"


def test_analysis_uses_the_project_long_run_switch(tmp_path):
    from analysis.pipeline import Analysis
    from core.project import Project

    project = Project.open(tmp_path / "raw")
    assert Analysis(project).governor.enabled is False
    project.long_run = True
    analysis = Analysis(project)
    assert analysis.governor.enabled and analysis.monitor.thermal is analysis.governor
