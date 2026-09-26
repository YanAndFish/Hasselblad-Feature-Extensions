"""同一 C 实现构建为 ARM ELF 与 Windows 离线验证 DLL。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".research-cache" / "x1d-1.25.0"
COMPILER = CACHE / "toolchain" / "zig-windows-x86_64-0.13.0" / "zig.exe"
OUT = ROOT / "x1d" / "artifacts" / "jpeg-container-v1"


def run() -> None:
    if not COMPILER.is_file():
        raise SystemExit("先运行 x1d/tools/prepare_native_toolchain.py")
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(CACHE / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(CACHE / "zig-local-cache")
    common = [str(COMPILER), "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
              "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-nostdlib", "-shared",
              "x1d/native/jpeg_container.c", "x1d/native/jpeg_preview.c", "x1d/native/display_pixels.c"]
    targets = [
        ("libx1d-jpeg-container.so", ["-target", "arm-linux-musleabihf", "-mcpu=cortex_a9", "-marm",
                                       "-fPIC", "-Wl,--no-undefined", "-Wl,-Bsymbolic"]),
        ("x1d-jpeg-container.dll", ["-target", "x86_64-windows-gnu", "-Wl,--entry,DllMain",
                                      "-Wl,--export-all-symbols", "x1d/CodeTests/jpeg_container/host_entry.c"]),
    ]
    commands = []
    for filename, flags in targets:
        command = common + flags + ["-o", str(OUT / filename)]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        commands.append({"output": filename, "flags": common[2:] + flags})
    sys.path.insert(0, str(ROOT / "x1d" / "tools"))
    from binary import ArmElf
    arm = ArmElf((OUT / targets[0][0]).read_bytes())
    undefined = sorted({s.name for s in arm.symbols if s["st_shndx"] == "SHN_UNDEF" and s.name})
    if undefined:
        raise ValueError("独立核心存在未解析符号：" + ",".join(undefined))
    exports = {s.name: s["st_value"] for s in arm.symbols if s.name.startswith("xj_") and s["st_value"]}
    sources = {}
    for name in ["x1d/native/jpeg_container.c", "x1d/native/jpeg_container.h",
                 "x1d/native/jpeg_preview.c", "x1d/native/jpeg_preview.h", "x1d/native/display_pixels.c",
                 "x1d/native/display_pixels.h", "x1d/native/display_tables.h"]:
        sources[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    report = {"status": "standalone-native-component-not-integrated", "compiler": "Zig 0.13.0",
              "cameraAccess": False, "firmwarePatched": False, "sources": sources,
              "commands": commands, "armExports": exports, "armUndefinedSymbols": undefined,
              "outputs": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name, _ in targets}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("JPEG 容器 C 核心已构建：ARM ELF 无未解析符号；Windows DLL 用于离线验证。尚未接入原生进程。")


if __name__ == "__main__":
    run()
