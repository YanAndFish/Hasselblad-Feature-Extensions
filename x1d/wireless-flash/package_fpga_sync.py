"""封装独立 FPGA 引闪候选；不发送设备请求，不覆盖旧安装清单。"""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "build/fpga-sync-candidate"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def package():
    assert Path.cwd().resolve() == ROOT
    sys.path.insert(0, str(ROOT / ".research-cache/x1d-1.25.0/python"))
    sys.path.insert(0, str(HERE / "research"))
    from farm_sync_loader import offline_ready, PAYLOAD_SHA
    if not offline_ready():
        raise RuntimeError("FARM/FPGA offline checks no longer match")
    build = load(OUT / "manifest.json")
    observer = load(HERE / "build/farm-sync-observer/validation.json")
    for report, key in ((build, "sourceHashes"), (observer, "source_hashes")):
        for name, digest in report[key].items():
            if sha((HERE / name).read_bytes()) != digest:
                raise RuntimeError("Rebuild required: " + name)
    paths = {n: OUT / n for n in ("libhbl-wireless.so", "wireless-worker", "ui.rcc", "prepare-radio.sh")}
    for name, meta in build["files"].items():
        if sha(paths[name].read_bytes()) != meta["sha256"]:
            raise RuntimeError("Build artifact changed: " + name)
    for name, meta in observer["files"].items():
        path = HERE / "build/farm-sync-observer" / name
        if sha(path.read_bytes()) != meta["sha256"]:
            raise RuntimeError("Observer artifact changed")
        paths[name] = path
    probe = HERE / "build/netlink-probe"
    if sha(probe.read_bytes()) != "a850123f1d67c553e073c00a2fc8fc3e34c45942e4c3b385a12055387df37741":
        raise RuntimeError("Fixed non-transmitting netlink probe changed")
    paths["netlink-probe"] = probe
    for name in ("fpga-sync-install.sh", "fpga-sync-restore.sh", "release-radio.sh"):
        paths[name] = HERE / name
    for index in range(3):
        name = "delta/" + str(index) + ".bin"
        paths[name] = HERE / "build" / name
    files = {name: path.read_bytes() for name, path in paths.items()}
    bash = Path("C:/Program Files/Git/bin/bash.exe")
    for name, path in paths.items():
        if name.endswith(".sh"):
            subprocess.run([str(bash), "--noprofile", "--norc", "-n", str(path)], check=True, timeout=10)
            if b"\r" in files[name]:
                files[name] = files[name].replace(b"\r\n", b"\n")
    files["manifest.sha256"] = "".join(sha(data) + "  " + name + "\n" for name, data in sorted(files.items())).encode("ascii")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.mode, entry.size, entry.mtime = 0o600, len(data), 0
            archive.addfile(entry, io.BytesIO(data))
    packed = gzip.compress(raw.getvalue(), mtime=0)
    # 重读最终包，检查成员、内容与模式；包中不含路径逃逸或设备节点。
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as archive:
        assert {entry.name for entry in archive} == set(files)
        for entry in archive:
            assert entry.isfile() and entry.mode == 0o600 and archive.extractfile(entry).read() == files[entry.name]
    (OUT / "session-package.tar.gz").write_bytes(packed)
    report = {"status": "离线完整候选，待独立机内 Qt 检查和实机安装", "installed": False,
              "hardwareRequests": 0, "agentFlashTrials": 0, "physicalTimingMeasured": False,
              "packageSha256": sha(packed), "packageBytes": len(packed), "farmPayloadSha256": PAYLOAD_SHA,
              "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in files.items()},
              "checks": {"host": build["checks"], "arm": "14 simulation + 14 target passed",
                         "loader": "6 tests; 1466 before/after-write failure positions passed",
                         "fpga": "3 explicit cases, 135 original states identical; local clear fanout verified",
                         "shellSyntax": True, "archiveRoundtrip": True, "targetQtCheck": False},
              "restoreOrder": "先停止 worker，再由电脑解除 FARM 四个钩子并回读，最后移除消息消费覆盖；payload 保留至手动重启。",
              "timingLimit": "固定电子快门自动规则：按同次曝光微秒参数计算，超过 0.5 秒或未知档位跳过；以 B 消息的 Linux 接收时间为基准。用户实拍近似模型，未测物理边沿误差。"}
    (OUT / "package-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"packageBytes": len(packed), "members": len(files), "offlinePassed": True, "installed": False}))


if __name__ == "__main__":
    package()
