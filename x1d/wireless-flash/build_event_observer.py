"""只构建被动时序观察器；不访问相机、不重建或覆盖现有插件包。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, BASELINE, CACHE


def run():
    out = HERE / "build/event-observer-build"
    out.mkdir(parents=True, exist_ok=True)
    compiler = CACHE / "toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    base = CACHE / "qt-public/qtbase-opensource-src-5.5.1"
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(HERE / "build/zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(HERE / "build/zig-local-cache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    flags = ["-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-marm", "-O2", "-fPIC", "-fno-stack-protector",
             "-I", str(HERE / "build/include"), "-isystem", str(base / "include"),
             "-I", str(base / "mkspecs/linux-arm-gnueabi-g++"), "-Wno-deprecated-declarations", "-Wno-enum-constexpr-conversion", "-Wall", "-Wextra"]
    obj = out / "event_observer.o"
    subprocess.run([str(compiler), "c++", "-std=c++11"] + flags +
                   ["-c", str(HERE / "native/event_observer.cpp"), "-o", str(obj)], env=env, check=True)
    libs = [BASELINE / ("usr/lib/libQt5" + name + ".so.5.5.1") for name in ["Core", "DBus"]]
    libs += [BASELINE / "usr/lib/libappscommon.so.1.0.0", BASELINE / "usr/lib/libstdc++.so.6.0.21",
             BASELINE / "lib/libgcc_s.so.1", BASELINE / "lib/libdl-2.22.so", BASELINE / "lib/libc-2.22.so"]
    output = out / "event-observer"
    layout = out / "relocations.ld"
    layout.write_text("SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n")
    subprocess.run([str(compiler), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-no-pie",
                    "-Wl,--no-undefined", "-Wl,-s", "-Wl,-T," + str(layout), str(obj)] +
                   [str(path) for path in libs] + ["-o", str(output)], env=env, check=True)
    elf = ArmElf(output.read_bytes()).elf
    rel, plt = [elf.get_section_by_name(name) for name in [".rel.dyn", ".rel.plt"]]
    if rel["sh_addr"] + rel["sh_size"] != plt["sh_addr"]:
        raise RuntimeError("动态重定位表不连续")
    manifest = {
        "status": "compiled-passive-observer-not-installed",
        "sourceFirmware": "X1D 1.25.0",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "cameraRequests": 0,
        "flashRequestsImplemented": False,
        "cameraMethodCallsImplemented": False,
        "maximumSeconds": 300,
        "maximumSamples": 512,
        "records": ["elapsed_us", "event"],
        "discardsExposureValue": True,
        "needed": [tag.needed for tag in elf.get_section_by_name(".dynamic").iter_tags() if tag.entry.d_tag == "DT_NEEDED"],
        "relocationsContiguous": True,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
