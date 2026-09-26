"""固定 v3 C 核心作逐字节回归基线；只运行宿主人工像素，不运行 Qt/设备。"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts/pixels"
REFERENCE = ROOT / "x1d/candidates/replay-v3/native/display_pixels.c"
COMPILER = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def run():
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == "efaee92b4cc9072d6e30ee198a432743553421e15b9aa39962ce617c53d4e79d"
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for key, subdir in (("ZIG_GLOBAL_CACHE_DIR","zig-global-cache"),("ZIG_LOCAL_CACHE_DIR","zig-local-cache"),("TEMP","tmp"),("TMP","tmp")):
        env[key] = str(OUT / subdir)
        (OUT / subdir).mkdir(exist_ok=True)
    flags = ["-O2","-Wall","-Wextra","-Werror"]
    commands = [
        [str(COMPILER),"cc","-std=c11",*flags,"-Dxj_display_bgra=reference_display_bgra","-Dxj_orient_bgra=reference_orient_bgra",
         "-c",str(REFERENCE),"-o",str(OUT / "reference.o")],
        [str(COMPILER),"cc","-std=c11",*flags,"-c",str(HERE / "native/display_pixels.c"),"-o",str(OUT / "candidate.o")],
        [str(COMPILER),"c++","-std=c++11",*flags,str(HERE / "CodeTests/pixels.test.cpp"),str(OUT / "reference.o"),str(OUT / "candidate.o"),"-o",str(OUT / "pixels.test.exe")]
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
        (OUT / f"compile-{index}.log").write_text(result.stdout + result.stderr,encoding="utf-8")
        result.check_returncode()
    result = subprocess.run([str(OUT / "pixels.test.exe")],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
    (OUT / "test-output.txt").write_text(result.stdout + result.stderr,encoding="utf-8")
    result.check_returncode()
    report = json.loads(result.stdout)
    sources = [REFERENCE,HERE / "native/display_pixels.c",HERE / "native/display_pixels.h",HERE / "native/display_tables.h",
               HERE / "native/display_fast_tables.h",HERE / "tools/generate_display_fast_tables.py",HERE / "CodeTests/pixels.test.cpp",Path(__file__)]
    report.update({
        "firmwareSource":"X1D-50c 1.25.0; exact fixed-v3 color and orientation outputs",
        "scope":"Host x86_64 Windows artificial BGRA. Separate pixel stages only; no JPEG decoder, Storage, Qt, GPU or camera.",
        "targetLatencyMeasured":False,"cameraRequests":0,"targetRuntimeRun":False,
        "testMemoryScope":"Host oracle keeps reference and candidate full arrays; production function only mutates one pixel array.",
        "compiler":"Zig 0.13.0/Clang O2",
        "sources":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    })
    (OUT / "validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "sources"},ensure_ascii=False))


if __name__ == "__main__": run()
