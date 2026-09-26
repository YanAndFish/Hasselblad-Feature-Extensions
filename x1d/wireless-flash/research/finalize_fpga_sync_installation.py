"""把已收到的安装与回读证据落盘；不访问相机。"""
from datetime import datetime, timezone
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "build/fpga-sync-candidate"


def finish(loader, session, qtcheck, linuxinstall, live):
    if (session.failed or loader.io.failed or not loader.io.closed or
            not loader.record.get("installed") or not loader.record.get("armed")):
        raise RuntimeError("Installation is not verified")
    if qtcheck["output"] != "sync-hook-selftest: own=5 forwarded=272 status=1 hardware=0\n":
        raise RuntimeError("Target Qt evidence mismatch")
    if not linuxinstall["output"].endswith("linux-sync-chain-ready-farm-hook-pending-auto-off\n"):
        raise RuntimeError("Linux installation not ready")
    if not all(e["matched"] and e["closed"] and e.get("exit_code") == 0 for e in session.entries):
        raise RuntimeError("Incomplete command evidence")
    fields = dict(part.split("=", 1) for part in live["output"].split())
    state = {key: int(value) for key, value in fields.items()}
    if state.get("event") != 1:
        raise RuntimeError("Sync receiver not available")
    package = json.loads((OUT / "package-validation.json").read_text(encoding="utf-8"))
    result = {"kind": "resident-fpga-sync-gfs3-es-auto", "installed": True,
              "observedAt": datetime.now(timezone.utc).isoformat(),
              "files": package["files"], "packageSha256": package["packageSha256"],
              "farmPayloadSha256": package["farmPayloadSha256"],
              "farmCaptureEnabled": True, "farmRecoveryRecord": str(loader.path.relative_to(HERE)),
              "qtCheck": qtcheck, "linuxInstall": linuxinstall, "liveCheck": live,
              "liveState": state, "defaultAutomaticEnabled": False,
              "userRetestPending": True, "physicalTimingMeasured": False,
              "physicalFlashVerified": False, "agentFlashTrials": 0, "cameraShotsTriggered": 0,
              "farmRequests": loader.io.requests, "farmWrites": loader.io.writes,
              "linuxCommandRequests": sum(e["submitted"] for e in session.entries),
              "allHandlesClosed": loader.io.closed and all(e["closed"] for e in session.entries),
              "factoryNotificationSubscription": False, "sourceKind": "gfs3-es-fixed-auto",
              "timing": package["timingLimit"], "restoreOrder": package["restoreOrder"]}
    previous_path = HERE / "build/installation.json"
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        (OUT / "previous-installation.json").write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["previousInstallationRecord"] = "build/fpga-sync-candidate/previous-installation.json"
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (OUT / "installation.json").write_text(text, encoding="utf-8")
    previous_path.write_text(text, encoding="utf-8")
    print(json.dumps({"installed": True, "auto_on": state["on"], "sent": state["sent"], "all_handles_closed": result["allHandlesClosed"]}))
    return result
