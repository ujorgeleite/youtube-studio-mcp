"""Energia e keep-awake com saídas reais do `pmset` gravadas como fixture."""
from core.keepawake import KeepAwake
from core.power import auto_install_macos_updates, battery_percent, low_power_mode, on_ac_power, power_checklist

PMSET_BATT_AC = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=23003235)\t86%; charging; (no estimate) present: true\n"
PMSET_BATT_BATTERY = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=23003235)\t41%; discharging; 3:12 remaining present: true\n"
PMSET_G = """System-wide power settings:
Currently in use:
 standby              1
 sleep                1 (sleep prevented by sharingd, bluetoothd, Claude, powerd)
 lowpowermode         0
 displaysleep         60
"""


def runner(outputs: dict[str, str]):
    def run(args: list[str]) -> str:
        return outputs.get(" ".join(args[:3]), "")
    return run


def test_power_parsers_read_real_pmset_output():
    ac = runner({"pmset -g batt": PMSET_BATT_AC, "pmset -g": PMSET_G})
    assert on_ac_power(ac) is True and battery_percent(ac) == 86
    assert low_power_mode(ac) is False
    battery = runner({"pmset -g batt": PMSET_BATT_BATTERY, "pmset -g": PMSET_G.replace("lowpowermode         0", "lowpowermode         1")})
    assert on_ac_power(battery) is False and low_power_mode(battery) is True
    assert on_ac_power(runner({})) is None


def test_auto_update_setting():
    assert auto_install_macos_updates(runner({"defaults read /Library/Preferences/com.apple.SoftwareUpdate": "1\n"})) is True
    assert auto_install_macos_updates(runner({"defaults read /Library/Preferences/com.apple.SoftwareUpdate": "0\n"})) is False
    assert auto_install_macos_updates(runner({})) is None


def test_checklist_flags_what_needs_attention():
    outputs = {"pmset -g batt": PMSET_BATT_BATTERY, "pmset -g": PMSET_G,
               "defaults read /Library/Preferences/com.apple.SoftwareUpdate": "1\n"}
    items = {item.key: item for item in power_checklist(4242, runner(outputs))}
    assert items["tomada"].status == "pendente" and "41%" in items["tomada"].detail
    assert items["baixo_consumo"].status == "ok"
    assert items["atualizacoes"].status == "pendente" and items["atualizacoes"].settings
    assert items["tampa"].status == "lembrete"
    assert items["acordado"].status == "lembrete"
    outputs["pgrep -fl caffeinate .*-w 4242"] = "999 caffeinate -i -m -s -w 4242\n"
    assert {item.key: item for item in power_checklist(4242, runner(outputs))}["acordado"].status == "ok"


class FakeProcess:
    def __init__(self, args, **kwargs):
        self.args = args
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def test_keep_awake_holds_while_any_job_runs_and_releases_after():
    spawned = []
    keeper = KeepAwake(spawn=lambda args, **kw: spawned.append(FakeProcess(args)) or spawned[-1], pid=777)
    with keeper:
        assert keeper.active and spawned[0].args == ["caffeinate", "-i", "-m", "-s", "-w", "777"]
        with keeper:
            assert len(spawned) == 1
        assert keeper.active
    assert not keeper.active and spawned[0].terminated


def test_keep_awake_releases_even_when_the_job_fails():
    spawned = []
    keeper = KeepAwake(spawn=lambda args, **kw: spawned.append(FakeProcess(args)) or spawned[-1], pid=1)
    try:
        with keeper:
            raise RuntimeError("falhou")
    except RuntimeError:
        pass
    assert spawned[0].terminated and not keeper.active
