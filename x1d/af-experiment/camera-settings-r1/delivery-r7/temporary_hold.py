"""为 r7 临时 RAM 装载建立和释放一次性 GUI 保持窗口。

默认和 ``report`` 完全离线。只有明确的 ``stage``、``begin``、``finish``
子命令访问相机；它们不访问 FARM RAM，不启动引闪 observer 或射频阶段。
"""
from datetime import datetime, timezone
from pathlib import Path
import base64
import hashlib
import json
import shlex
import sys
import tarfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if Path.cwd().resolve() != ROOT:
    raise RuntimeError("Hasselblad workspace required")
sys.path.insert(0, str(HERE))
import transfer

REMOTE = "/tmp/hbl-wireless-flash"
ARCHIVE = ROOT / "x1d/wireless-flash/build/formal-flash-package/stable-install-20260912T123138Z/session-package.tar.gz"
ARCHIVE_SHA256 = "a57af6e4ed383daa59e58ba4b33e5d2ee54f40f79e2bceb2e309d30e347f6327"
ARCHIVE_BYTES = 147174
MANIFEST_SHA256 = "a4872ac129aa9d532065be2f77a4f6525a32fc02460d057767c957df01e5f8df"
MEMBERS = {
    "delta/0.bin", "delta/1.bin", "delta/2.bin", "formal-client-check",
    "formal-install.sh", "formal-netlink-probe", "formal-prepare-radio.sh",
    "formal-restore.sh", "formal-sync-hook-check", "formal-system-check",
    "formal-ui.rcc", "libhbl-formal-observer.so", "libhbl-formal.so",
    "manifest.sha256",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_archive():
    if not ARCHIVE.is_file() or ARCHIVE.stat().st_size != ARCHIVE_BYTES or sha(ARCHIVE) != ARCHIVE_SHA256:
        raise RuntimeError("fixed hold archive changed; no USB opened")
    with tarfile.open(ARCHIVE, "r:gz") as bundle:
        members = bundle.getmembers()
        if {item.name for item in members} != MEMBERS:
            raise RuntimeError("fixed hold archive members changed; no USB opened")
        if any(not item.isfile() or item.name.startswith("/") or ".." in Path(item.name).parts for item in members):
            raise RuntimeError("unsafe hold archive member; no USB opened")
        manifest = bundle.extractfile("manifest.sha256").read()
        if hashlib.sha256(manifest).hexdigest() != MANIFEST_SHA256:
            raise RuntimeError("fixed hold manifest changed; no USB opened")
    return {"archiveSha256": ARCHIVE_SHA256, "archiveBytes": ARCHIVE_BYTES,
            "manifestSha256": MANIFEST_SHA256, "members": len(MEMBERS)}


def write_record(session, state, name):
    state.update(session.summary())
    path = session.directory / name
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def stage():
    fixed = verify_archive()
    data = ARCHIVE.read_bytes()
    session = transfer.Session("r7-hold-stage")
    state = {**fixed, "staged": False, "farmRequests": 0, "farmWrites": 0,
             "flashObserverStarted": False, "radioStarted": False}
    try:
        active = session.command("original-services", "systemctl is-active victory-gui msg2dbus-farm")
        if active["output"].split() != ["active", "active"]:
            raise RuntimeError("original services not active")
        session.command("fresh-hold-directory",
                        "d=" + REMOTE + ";umask 077;test ! -e \"$d\" && test ! -L \"$d\" && mkdir -m 700 \"$d\"")
        decoder = transfer.DECODER
        for index, start in enumerate(range(0, len(decoder), 70)):
            session.command("decoder-" + str(index), "printf %s " + shlex.quote(decoder[start:start+70]) +
                            (" >" if index == 0 else " >>") + REMOTE + "/d.awk")
        encoded = base64.b64encode(data).decode("ascii")
        parts = [encoded[start:start+176] for start in range(0, len(encoded), 176)]
        for index, part in enumerate(parts):
            session.command("archive-" + str(index), "printf %s " + shlex.quote(part) +
                            (" >" if index == 0 else " >>") + REMOTE + "/p64")
            if (index + 1) % 100 == 0:
                print(json.dumps({"stage": "hold-transfer", "chunks": index + 1,
                                  "total": len(parts)}), flush=True)
        decode = "d=" + REMOTE + ";(printf '%b' \"$(awk -f \"$d/d.awk\" \"$d/p64\")\" >\"$d/session.tar.gz\";sha256sum \"$d/session.tar.gz\" >\"$d/decode.sha\") </dev/null >/dev/null 2>&1 &"
        session.command("decode-once", decode)
        for index in range(90):
            time.sleep(1)
            result = session.command("decode-result-" + str(index),
                                     "d=" + REMOTE + ";if test -f \"$d/decode.sha\";then cat \"$d/decode.sha\";else printf pending;fi")
            if result["output"] != "pending":
                break
        else:
            raise RuntimeError("hold archive decode outcome unknown; do not repeat")
        if result["output"].split()[0] != ARCHIVE_SHA256:
            raise RuntimeError("hold archive checksum mismatch")
        result = session.command("extract-and-verify",
            "cd " + REMOTE + " && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n formal-install.sh formal-restore.sh && printf hold-package-verified")
        if result["output"] != "hold-package-verified":
            raise RuntimeError("hold package target verification failed")
        state["staged"] = True
    finally:
        path = write_record(session, state, "stage.json")
        print(json.dumps({"stage": "hold-package-staged" if state["staged"] else "stopped",
                          "evidence": str(path.relative_to(ROOT)), **session.summary()}), flush=True)
    return path


def load_stage(path):
    fixed = verify_archive()
    path = Path(path).resolve()
    root = (HERE / "build/sessions").resolve()
    if not path.is_relative_to(root) or path.name != "stage.json":
        raise ValueError("stage evidence path")
    state = json.loads(path.read_text(encoding="utf-8"))
    if (not state.get("staged") or state.get("failed") or not state.get("allHandlesClosed") or
            state.get("archiveSha256") != fixed["archiveSha256"] or
            state.get("manifestSha256") != fixed["manifestSha256"]):
        raise RuntimeError("complete fixed hold staging evidence required")
    return path, state


def begin(path):
    path, staged = load_stage(path)
    session = transfer.Session("r7-hold-begin")
    state = {"begun": False, "stageEvidence": str(path.relative_to(ROOT)),
             "archiveSha256": staged["archiveSha256"], "farmRequests": 0, "farmWrites": 0,
             "flashObserverStarted": False, "radioStarted": False}
    try:
        check = session.command("staged-archive-identity",
            "d=" + REMOTE + ";test -d \"$d\" && test ! -L \"$d\" && sha256sum \"$d/session.tar.gz\"")
        if check["output"].split()[0] != ARCHIVE_SHA256:
            raise RuntimeError("staged hold archive changed")
        check = session.command("staged-manifest-identity",
            "cd " + REMOTE + " && sha256sum -c manifest.sha256 >/dev/null && printf fixed")
        if check["output"] != "fixed":
            raise RuntimeError("staged hold package changed")
        ready = session.command("current-ui-snapshot",
            REMOTE + "/formal-system-check --snapshot")
        if ready["output"].strip() != "system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0":
            raise RuntimeError("wake camera screen to the normal active view before beginning hold")
        session.command("begin-once",
            "d=" + REMOTE + ";p=r7-ui;test ! -e \"$d/$p.sent\" && touch \"$d/$p.sent\" && (sh \"$d/formal-install.sh\" --stage-ui >\"$d/$p.log\" 2>&1;echo $? >\"$d/$p.exit\") </dev/null >/dev/null 2>&1 &")
        for index in range(90):
            time.sleep(1)
            result = session.command("begin-result-" + str(index),
                "d=" + REMOTE + ";p=r7-ui;if test -f \"$d/$p.exit\";then cat \"$d/$p.exit\";cat \"$d/formal-install.status\" 2>/dev/null;else printf pending;fi")
            if result["output"] != "pending":
                break
        else:
            raise RuntimeError("hold begin outcome unknown; do not repeat")
        if result["output"].splitlines() != ["0", "formal-ui-hold-ready-default-off"]:
            raise RuntimeError("hold begin failed: " + result["output"])
        health = session.command("held-health",
            REMOTE + "/formal-system-check --require-held-min-ms 180000")
        if health["output"].strip() != "system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1":
            raise RuntimeError("hold health not ready")
        state["begun"] = True
    finally:
        evidence = write_record(session, state, "begin.json")
        print(json.dumps({"stage": "hold-ready" if state["begun"] else "stopped",
                          "evidence": str(evidence.relative_to(ROOT)), **session.summary()}), flush=True)
    return evidence


def finish(path):
    path = Path(path).resolve()
    root = (HERE / "build/sessions").resolve()
    if not path.is_relative_to(root) or path.name != "begin.json":
        raise ValueError("begin evidence path")
    begun = json.loads(path.read_text(encoding="utf-8"))
    if not begun.get("begun") or begun.get("failed") or not begun.get("allHandlesClosed"):
        raise RuntimeError("complete hold begin evidence required")
    session = transfer.Session("r7-hold-finish")
    state = {"finished": False, "beginEvidence": str(path.relative_to(ROOT)),
             "farmRequests": 0, "farmWrites": 0, "flashObserverStarted": False,
             "radioStarted": False}
    try:
        result = session.command("restore-original-gui",
            "sh " + REMOTE + "/formal-restore.sh --before-farm-install", timeout_ms=45000)
        if result["output"].strip() != "original-linux-services-and-radio-restored":
            raise RuntimeError("original GUI restoration not confirmed")
        health = session.command("active-after-restore", REMOTE + "/formal-system-check --require-active")
        if health["output"].strip() != "system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=0":
            raise RuntimeError("original active GUI not confirmed")
        state["finished"] = True
    finally:
        evidence = write_record(session, state, "finish.json")
        print(json.dumps({"stage": "original-gui-restored" if state["finished"] else "stopped",
                          "evidence": str(evidence.relative_to(ROOT)), **session.summary()}), flush=True)
    return evidence


def main():
    verify_archive()
    args = sys.argv[1:]
    if not args or args == ["report"]:
        print(json.dumps({"ready": True, **verify_archive(), "hardwareRequests": 0,
                          "scope": "temporary GUI hold only"}))
    elif args == ["stage"]:
        stage()
    elif len(args) == 2 and args[0] == "begin":
        begin(args[1])
    elif len(args) == 2 and args[0] == "finish":
        finish(args[1])
    else:
        raise SystemExit("usage: temporary_hold.py [report|stage|begin STAGE_JSON|finish BEGIN_JSON]")


if __name__ == "__main__":
    main()
