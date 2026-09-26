"""核对原生接入点、ARM ABI 和动态符号依赖；这是静态审计，不是 Qt 运行联调。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, BASELINE


def run():
    path = ROOT / "x1d/candidates/replay-stable/artifacts/adapter/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for relative, expected in manifest["inputHashes"].items():
        source = (ROOT / relative).resolve()
        source.relative_to(ROOT.resolve())
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, relative
    for relative, expected in manifest["sources"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    original = {
        "jpeg": ArmElf.load("usr/bin/jpeg-daemon"),
        "gui": ArmElf.load("usr/bin/victory-gui"),
        "apps": ArmElf.load("usr/lib/libappscommon.so.1.0.0"),
        "storage": ArmElf.load("usr/bin/storage-daemon"),
        "quick": ArmElf.load("usr/lib/libQt5Quick.so.5.5.1"),
    }
    symbols = {
        "image": "_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile",
        "write": "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString",
        "provider": "_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase",
        "pixmap": "_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform",
    }
    checks = []
    for component, address, name in [
        ("jpeg", 0x178c4, symbols["image"]), ("jpeg", 0x1e2dc, symbols["write"]),
        ("gui", 0x26e7c, symbols["provider"]),
        ("apps", 0x4ad97220, "_ZN9DBusProxy16callWithFinishedERK12QDBusMessageP7QObjecti"),
        ("storage", 0x35608, "_ZN3Bus3busEv"),
    ]:
        calls = list(original[component].direct_calls(address, 4))
        # CloseFile 的回包调用点单独从该成功块查找，避免把取 Bus 与 send 混淆。
        if component == "storage":
            block = list(original[component].direct_calls(0x355c0, 0x78))
            assert any("createReply" in n for _, _, n in block)
            assert any(n == "_ZN3Bus4sendERK12QDBusMessage" for _, _, n in block)
            checks.append({"component": component, "block": "0x355c0..0x35638", "replyThenBusSend": True})
            continue
        assert len(calls) == 1 and calls[0][2] == name, (component, hex(address), calls)
        checks.append({"component": component, "call": hex(address), "symbol": name})
    j = original["jpeg"]
    for at, expected in [(0x197b0, 0xe596e014), (0x19814, 0xe584e01c), (0x1e2c8, 0xe595001c)]:
        assert j.word(at) == expected, hex(at)
    checks.append({"component": "jpeg", "captureAssociation": "Encoder+0x14 -> ConvertCall+0x1c -> writeFile this"})
    quick = original["quick"]
    load = next(s for s in quick.symbols if s.name == "_ZN15QQuickImageBase4loadEv" and s["st_value"])
    calls = [c for c in quick.direct_calls(load["st_value"], load["st_size"]) if c[2] == symbols["pixmap"]]
    assert len(calls) == 1
    assert calls[0][1] not in quick.direct, "预期为可接入的 PLT 路径"
    checks.append({"component": "quick", "call": hex(calls[0][0]), "symbol": symbols["pixmap"], "usesPlt": True})
    libraries = [ArmElf(p.read_bytes()) for p in list((BASELINE / "usr/lib").glob("*.so.*")) + list((BASELINE / "lib").glob("*.so*"))
                 if p.is_file() and p.read_bytes()[:4] == b"\x7fELF"]
    libraries.append(ArmElf((ROOT / "x1d/candidates/replay-next/artifacts/load-preparation/inputs/usr/lib/libGLESv2.so.2.0.0").read_bytes()))
    available = {s.name for e in libraries for s in e.elf.get_section_by_name(".dynsym").iter_symbols()
                 if s.name and s["st_shndx"] != "SHN_UNDEF"}
    modules = []
    for filename, record in manifest["outputs"].items():
        data = (path.parent / filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == record["sha256"]
        e = ArmElf(data)
        assert e.elf["e_type"] == "ET_DYN" and e.elf["e_flags"] & 0x400
        dynamic = e.elf.get_section_by_name(".dynamic")
        assert not any(t.entry.d_tag == "DT_TEXTREL" for t in dynamic.iter_tags())
        rel, plt = e.elf.get_section_by_name(".rel.dyn"), e.elf.get_section_by_name(".rel.plt")
        assert rel["sh_addr"] + rel["sh_size"] == plt["sh_addr"], "旧链接器重定位表不连续"
        missing = set(record["dynamicImports"]) - available
        assert not missing, sorted(missing)
        required = [symbols["image"], symbols["write"]] if "jpeg-adapter" in filename else [symbols["provider"], symbols["pixmap"]]
        assert sorted(record["dynamicExports"]) == sorted(required)
        for section in e.sections:
            if section["sh_type"] == "SHT_REL":
                assert all(r["r_info_type"] != 20 for r in section.iter_relocations()), "R_ARM_COPY 不应出现在模块内"
        modules.append({"file": filename, "sha256": record["sha256"], "hardFloatArmSharedObject": True, "textRelocations": False, "relocationsContiguous": True,
                        "importsResolvedInFixedInputLibraries": len(record["dynamicImports"]), "entrySymbols": required,
                        "otherExports": []})
    evidence = {"kind": "static-abi-and-callsite-audit", "version": "X1D-50c 1.25.0 / Qt 5.5.1",
                "buildManifestSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "auditSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "cameraAccess": False, "qtRuntimeIntegration": False, "checks": checks, "modules": modules}
    (ROOT / "x1d/candidates/replay-stable/artifacts/adapter/abi-audit.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("原生接入点、ARM hard-float 与固定库导入审计通过；未运行 Qt/DBus/GPU 联调。")


if __name__ == "__main__": run()
