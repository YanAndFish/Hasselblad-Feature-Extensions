"""构建独立的 GFS1 分发候选及纯内存检查程序；不更新安装包，不访问设备。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
CACHE = ROOT / ".research-cache/x1d-1.25.0"
BASELINE = CACHE / "baseline"
OUT = HERE / "build/farm-sync-observer"
COMPILER = CACHE / "toolchain/zig-windows-x86_64-0.13.0/zig.exe"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("必须在本任务 Hasselblad 工作目录内构建")
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(HERE / "build/zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(HERE / "build/zig-local-cache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    temporary = OUT / "tmp"
    temporary.mkdir(exist_ok=True)
    env["TEMP"] = env["TMP"] = str(temporary)
    qt = CACHE / "qt-public/qtbase-opensource-src-5.5.1"
    flags = ["-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-marm",
             "-O2", "-fPIC", "-fno-stack-protector", "-I", str(HERE / "build/include"),
             "-isystem", str(qt / "include"), "-I", str(qt / "mkspecs/linux-arm-gnueabi-g++"),
             "-Wno-deprecated-declarations", "-Wno-enum-constexpr-conversion", "-Wall", "-Wextra"]
    libs = [BASELINE / name for name in (
        "usr/lib/libQt5Core.so.5.5.1", "usr/lib/libstdc++.so.6.0.21",
        "lib/libgcc_s.so.1", "lib/libdl-2.22.so", "lib/libc-2.22.so")]
    layout = OUT / "relocations.ld"
    layout.write_text("SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n")
    commands = []

    def run(arguments):
        command = [str(COMPILER)] + arguments
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
        commands.append({"arguments": arguments, "exit": result.returncode, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr)
        return result

    for name in ("farm_sync_observer", "farm_sync_hook_check"):
        run(["c++", "-std=c++11"] + flags +
            ["-c", str(HERE / ("native/" + name + ".cpp")), "-o", str(OUT / (name + ".o"))])
    common = ["cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9",
              "-Wl,--no-undefined", "-Wl,-s", "-Wl,-T," + str(layout)]
    shared = OUT / "libhbl-farm-sync-observer.so"
    check = OUT / "farm-sync-hook-check"
    run(common + ["-shared", "-Wl,-soname,libhbl-farm-sync-observer.so",
                  str(OUT / "farm_sync_observer.o")] + [str(p) for p in libs] + ["-o", str(shared)])
    run(common + ["-no-pie", "-Wl,--export-dynamic", str(OUT / "farm_sync_hook_check.o")] +
        [str(p) for p in libs] + ["-o", str(check)])
    native_test = OUT / "farm_sync_wire.test.exe"
    run(["cc", "-std=c11", "-O2", str(HERE / "CodeTests/farm_sync_wire.test.c"), "-o", str(native_test)])
    verified = subprocess.run([str(native_test)], capture_output=True, text=True, timeout=10)
    if verified.returncode:
        raise RuntimeError(verified.stdout + verified.stderr)
    sys.path.insert(0, str(ROOT / "x1d/tools"))
    from binary import ArmElf
    outputs = {}
    for artifact in (shared, check):
        elf = ArmElf(artifact.read_bytes())
        rel = elf.elf.get_section_by_name(".rel.dyn")
        plt = elf.elf.get_section_by_name(".rel.plt")
        if rel["sh_addr"] + rel["sh_size"] != plt["sh_addr"]:
            raise RuntimeError("旧版加载器所需的 REL/JMPREL 连续性检查失败")
        outputs[artifact.name] = {"sha256": digest(artifact), "bytes": artifact.stat().st_size,
                                  "relocations_contiguous": True}
    report = {
        "status": "compiled; host sync-wire checks passed; target Qt separation check pending",
        "source_firmware": "official X1D 1.25.0 wedge",
        "msg2dbus_sha256": "988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1",
        "signal_evidence": {"ReceiveMessage": "0x54f60", "activate_call": "0x54f90",
                            "meta_object": "0x7e32c", "argument": "QByteArray", "signal_index": 0},
        "files": outputs,
        "source_hashes": {name: digest(HERE / name) for name in (
            "native/farm_sync_wire.h", "native/farm_sync_observer.cpp",
            "native/farm_sync_hook_check.cpp", "CodeTests/farm_sync_wire.test.c")},
        "commands": commands,
        "host_wire_check": json.loads(verified.stdout),
        "target_check_run": False, "installed": False, "hardware_requests": 0,
        "uses_fpga_sync_flags": True, "physical_timing_measured": False,
        "radio_submission": False,
    }
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
