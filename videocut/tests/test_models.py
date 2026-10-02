import os
import sys
import time
from pathlib import Path

import pytest

from analysis import models


@pytest.fixture
def cache(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(models, "HF_CACHE", tmp_path)
    monkeypatch.setattr(models, "expected_bytes", lambda repo: 3000)
    monkeypatch.setattr(models, "POLL_S", 0.05)
    blobs = tmp_path / "models--org--modelo" / "blobs"
    blobs.mkdir(parents=True)
    return blobs


def _script(code: str):
    return lambda repo: [sys.executable, "-c", code]


def test_download_reports_progress_and_finishes(cache: Path, monkeypatch):
    done = {"value": False}
    monkeypatch.setattr(models, "is_complete", lambda repo: done["value"])
    writer = _script(f"import time, pathlib\nf = pathlib.Path({str(cache / 'a')!r})\n"
                     "for i in range(3):\n    f.write_bytes(b'x' * 1000 * (i + 1)); time.sleep(0.15)\n")
    messages = []

    def progress(fraction, message):
        messages.append((fraction, message))
        if fraction >= 0.999:
            done["value"] = True

    models.ensure_model("org/modelo", "modelo", progress, command=writer)
    assert any("Baixando modelo" in message and "%" in message for _, message in messages)
    assert messages[-1] == (1.0, "modelo pronto")


def test_stalled_download_is_killed_retried_and_then_reported(cache: Path, monkeypatch):
    monkeypatch.setattr(models, "is_complete", lambda repo: False)
    hang = _script("import time; time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(models.ModelDownloadError, match="após 2 tentativas"):
        models.ensure_model("org/modelo", "modelo", None, command=hang, stall_timeout_s=0.3, attempts=2)
    assert time.monotonic() - started < 10


def test_complete_model_skips_download(cache: Path, monkeypatch):
    monkeypatch.setattr(models, "is_complete", lambda repo: True)
    models.ensure_model("org/modelo", "modelo", None, command=lambda repo: pytest.fail("não deveria baixar"))


def test_only_stale_partials_are_discarded(cache: Path):
    old, fresh = cache / "velho.incomplete", cache / "novo.incomplete"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    os.utime(old, (time.time() - 600, time.time() - 600))
    assert models.discard_orphans("org/modelo") == [old]
    assert fresh.exists() and not old.exists()
