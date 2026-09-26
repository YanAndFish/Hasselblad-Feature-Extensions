"""用固定 Qt 5.5.1 公共头和原镜像库构建本地候选；不安装或修改服务。"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "x1d" / "tools"))
from binary import ArmElf, BASELINE, CACHE

OUT = ROOT / "x1d" / "artifacts" / "replay-adapter-v1"
BUILD = CACHE / "adapter-build"
COMPILER = CACHE / "toolchain" / "zig-windows-x86_64-0.13.0" / "zig.exe"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    include = BUILD / "include" / "QtCore"
    include.mkdir(parents=True, exist_ok=True)
    # 无 namespace、共享 Qt、双精度 qreal；新模块仅用核对过的公共 ABI。
    (include / "qconfig.h").write_text("#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n", encoding="utf-8")
    (include / "qfeatures.h").write_text("/* No QT_NO feature overrides; public ABI only. */\n", encoding="utf-8")
    qt = CACHE / "qt-public"
    base = qt / "qtbase-opensource-src-5.5.1"
    declarative = qt / "qtdeclarative-opensource-src-5.5.1"
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(CACHE / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(CACHE / "zig-local-cache")
    bindings = {
        "X1D_JPEG_SHA256": ROOT / "x1d/artifacts/jpeg-failure-v1/jpeg-daemon.elf",
        "X1D_GUI_SHA256": BASELINE / "usr/bin/victory-gui",
        "X1D_APPS_SHA256": BASELINE / "usr/lib/libappscommon.so.1.0.0",
        "X1D_TURBO_SHA256": BASELINE / "usr/lib/libturbojpeg.so.0.1.0",
    }
    for short, module in [("CORE", "Core"), ("DBUS", "DBus"), ("GUI", "Gui"), ("QUICK", "Quick"), ("QML", "Qml")]:
        bindings["X1D_QT" + short + "_SHA256"] = BASELINE / ("usr/lib/libQt5" + module + ".so.5.5.1")
    definitions = []
    hashes = {}
    for name, path in bindings.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        definitions += ["-D" + name + '=\"' + digest + '\"']
        hashes[path.relative_to(ROOT).as_posix()] = digest
    (BUILD / "bindings.h").write_text("\n".join("#define " + d[2:].replace("=", " ", 1) for d in definitions) + "\n", encoding="utf-8")
    flags = ["-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-marm", "-O2", "-fPIC", "-fno-stack-protector",
             "-I", str(BUILD / "include"), "-isystem", str(base / "include"), "-isystem", str(declarative / "include"),
             "-isystem", str(base / "src/3rdparty/angle/include"),
             "-I", str(base / "mkspecs/linux-arm-gnueabi-g++"), "-include", str(BUILD / "bindings.h"),
             "-Wno-deprecated-declarations", "-Wno-enum-constexpr-conversion", "-Wall", "-Wextra"]
    cpp = ["x1d/native/replay_runtime.cpp", "x1d/native/jpeg_adapter.cpp"]
    provider = ROOT / "x1d/native/replay_provider.cpp"
    if provider.exists():
        cpp.append(provider.relative_to(ROOT).as_posix())
    objects = {}
    sources = ["x1d/native/jpeg_container.c", "x1d/native/jpeg_preview.c", "x1d/native/display_pixels.c"] + cpp
    for source in sources:
        obj = BUILD / (Path(source).stem + ".o")
        is_cpp = source.endswith(".cpp")
        command = [str(COMPILER), "c++" if is_cpp else "cc", "-std=c++11" if is_cpp else "-std=c11"] + flags
        subprocess.run(command + ["-c", source, "-o", str(obj)], cwd=ROOT, env=env, check=True)
        objects[Path(source).stem] = str(obj)
    common_libs = [BASELINE / "usr/lib/libQt5DBus.so.5.5.1", BASELINE / "usr/lib/libQt5Core.so.5.5.1",
                  BASELINE / "usr/lib/libappscommon.so.1.0.0", BASELINE / "usr/lib/libstdc++.so.6.0.21",
             BASELINE / "lib/libgcc_s.so.1", BASELINE / "lib/libdl-2.22.so", BASELINE / "lib/libc-2.22.so"]
    outputs = {}
    targets = [("libx1d-jpeg-adapter.so", ["jpeg_container", "jpeg_preview", "replay_runtime", "jpeg_adapter"], [])]
    if provider.exists():
        targets.append(("libx1d-replay-provider.so", ["jpeg_container", "display_pixels", "replay_runtime", "replay_provider"],
                        [BASELINE / ("usr/lib/libQt5" + module + ".so.5.5.1") for module in ["Quick", "Qml", "Gui", "Network"]]))
    for filename, modules, extra in targets:
        output = OUT / filename
        command = [str(COMPILER), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-shared", "-nostdlib",
                   "-Wl,--no-undefined", "-Wl,-soname," + filename] + [objects[n] for n in modules] + [str(p) for p in extra + common_libs] + ["-o", str(output)]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        elf = ArmElf(output.read_bytes())
        needed = [entry.needed for entry in elf.elf.get_section_by_name(".dynamic").iter_tags() if entry.entry.d_tag == "DT_NEEDED"]
        dyn = elf.elf.get_section_by_name(".dynsym")
        unresolved = sorted({s.name for s in dyn.iter_symbols() if s.name and s["st_shndx"] == "SHN_UNDEF"})
        exports = sorted({s.name for s in dyn.iter_symbols() if s["st_shndx"] != "SHN_UNDEF" and s.name})
        outputs[filename] = {"sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "needed": needed,
                             "dynamicImports": unresolved, "dynamicExports": exports}
    report = {"status": "compiled-native-adapter-runtime-integration-unverified", "cameraAccess": False,
              "installed": False, "compiler": "Zig 0.13.0 / Clang", "qtHeaders": "5.5.1 public source",
              "inputHashes": hashes, "outputs": outputs,
              "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("原生适配候选已链接到固定 ARM/Qt 库；尚未执行 Qt/DBus 集成或安装。")


if __name__ == "__main__":
    run()
