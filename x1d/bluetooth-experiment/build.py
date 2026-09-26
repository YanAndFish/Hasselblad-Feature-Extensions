"""仅在本实验目录构建和运行离线测试；不访问相机。"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build"
ZIG = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if Path.cwd().resolve() != ROOT:
        raise SystemExit("必须从已授权的 Hasselblad 工作区运行")
    for name in ("tmp", "zig-local", "zig-global"):
        (BUILD / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TEMP=str(BUILD / "tmp"), TMP=str(BUILD / "tmp"),
               ZIG_LOCAL_CACHE_DIR=str(BUILD / "zig-local"),
               ZIG_GLOBAL_CACHE_DIR=str(BUILD / "zig-global"))
    sources = [HERE / "native/bt_hci.c", HERE / "native/self_test.c"]
    base = [str(ZIG), "cc", "-O2", "-s", "-Wall", "-Wextra", "-Werror", "-std=c11"]
    outputs = {}
    for target, flags, name in (
        ("host", [], "bt-hci-offline-test.exe"),
        ("arm", ["-target", "arm-linux-musleabihf", "-mcpu=cortex_a9", "-marm", "-static"],
         "x1d-bt-protocol-test"),
    ):
        out = BUILD / name
        subprocess.run(base + flags + list(map(str, sources)) + ["-o", str(out)],
                       cwd=HERE, env=env, check=True)
        outputs[target] = out
    test = subprocess.run([str(outputs["host"]), "--self-test"], capture_output=True,
                          text=True, env=env, check=True)
    for denied in ([], ["--scan"], ["--advertise"], ["--device", "/dev/ttymxc4"]):
        result = subprocess.run([str(outputs["host"])] + denied, capture_output=True,
                                text=True, env=env)
        if result.returncode != 2 or "hardware_binding_unverified" not in result.stderr:
            raise RuntimeError("未确认硬件绑定的入口未拒绝")
    raw = outputs["arm"].read_bytes()
    if raw[:6] != b"\x7fELF\x01\x01" or struct.unpack_from("<H", raw, 18)[0] != 40:
        raise RuntimeError("目标不是 ELF32 little-endian ARM")
    phoff = struct.unpack_from("<I", raw, 28)[0]
    phsize, phnum = struct.unpack_from("<HH", raw, 42)
    if any(struct.unpack_from("<I", raw, phoff + i * phsize)[0] == 3 for i in range(phnum)):
        raise RuntimeError("目标意外依赖动态解释器")
    report = {
        "stage": "offline-protocol-candidate",
        "hardware_binding": "unverified",
        "radio_discovery": "not-tested",
        "camera_execution": "not-tested",
        "host_self_test": test.stdout.strip(),
        "live_entry_rejection": "passed",
        "arm_elf": {"class": 32, "machine": "ARM", "interpreter": None},
        "compiler_sha256": sha(ZIG),
        "sources": {str(p.relative_to(HERE)): sha(p) for p in
                    sources + [HERE / "native/bt_hci.h", Path(__file__).resolve()]},
        "artifacts": {key: {"path": str(path.relative_to(HERE)), "bytes": path.stat().st_size,
                            "sha256": sha(path)} for key, path in outputs.items()},
    }
    (BUILD / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
