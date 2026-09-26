"""只构建/执行宿主人工像素与缓存检查；输出均位于 replay-next。"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts" / "checks"
COMPILER = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(OUT / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(OUT / "zig-local-cache")
    flags = ["-O2", "-Wall", "-Wextra", "-Werror"]
    obj = OUT / "display_pixels.o"
    commands = [
        [str(COMPILER), "cc", "-std=c11", *flags, "-c", str(HERE / "native/display_pixels.c"), "-o", str(obj)],
        [str(COMPILER), "c++", "-std=c++11", *flags, str(HERE / "CodeTests/preview_cache.test.cpp"), str(obj), "-o", str(OUT / "preview-cache.test.exe")],
    ]
    compiler_log = []
    for command in commands:
        compilation = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        compiler_log.append(compilation.stdout + compilation.stderr)
        (OUT / "compiler.log").write_text("\n".join(compiler_log), encoding="utf-8")
        compilation.check_returncode()
    result = subprocess.run([str(OUT / "preview-cache.test.exe")], cwd=ROOT, check=True, capture_output=True, text=True, timeout=90)
    report = json.loads(result.stdout)
    report.update({
        "firmwareSource": "X1D-50c 1.25.0; replay-next exact interval color tables and bounded tile orientation",
        "hostTimingScope": "Artificial BGRA fill/allocation + candidate Adobe conversion + candidate orientation 6 + actual PreviewCache. No JPEG decoder, Storage, Qt, GPU, camera or user photographs.",
        "fullTimingScope": "Host x86_64 native C only. Separate candidate Adobe conversion and orientation-6 stages; no decode or texture upload.",
        "notTargetLatency": True,
        "sourceHashes": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [HERE / "native/preview_cache.h", HERE / "native/display_pixels.c", HERE / "native/display_pixels.h",
                                   HERE / "native/display_tables.h", HERE / "native/display_fast_tables.h", Path(__file__), HERE / "CodeTests/preview_cache.test.cpp"]},
        "compiler": "Zig 0.13.0/Clang, host x86_64 Windows, O2",
        "commands": commands,
    })
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("commands", "sourceHashes")}, ensure_ascii=False))


if __name__ == "__main__":
    run()
