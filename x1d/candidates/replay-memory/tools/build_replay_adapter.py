"""用固定 Qt 5.5.1 公共头和原镜像库构建本地候选；不安装或修改服务。"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "x1d" / "tools"))
from binary import ArmElf, BASELINE, CACHE

OUT = ROOT / "x1d/candidates/replay-memory/artifacts/adapter"
BUILD = ROOT / "x1d/candidates/replay-memory/artifacts/build"
SOURCE = "x1d/candidates/replay-memory/native/"
COMPILER = CACHE / "toolchain" / "zig-windows-x86_64-0.13.0" / "zig.exe"


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    include = BUILD / "include" / "QtCore"
    include.mkdir(parents=True, exist_ok=True)
    # 无 namespace、共享 Qt、双精度 qreal；另含逐项核对的固定 Qt 私有入口。
    (include / "qconfig.h").write_text("#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n", encoding="utf-8")
    (include / "qfeatures.h").write_text("/* No QT_NO feature overrides; public ABI only. */\n", encoding="utf-8")
    qt = CACHE / "qt-public"
    base = qt / "qtbase-opensource-src-5.5.1"
    declarative = qt / "qtdeclarative-opensource-src-5.5.1"
    env = dict(os.environ)
    env["ZIG_GLOBAL_CACHE_DIR"] = str(BUILD / "zig-global-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(BUILD / "zig-local-cache")
    bindings = {
        "X1D_JPEG_SHA256": BASELINE / "usr/bin/jpeg-daemon",
        "X1D_GUI_SHA256": BASELINE / "usr/bin/victory-gui",
        "X1D_APPS_SHA256": BASELINE / "usr/lib/libappscommon.so.1.0.0",
        "X1D_TURBO_SHA256": BASELINE / "usr/lib/libturbojpeg.so.0.1.0",
        "X1D_GLES_SHA256": ROOT / "x1d/candidates/replay-next/artifacts/load-preparation/inputs/usr/lib/libGLESv2.so.2.0.0",
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
    cpp = [SOURCE + "replay_runtime.cpp"]
    provider = ROOT / (SOURCE + "replay_provider.cpp")
    if provider.exists():
        cpp.append(provider.relative_to(ROOT).as_posix())
        cpp.append(SOURCE + "ready_refresh.cpp")
        cpp.extend(SOURCE+n for n in ("replay_budget.cpp","replay_retry.cpp","safe_texture.cpp","replay_catalog.cpp"))
    objects = {}
    sources = [SOURCE + n for n in ["jpeg_container.c", "display_pixels.c"]] + cpp
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
    layout = BUILD / "relocations.ld"
    layout.write_text("SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n", encoding="ascii")
    targets = []
    if provider.exists():
        targets.append(("libx1d-replay-provider.so", ["jpeg_container", "display_pixels", "replay_runtime", "replay_provider", "ready_refresh", "replay_budget", "replay_retry", "safe_texture", "replay_catalog"],
                        [BASELINE / ("usr/lib/libQt5" + module + ".so.5.5.1") for module in ["Quick", "Qml", "Gui", "Network"]] +
                        [ROOT / "x1d/candidates/replay-next/artifacts/load-preparation/inputs/usr/lib/libGLESv2.so.2.0.0"]))
    entry_symbols = {
        "libx1d-jpeg-adapter.so": [
            "_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile",
            "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString"],
        "libx1d-replay-provider.so": [
            "_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase",
            "_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform"]}
    for filename, modules, extra in targets:
        output = OUT / filename
        export_map = BUILD / (filename + ".map")
        export_map.write_text("{ global:\n" + "\n".join("  " + name + ";" for name in entry_symbols[filename]) +
                              "\nlocal: *; };\n", encoding="utf-8")
        command = [str(COMPILER), "cc", "-target", "arm-linux-gnueabihf.2.22", "-mcpu=cortex_a9", "-shared", "-nostdlib",
                   "-Wl,--no-undefined", "-Wl,-T," + str(layout), "-Wl,-soname," + filename,
                   "-Wl,--version-script," + str(export_map)] + [objects[n] for n in modules] + [str(p) for p in extra + common_libs] + ["-o", str(output)]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        elf = ArmElf(output.read_bytes())
        rel, plt = elf.elf.get_section_by_name(".rel.dyn"), elf.elf.get_section_by_name(".rel.plt")
        assert rel["sh_addr"] + rel["sh_size"] == plt["sh_addr"], "固定旧链接器要求重定位表连续"
        needed = [entry.needed for entry in elf.elf.get_section_by_name(".dynamic").iter_tags() if entry.entry.d_tag == "DT_NEEDED"]
        dyn = elf.elf.get_section_by_name(".dynsym")
        unresolved = sorted({s.name for s in dyn.iter_symbols() if s.name and s["st_shndx"] == "SHN_UNDEF"})
        exports = sorted({s.name for s in dyn.iter_symbols() if s["st_shndx"] != "SHN_UNDEF" and s.name})
        assert exports == sorted(entry_symbols[filename]), "动态导出超出接入入口"
        outputs[filename] = {"sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "needed": needed,
                             "dynamicImports": unresolved, "dynamicExports": exports}
    sources += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / SOURCE).glob("*.h"))]
    sources += [Path(__file__).relative_to(ROOT).as_posix()]
    report = {"status": "compiled-native-replay-reader-target-unverified", "cameraAccess": False,
              "firmware": "X1D-50c 1.25.0",
              "predecessor": "x1d/candidates/replay-next/releases/session-compat-r2/package.json",
              "changes": ["同一主 JPEG，浏览使用 TurboJPEG DCT 缩放，Full 保留原尺寸",
                          "不再额外生成或嵌入预览 JPEG，不读取 3FR 头或主体进行配对",
                          "Full CPU 与 GPU 共享同一额度，检查上传错误，保留下层预览",
                          "按源取消过期请求，额度归还后有界重试，禁用旧路径 pixmap 缓存"],
              "recordFormat": "none; read-only JPEG selection; factory production unchanged",
              "limitations": ["同名旧 RAW 的捕获身份无法仅靠 JPEG 证明", "未知 JPEG 读取失败不会转读 RAW；RAW-only 缺失判据尚未在目标验证",
                              "新版本尚无实机功能、内存或速度测量"],
              "installed": False, "compiler": "Zig 0.13.0 / Clang", "qtHeaders": "5.5.1 public source",
              "inputHashes": hashes, "outputs": outputs,
              "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}}
    (OUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("原生适配候选已链接到固定 ARM/Qt 库；尚未执行 Qt/DBus 集成或安装。")


if __name__ == "__main__":
    run()
