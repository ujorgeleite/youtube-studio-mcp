import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_clip(path: Path, *, seconds: float = 6, audio: bool = True, size: str = "320x240", cut_at: float | None = 3) -> Path:
    """Clipe sintético: cor sólida e padrão de teste, com troca brusca em `cut_at`."""
    first = cut_at if cut_at is not None else seconds
    video = f"color=c=red:s={size}:d={first}:r=25"
    inputs = ["-f", "lavfi", "-i", video]
    graph = "[0:v]format=yuv420p[v]"
    if cut_at is not None:
        inputs += ["-f", "lavfi", "-i", f"testsrc2=s={size}:d={seconds - cut_at}:r=25"]
        graph = "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]"
    if audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000"]
    audio_index = 2 if cut_at is not None else 1
    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[v]"]
    if audio:
        args += ["-map", f"{audio_index}:a", "-c:a", "aac"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-t", str(seconds), str(path)]
    subprocess.run(args, check=True)
    return path


@pytest.fixture(autouse=True)
def no_model_downloads(monkeypatch):
    """A suíte nunca baixa modelos; `tests/test_models.py` exercita o download com comandos falsos."""
    monkeypatch.setattr("analysis.pipeline.ensure_model", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def cool_mac(monkeypatch):
    """Nenhum teste lê o sensor real; quem precisa de calor injeta um leitor próprio."""
    from core.thermal import ThermalReading
    monkeypatch.setattr("core.thermal.read_thermal", lambda: ThermalReading(0, 50.0, 55.0))


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Edições de prompts, skills e agentes feitas nos testes nunca tocam `.state/ajustes` real."""
    from core import extensions, settings
    from core.config import load_yaml
    overrides = tmp_path / "ajustes"
    monkeypatch.setattr(settings, "OVERRIDES", overrides)
    monkeypatch.setattr(settings, "HISTORY", overrides / "historico")
    for registry in (extensions.SKILLS, extensions.AGENTS):
        monkeypatch.setattr(registry, "user_dir", overrides / registry.kind)
    load_yaml.cache_clear()
    yield
    load_yaml.cache_clear()


@pytest.fixture(autouse=True)
def roomy_memory(monkeypatch):
    """Nenhum teste lê a memória real nem abre o aviso de pouca memória por acaso."""
    from core.memory import GB, AppMemory, MemoryStatus
    healthy = MemoryStatus(total=24 * GB, available=16 * GB, swap_used=0, pressure=1,
                           apps=[AppMemory("Navegador", 2 * GB, 10)])
    monkeypatch.setattr("ui.memory_view.memory_status", lambda *args, **kwargs: healthy)
    monkeypatch.setattr("ui.memory_view._cache", {"full": None, "quick": None}, raising=False)


@pytest.fixture(autouse=True)
def no_caffeinate(monkeypatch):
    """Keep-awake é testado com processo falso; a suíte nunca segura o sono de verdade."""
    class Idle:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("core.keepawake.KEEP_AWAKE.spawn", lambda *args, **kwargs: Idle())
    monkeypatch.setattr("core.keepawake.KEEP_AWAKE.process", None)
    monkeypatch.setattr("core.keepawake.KEEP_AWAKE.holders", 0)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("raw")
    make_clip(folder / "b_conversa.mp4")
    make_clip(folder / "a_passeio.mov", audio=False, cut_at=None, seconds=4)
    (folder / "c_quebrado.mp4").write_bytes(b"not a video")
    (folder / "notas.txt").write_text("ignorar")
    return folder
