"""仅在本模块目录构建临时试用包；不访问相机，不自动安装。"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, BASELINE, CACHE, qml_files
sys.path.insert(0, str(HERE / "firmware"))
from prepared_flash import build as build_prepared_firmware

OUT = HERE / "build"
COMPILER = CACHE / "toolchain/zig-windows-x86_64-0.13.0/zig.exe"
GUI_SHA = "d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qhash(text):
    h = 0
    for c in text:
        h = (h << 4) + ord(c)
        h ^= (h & 0xF0000000) >> 23
        h &= 0x0FFFFFFF
    return h


def rcc(files):
    """Qt 5.5.1 v1，固定根目录；以原厂散列排序规则生成最小覆盖资源。"""
    root = {"name": "", "children": {}}
    for path, text in files.items():
        node = root
        parts = path.strip("/").split("/")
        for part in parts:
            node = node.setdefault("children", {}).setdefault(part, {"name": part})
        node["text"] = text
    nodes = [root]
    for node in nodes:
        if "children" in node:
            children = sorted(node["children"].values(), key=lambda x: (qhash(x["name"]), x["name"]))
            node["first"] = len(nodes)
            nodes.extend(children)
    names = bytearray()
    payload = bytearray()
    tree = bytearray()
    for node in nodes:
        name = node["name"]
        offset = len(names)
        names += struct.pack(">HI", len(name), qhash(name)) + name.encode("utf-16-be")
        if "children" in node:
            tree += struct.pack(">IHII", offset, 2, len(node["children"]), node["first"])
        else:
            text = node["text"].encode("utf-8")
            compressed = struct.pack(">I", len(text)) + zlib.compress(text, 9)
            tree += struct.pack(">IHHHI", offset, 1, 0, 1, len(payload))
            payload += struct.pack(">I", len(compressed)) + compressed
    return b"qres" + struct.pack(">IIII", 1, 20 + len(payload) + len(names), 20, 20 + len(payload)) + payload + names + tree


def patch_qml():
    original = (BASELINE / "usr/bin/victory-gui").read_bytes()
    if sha(original) != GUI_SHA:
        raise RuntimeError("原生 GUI 与固定基线不符")
    files = qml_files(ArmElf(original))
    if not isinstance(files, dict):
        files = dict(files)
    main = files["/main.qml"]
    settings = files["/settings/SettingsGeneric.qml"]
    if "Component.onDestruction" in main:
        raise RuntimeError("原主页面已有销毁处理器，需人工合并")
    additions = (HERE / "ui/main_additions.qml.inc").read_text(encoding="utf-8")
    main = main[:main.rfind("}")] + additions + "\n}\n"
    additions = (HERE / "ui/settings_additions.qml.inc").read_text(encoding="utf-8")
    if "onItemValuesChanged:" in settings:
        raise RuntimeError("原设置页已有切换处理器，需人工合并")
    settings = settings[:settings.rfind("}")] + additions + "\n}\n"
    import re
    settings, count = re.subn(r"(property bool preventSwipe:\s*)([^\n]+)", r"\1hblRfPanel.visible || (\2)", settings, count=1)
    if count != 1:
        raise RuntimeError("无法定位原厂 preventSwipe 门控")
    edited = {"/main.qml": main, "/settings/SettingsGeneric.qml": settings}
    for path, text in edited.items():
        target = OUT / "qml" / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (OUT / "ui.rcc").write_bytes(rcc(edited))
    return {p: sha(t.encode()) for p, t in edited.items()}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    firmware = build_prepared_firmware()
    firmware_checked = subprocess.run([sys.executable, "-B", str(HERE / "CodeTests/prepared_firmware.test.py")],
                                      capture_output=True, text=True, check=True)
    loader = (HERE / "prepare-radio.sh.in").read_text(encoding="ascii")
    (OUT / "prepare-radio.sh").write_text(loader.replace("@FIRMWARE_SHA256@", firmware["preparedSha256"]), encoding="ascii", newline="\n")
    qml_hashes = patch_qml()
    include = OUT / "include/QtCore"
    include.mkdir(parents=True, exist_ok=True)
    (include / "qconfig.h").write_text("#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n")
    (include / "qfeatures.h").write_text("/* 固定 Qt 公共 ABI，无功能裁剪覆盖。 */\n", encoding="utf-8")
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(OUT / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(OUT / "zig-local-cache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    qt = CACHE / "qt-public"
    base = qt / "qtbase-opensource-src-5.5.1"
    declarative = qt / "qtdeclarative-opensource-src-5.5.1"
    flags = ["-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-marm", "-O2", "-fPIC", "-fno-stack-protector",
             "-I", str(OUT / "include"), "-isystem", str(base / "include"), "-isystem", str(declarative / "include"),
             "-I", str(base / "mkspecs/linux-arm-gnueabi-g++"), "-Wno-deprecated-declarations", "-Wno-enum-constexpr-conversion", "-Wall", "-Wextra"]
    obj = OUT / "wireless_runtime.o"
    subprocess.run([str(COMPILER), "c++", "-std=c++11"] + flags + ["-c", str(HERE / "native/wireless_runtime.cpp"), "-o", str(obj)], env=env, check=True)
    libs = [BASELINE / ("usr/lib/libQt5" + module + ".so.5.5.1") for module in ["Qml", "Core", "Network"]]
    libs += [BASELINE / "usr/lib/libappscommon.so.1.0.0", BASELINE / "usr/lib/libstdc++.so.6.0.21",
             BASELINE / "lib/libgcc_s.so.1", BASELINE / "lib/libdl-2.22.so", BASELINE / "lib/libc-2.22.so"]
    output = OUT / "libhbl-wireless.so"
    # glibc 2.22 在立即绑定时把 REL 与 JMPREL 当作连续区间处理。
    # LLD 默认可能把 ARM.exidx 插在两者之间，须显式保持连续。
    layout = OUT / "relocations.ld"
    layout.write_text("SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n")
    subprocess.run([str(COMPILER), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-shared",
                    "-Wl,--no-undefined", "-Wl,-s", "-Wl,-T," + str(layout), "-Wl,-soname,libhbl-wireless.so", str(obj)] + [str(p) for p in libs] + ["-o", str(output)], env=env, check=True)
    worker_obj = OUT / "wireless_worker.o"
    subprocess.run([str(COMPILER), "c++", "-std=c++11"] + flags +
                   ["-c", str(HERE / "native/wireless_worker.cpp"), "-o", str(worker_obj)], env=env, check=True)
    worker_output = OUT / "wireless-worker"
    worker_libs = libs + [BASELINE / "usr/lib/libQt5DBus.so.5.5.1"]
    subprocess.run([str(COMPILER), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9",
                    "-no-pie", "-Wl,--no-undefined", "-Wl,-s", "-Wl,-T," + str(layout), str(worker_obj)] +
                   [str(p) for p in worker_libs] + ["-o", str(worker_output)], env=env, check=True)
    probe_output = OUT / "netlink-probe"
    subprocess.run([str(COMPILER), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-O2",
                    "-no-pie", "-Wl,-s", "-Wl,-T," + str(layout), str(HERE / "native/netlink_probe.c"),
                    "-o", str(probe_output)], env=env, check=True)
    test = OUT / "native_core.test.exe"
    subprocess.run([str(COMPILER), "cc", "-std=c11", "-O2", str(HERE / "CodeTests/native_core.test.c"), "-o", str(test)], env=env, check=True)
    checked = subprocess.run([str(test)], capture_output=True, text=True, check=True)
    protocol_checks = {}
    for name in ["bridge", "netlink_wire"]:
        binary = OUT / (name + ".test.exe")
        subprocess.run([str(COMPILER), "cc", "-std=c11", "-O2", str(HERE / ("CodeTests/" + name + ".test.c")),
                        "-o", str(binary)], env=env, check=True)
        check = subprocess.run([str(binary)], capture_output=True, text=True, check=True)
        protocol_checks[name] = json.loads(check.stdout)
    elf = ArmElf(output.read_bytes())
    rel = elf.elf.get_section_by_name(".rel.dyn")
    plt = elf.elf.get_section_by_name(".rel.plt")
    if rel["sh_addr"] + rel["sh_size"] != plt["sh_addr"]:
        raise RuntimeError("动态重定位表不连续，拒绝生成旧版加载器试用包")
    worker_elf = ArmElf(worker_output.read_bytes())
    worker_rel = worker_elf.elf.get_section_by_name(".rel.dyn")
    worker_plt = worker_elf.elf.get_section_by_name(".rel.plt")
    if worker_rel["sh_addr"] + worker_rel["sh_size"] != worker_plt["sh_addr"]:
        raise RuntimeError("常驻程序动态重定位表不连续")
    manifest = {"status": "compiled-resident-receiver-not-installed", "cameraAccess": False, "installed": False,
                "availableSources": [0], "inputGuiSha256": GUI_SHA, "qml": qml_hashes,
                "rccSha256": sha((OUT / "ui.rcc").read_bytes()), "runtimeSha256": sha(output.read_bytes()),
                "workerSha256": sha(worker_output.read_bytes()), "protocolChecks": protocol_checks,
                "probeSha256": sha(probe_output.read_bytes()),
                "nativeCheck": checked.stdout.strip(),
                "preparedFirmwareCheck": json.loads(firmware_checked.stdout),
                "preparedFirmwareSha256": firmware["preparedSha256"],
                "needed": [e.needed for e in elf.elf.get_section_by_name(".dynamic").iter_tags() if e.entry.d_tag == "DT_NEEDED"],
                "timing": "原厂曝光通知由常驻进程接收；设置时准备波形与驱动通道，触发时直接下发一次正常驱动请求；物理延迟未测量"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
