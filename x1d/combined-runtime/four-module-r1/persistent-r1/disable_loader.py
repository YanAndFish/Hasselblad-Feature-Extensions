"""停用已安装四模块的开机入口；保留可核验备份，不重启当前服务。"""
from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json
import shlex
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
import session

REMOTE = "/tmp/hbl-disable-loader-r1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run() -> dict:
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError("workspace")
    script = (HERE / "disable-loader.sh").read_bytes().replace(b"\r\n", b"\n")
    digest = sha(script)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record_path = HERE / "build/sessions" / f"disable-loader-{stamp}.json"
    state = {"disabled": False, "scriptSha256": digest, "servicesRestarted": False,
             "cameraRebooted": False, "controllerWrites": 0}
    s = session.Session("disable-loader")
    seen = set()

    def command(label: str, text: str, timeout_ms: int = 15000) -> str:
        if label in seen or not 0 < len(text.encode("ascii")) <= 231 or "\n" in text:
            raise RuntimeError("command contract")
        seen.add(label)
        return s.command(label, text, timeout_ms)["output"].strip()

    def save(stage: str) -> None:
        state.update(stage=stage, transport=s.summary())
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"stage": stage, "requests": state["transport"]["requests"]}), flush=True)

    try:
        if command("installed", "test -f /opt/hbl-four-module-v1/enabled && test ! -L /opt/hbl-four-module-v1/enabled && test \"$(cat /opt/hbl-four-module-v1/enabled)\" = enabled-current-firmware && echo installed") != "installed":
            raise RuntimeError("installed package not verified")
        if command("dropins", "test -f /etc/systemd/system/victory-gui.service.d/92-hbl-four-module.conf && test -f /etc/systemd/system/msg2dbus-farm.service.d/92-hbl-four-module.conf && echo present") != "present":
            raise RuntimeError("drop-ins missing")
        if command("services", "systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon").splitlines() != ["active"] * 5:
            raise RuntimeError("service state")
        command("stage", f"umask 077;test ! -e {REMOTE} && test ! -L {REMOTE} && mkdir -m 700 {REMOTE}")
        save("preflight-passed")
        decoder = session.transport.DECODER
        for index, start in enumerate(range(0, len(decoder), 90)):
            redirect = ">" if index == 0 else ">>"
            command(f"decoder-{index}", f"printf %s {shlex.quote(decoder[start:start + 90])} {redirect}{REMOTE}/d.awk")
        encoded = base64.b64encode(script).decode("ascii")
        for index, start in enumerate(range(0, len(encoded), 170)):
            redirect = ">" if index == 0 else ">>"
            command(f"chunk-{index}", f"printf '%s\\n' {shlex.quote(encoded[start:start + 170])} {redirect}{REMOTE}/p64")
        command("decode", f"r={REMOTE};(printf '%b' \"$(awk -f \"$r/d.awk\" \"$r/p64\")\" >\"$r/disable.sh\";sha256sum \"$r/disable.sh\" >\"$r/hash\") </dev/null >/dev/null 2>&1 &")
        result = "pending"
        for index in range(30):
            time.sleep(0.5)
            result = command(f"hash-{index}", f"r={REMOTE};if test -f \"$r/hash\";then cat \"$r/hash\";else echo pending;fi")
            if result != "pending":
                break
        if result.split()[0] != digest:
            raise RuntimeError("staged script hash")
        command("syntax", f"sh -n {REMOTE}/disable.sh")
        command("dispatch", f"r={REMOTE};test ! -e \"$r/dispatched\" && touch \"$r/dispatched\" && (sh \"$r/disable.sh\" >\"$r/result\" 2>&1;echo $? >\"$r/exit\") </dev/null >/dev/null 2>&1 &")
        save("disable-dispatched")
        result = "pending"
        for index in range(60):
            time.sleep(0.5)
            result = command(f"result-{index}", f"r={REMOTE};if test -f \"$r/exit\";then cat \"$r/exit\" \"$r/result\";else echo pending;fi")
            if result != "pending":
                break
        state["deviceResult"] = result
        if result.splitlines() != ["0", "four-module-autoload-disabled-next-boot"]:
            raise RuntimeError("disable transaction")
        if command("final-files", "test -f /opt/hbl-four-module-v1/enabled && test ! -L /opt/hbl-four-module-v1/enabled && test ! -e /etc/systemd/system/victory-gui.service.d/92-hbl-four-module.conf && test ! -e /etc/systemd/system/msg2dbus-farm.service.d/92-hbl-four-module.conf && echo disabled") != "disabled":
            raise RuntimeError("autoload still enabled")
        if command("backup", "test -f /opt/hbl-four-module-v1.disabled/enabled && test -f /opt/hbl-four-module-v1.disabled/gui.conf && test -f /opt/hbl-four-module-v1.disabled/farm.conf && echo backup-ready") != "backup-ready":
            raise RuntimeError("backup")
        if command("final-services", "systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon").splitlines() != ["active"] * 5:
            raise RuntimeError("final service state")
        root = command("root-readonly", "grep ' / ' /proc/mounts")
        if " ext4 " not in root or ",ro," not in "," + root.split()[3] + ",":
            raise RuntimeError("root not read-only")
        state.update(disabled=True, rootReadOnly=True, backupReady=True)
        save("autoload-disabled-awaiting-normal-power-cycle")
        return state
    except BaseException as error:
        state["error"] = type(error).__name__ + ": " + str(error)
        save("stopped-for-review")
        raise


if __name__ == "__main__":
    if sys.argv[1:] == ["--run"]:
        print(json.dumps(run(), ensure_ascii=False))
    else:
        raise SystemExit("select --run")
