"""准备独立 Qt 内存自检包；不连接设备，不修改原服务或既有安装包。"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / "build/farm-reply-observer"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package():
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("必须在本任务 Hasselblad 工作目录内准备")
    report = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))
    names = ("libhbl-farm-reply-observer.so", "farm-reply-hook-check")
    payloads = {name: (OUT / name).read_bytes() for name in names}
    for name, data in payloads.items():
        if sha(data) != report["files"][name]["sha256"]:
            raise RuntimeError("产物与编译报告不符")
    for name, expected in report["source_hashes"].items():
        if sha((HERE / name).read_bytes()) != expected:
            raise RuntimeError("源码已改变，必须先重新构建")
    directory = "/tmp/hbl-farm-reply-check-" + sha(payloads[names[1]])[:12]
    libraries = ("usr/lib/libQt5Core.so.5.5.1", "usr/lib/libstdc++.so.6.0.21",
                 "lib/libgcc_s.so.1", "lib/libdl-2.22.so", "lib/libc-2.22.so")
    dependencies = {"/" + name: sha((ROOT / ".research-cache/x1d-1.25.0/baseline" / name).read_bytes())
                    for name in libraries}
    guards = "\n".join("printf '%s\\n' '" + digest + "  " + path + "' | sha256sum -c - >/dev/null"
                       for path, digest in dependencies.items())
    own_guards = "\n".join("[ -f '" + name + "' ] && [ ! -L '" + name + "' ]\n" +
                            "printf '%s\\n' '" + sha(data) + "  " + name + "' | sha256sum -c - >/dev/null"
                            for name, data in payloads.items())
    script = """#!/bin/sh
set -eu
PATH=/usr/bin:/bin
export PATH
umask 077
[ "$#" -eq 0 ]
ulimit -c 0
stage='{directory}'
[ -d "$stage" ] && [ ! -L "$stage" ]
[ "$(stat -c '%u:%a' "$stage")" = "$(id -u):700" ]
cd "$stage"
{own_guards}
{guards}
exec /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LD_BIND_NOW=1 \\
    LD_PRELOAD="$stage/libhbl-farm-reply-observer.so" \\
    HBL_FARM_REPLY_SELFTEST=1 HBL_FARM_REPLY_OBSERVE=0 \\
    "$stage/farm-reply-hook-check"
""".format(directory=directory, own_guards=own_guards, guards=guards)
    payloads["run.sh"] = script.encode("ascii")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in payloads.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o700, 0
            tar.addfile(info, io.BytesIO(data))
    packed = gzip.compress(archive.getvalue(), mtime=0)
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as tar:
        members = tar.getmembers()
        assert [entry.name for entry in members] == list(payloads)
        assert all(entry.isfile() and "/" not in entry.name and entry.mode == 0o700 for entry in members)
        assert all(tar.extractfile(entry).read() == payloads[entry.name] for entry in members)
    (OUT / "run-check.sh").write_bytes(payloads["run.sh"])
    (OUT / "selfcheck-package.tar.gz").write_bytes(packed)
    manifest = {
        "status": "prepared offline; not installed or executed on camera",
        "stage_directory": directory,
        "archive_sha256": sha(packed), "archive_bytes": len(packed),
        "files": {name: {"sha256": sha(data), "bytes": len(data)} for name, data in payloads.items()},
        "target_dependency_hashes": dependencies,
        "tar_contents_verified": True,
        "target_command": "sh " + directory + "/run.sh",
        "check_process_alarm_seconds_from_main": 5,
        "original_service_restart": False, "camera_hardware_requests": 0,
        "radio_submission": False, "camera_check_executed": False,
    }
    (OUT / "selfcheck-package.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(package(), ensure_ascii=False, indent=2))
