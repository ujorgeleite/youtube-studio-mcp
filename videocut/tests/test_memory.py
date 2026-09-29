"""Memória com saídas reais de `vm_stat`, `sysctl`, `top` e `ps` gravadas como fixture."""
import asyncio

from nicegui import Client, core
from nicegui.page import page

from core import memory
from core.memory import GB, AppMemory, MemoryStatus, app_name, freeing_steps, parse_size, parse_swap, parse_vm_stat

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                              271943.
Pages active:                            361855.
Pages inactive:                          347938.
Pages speculative:                        13108.
Pages wired down:                        239585.
Pages purgeable:                          10419.
"""
SWAP = "total = 12288.00M  used = 11375.62M  free = 912.38M  (encrypted)"
TOP = """PID    MEM
70005  4220M
12516  949M+
12512  658M
53126  557M
69995  1557M
"""
PS = """70005 /Applications/Wondershare Filmora Mac.app/Contents/MacOS/Wondershare Filmora Mac
12516 /Applications/Brave Browser.app/Contents/Frameworks/Brave Browser Framework.framework/Versions/1/Helpers/Brave Browser Helper (Renderer).app/Contents/MacOS/Brave Browser Helper (Renderer)
12512 /Applications/Brave Browser.app/Contents/MacOS/Brave Browser
53126 /Applications/Brave Browser.app/Contents/Frameworks/Brave Browser Framework.framework/Versions/1/Helpers/Brave Browser Helper.app/Contents/MacOS/Brave Browser Helper
69995 /System/Library/Frameworks/Virtualization.framework/Versions/A/XPCServices/com.apple.Virtualization.VirtualMachine.xpc/Contents/MacOS/com.apple.Virtualization.VirtualMachine
"""


OUTPUTS = {
    "sysctl -n hw.memsize": str(24 * GB),
    "sysctl -n kern.memorystatus_vm_pressure_level": "1",
    "sysctl -n vm.swapusage": SWAP,
    "vm_stat": VM_STAT,
    "top": TOP,
    "ps": PS,
}


def runner(args):
    command = " ".join(args)
    return next((output for prefix, output in OUTPUTS.items() if command.startswith(prefix)), "")


def test_parsers_match_real_outputs():
    assert parse_vm_stat(VM_STAT) == (271943 + 347938 + 13108 + 10419) * 16384
    assert round(parse_swap(SWAP) / GB, 1) == 11.1
    assert parse_size("949M+") == 949 * 1024 ** 2 and parse_size("12K") == 12 * 1024 and parse_size("1.5G") == int(1.5 * GB)


def test_helpers_are_grouped_under_their_application():
    assert app_name("/Applications/Brave Browser.app/Contents/Frameworks/X.framework/Helpers/Brave Browser Helper.app/Contents/MacOS/h") == "Brave Browser"
    assert app_name("/System/.../com.apple.Virtualization.VirtualMachine") == "Máquina virtual (Virtualization)"
    apps = memory.top_apps(runner)
    assert [(app.name, app.processes) for app in apps][:3] == [("Wondershare Filmora Mac", 1), ("Brave Browser", 3), ("Máquina virtual (Virtualization)", 1)]
    assert round(apps[1].gb, 2) == round((949 + 658 + 557) / 1024, 2)


def test_status_levels_and_steps():
    status = MemoryStatus(total=24 * GB, available=int(6 * GB), swap_used=int(11 * GB), pressure=1,
                          apps=[AppMemory("Brave Browser", int(8.8 * GB), 52), AppMemory("Wondershare Filmora Mac", int(4.6 * GB), 4)])
    assert status.level(8) == "apertado" and status.level(12) == "critico"
    assert MemoryStatus(total=24 * GB, available=16 * GB, swap_used=0, pressure=1).level(8) == "ok"
    steps = freeing_steps(status, 8)
    assert steps[0] == "Libere pelo menos 2,0 GB: o modelo escolhido precisa de ~8 GB livres."
    assert "Brave Browser usa 8,8 GB em 52 processos: feche abas e janelas" in steps[1]
    assert "Wondershare Filmora Mac usa 4,6 GB em 4 processos: feche o app (⌘Q)" in steps[2]
    assert any("11,0 GB em swap" in step for step in steps)


def test_required_memory_follows_the_chosen_model():
    assert memory.required_gb("qwen3-vl-4b") == 5 and memory.required_gb("qwen3-vl-8b") == 8
    assert memory.required_gb(None) == 8


def test_low_memory_asks_before_analysis_and_panel_lists_apps(media_dir, tmp_path, monkeypatch):
    from tests.test_ui import _project, _renderers, _texts
    from ui import analysis_view, memory_view, state
    from ui.shell import Shell
    from ui.state import Studio

    tight = MemoryStatus(total=24 * GB, available=int(3 * GB), swap_used=int(11 * GB), pressure=2,
                         apps=[AppMemory("Brave Browser", int(8.8 * GB), 52)])
    monkeypatch.setattr(memory_view, "memory_status", lambda *args, **kwargs: tight)
    monkeypatch.setattr(state, "LAST_PROJECT", tmp_path / "last.json")

    async def declined(shell, model_key):
        return False

    monkeypatch.setattr(memory_view, "confirm_low_memory", declined)
    studio = Studio()
    studio.use(_project(media_dir, tmp_path))

    async def exercise():
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        with Client(page("/memory-test")) as client:
            shell = Shell(studio, _renderers())
            shell.build()
            texts = _texts(client)
            assert "Memória insuficiente" in texts and "Brave Browser" in texts and "8,8 GB" in texts
            assert "Abrir Monitor de Atividade" in texts
            await analysis_view.start_analysis(shell)
            assert studio.monitor is None and not studio.analyzing

    asyncio.run(exercise())


def test_full_status_from_real_outputs():
    status = memory.memory_status(runner)
    assert round(status.total_gb) == 24 and round(status.swap_gb, 1) == 11.1 and status.pressure_label == "normal"
    assert status.apps[0].name == "Wondershare Filmora Mac"
