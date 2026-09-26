"""构建 FPGA 同步版界面/常驻程序；独立输出，不替换已安装版本清单。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "build/fpga-sync-candidate"
PREPARED_SHA = "654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688"


def build():
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError("workspace mismatch")
    OUT.mkdir(exist_ok=True)
    common = {"__name__": "wireless_build_helpers", "__file__": str(HERE / "build.py")}
    exec(compile((HERE / "build.py").read_text(encoding="utf-8"), str(HERE / "build.py"), "exec"), common)
    common["OUT"] = OUT
    qml_hashes = common["patch_qml"]()
    cache, baseline, compiler = common["CACHE"], common["BASELINE"], common["COMPILER"]
    include = OUT / "include/QtCore"
    include.mkdir(parents=True, exist_ok=True)
    (include / "qconfig.h").write_text("#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n")
    (include / "qfeatures.h").write_text("/* Fixed public Qt ABI. */\n")
    env = dict(os.environ)
    for key, name in (("ZIG_GLOBAL_CACHE_DIR", "global-cache"), ("ZIG_LOCAL_CACHE_DIR", "local-cache"), ("TEMP", "tmp"), ("TMP", "tmp")):
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    qt = cache / "qt-public"
    base = qt / "qtbase-opensource-src-5.5.1"
    flags = ["-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-marm", "-O2", "-fPIC", "-fno-stack-protector",
             "-I", str(OUT / "include"), "-isystem", str(base / "include"), "-isystem", str(qt / "qtdeclarative-opensource-src-5.5.1/include"),
             "-I", str(base / "mkspecs/linux-arm-gnueabi-g++"), "-Wno-deprecated-declarations", "-Wno-enum-constexpr-conversion", "-Wall", "-Wextra"]
    commands = []
    def run(args):
        result = subprocess.run([str(compiler)] + args, env=env, capture_output=True, text=True, timeout=60)
        commands.append({"arguments": args, "exit": result.returncode, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr)
    layout = OUT / "relocations.ld"
    layout.write_text("SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n")
    libs = [baseline / ("usr/lib/libQt5" + module + ".so.5.5.1") for module in ("Qml", "Core", "Network", "DBus")]
    libs += [baseline / p for p in ("usr/lib/libappscommon.so.1.0.0", "usr/lib/libstdc++.so.6.0.21", "lib/libgcc_s.so.1", "lib/libdl-2.22.so", "lib/libc-2.22.so")]
    for name, output, kind in (("wireless_runtime", "libhbl-wireless.so", "-shared"), ("wireless_worker", "wireless-worker", "-no-pie")):
        obj = OUT / (name + ".o")
        run(["c++", "-std=c++11"] + flags + ["-c", str(HERE / ("native/" + name + ".cpp")), "-o", str(obj)])
        link = ["cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", kind, "-Wl,--no-undefined", "-Wl,-s", "-Wl,-T," + str(layout)]
        if kind == "-shared":
            link.append("-Wl,-soname,libhbl-wireless.so")
        run(link + [str(obj)] + [str(p) for p in libs] + ["-o", str(OUT / output)])
    checks = {}
    for name in ("native_core", "bridge", "netlink_wire", "farm_sync_wire", "es_timing"):
        exe = OUT / (name + ".test.exe")
        run(["cc", "-std=c11", "-O2", str(HERE / ("CodeTests/" + name + ".test.c")), "-o", str(exe)])
        result = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        checks[name] = result.stdout.strip()
    files = {}
    for name in ("libhbl-wireless.so", "wireless-worker"):
        artifact = OUT / name
        elf = common["ArmElf"](artifact.read_bytes())
        rel, plt = (elf.elf.get_section_by_name(n) for n in (".rel.dyn", ".rel.plt"))
        if rel["sh_addr"] + rel["sh_size"] != plt["sh_addr"]:
            raise RuntimeError("REL/JMPREL discontinuity")
        files[name] = {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "bytes": artifact.stat().st_size, "relocations_contiguous": True}
    for name in ("ui.rcc",):
        artifact = OUT / name
        files[name] = {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "bytes": artifact.stat().st_size}
    prepared = (HERE / "build/prepared-wltest.bin").read_bytes()
    if hashlib.sha256(prepared).hexdigest() != PREPARED_SHA:
        raise RuntimeError("prepared radio bytes changed")
    (OUT / "prepared-wltest.bin").write_bytes(prepared)
    (OUT / "prepare-radio.sh").write_text((HERE / "prepare-radio.sh.in").read_text(encoding="ascii").replace("@FIRMWARE_SHA256@", PREPARED_SHA), encoding="ascii", newline="\n")
    report = {"status": "FPGA 同步版离线候选；未安装", "files": files, "checks": checks, "qml": qml_hashes,
              "preparedFirmwareSha256": PREPARED_SHA, "preparedFirmwareUnchanged": True,
              "sourceKind": "gfs3-es-fixed-auto", "availableSources": [0],
              "factoryNotificationSubscription": False,
              "hardwareRequests": 0, "installed": False, "physicalTimingMeasured": False,
              "fixedElectronicRule": {"scanUs":295000,"shortEndUs":590000,"longEndUs":890000,"maximumExposureUs":500000},
              "timing": "电子快门 B 消息附带本次曝光参数，按用户实拍近似模型固定计算延迟；超过 0.5 秒不自动引闪。基准为 Linux 接收时间。",
              "sourceHashes": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [Path(__file__), HERE / "build.py"] + list((HERE / "native").glob("*.h")) +
                                        [HERE / "native/wireless_worker.cpp", HERE / "native/wireless_runtime.cpp",
                                         HERE / "ui/main_additions.qml.inc", HERE / "ui/settings_additions.qml.inc"]},
              "commands": commands}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
