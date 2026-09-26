"""离线装载准备审计：组件、每进程依赖闭包与符号版本、固定 Qt 纹理分支。

仅解析当前工作区文件。无网络、设备、进程启动、服务修改或安装入口。
成功退出只表示离线检查通过，loadReady 恒为 false，实机证据另行取得。
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts/load-preparation"
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, BASELINE, CACHE, qml_files
from prepare_load_inputs import metadata
from verify_candidate import run as verify_candidate


def sha(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(path.read_text(encoding="utf-8"))
def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def symbols(data):
    elf = ArmElf(data).elf
    versions, version_needs = {}, []
    sec = elf.get_section_by_name(".gnu.version_r")
    if sec:
        for item, auxiliaries in sec.iter_versions():
            for aux in auxiliaries:
                versions[aux["vna_other"] & 0x7fff] = aux.name
                version_needs.append({"library": item.name, "version": aux.name})
    sec = elf.get_section_by_name(".gnu.version_d")
    definitions = set()
    if sec:
        for item, auxiliaries in sec.iter_versions():
            names = [aux.name for aux in auxiliaries]
            versions[item["vd_ndx"]] = names[0]
            definitions.add(names[0])
    versym = elf.get_section_by_name(".gnu.version")
    imports, exports = [], []
    for index, sym in enumerate(elf.get_section_by_name(".dynsym").iter_symbols()):
        if not sym.name: continue
        vi = versym.get_symbol(index)["ndx"] if versym else "VER_NDX_GLOBAL"
        hidden = isinstance(vi, int) and bool(vi & 0x8000)
        version = versions.get(vi & 0x7fff) if isinstance(vi, int) else None
        entry = {"name": sym.name, "version": version, "default": not hidden,
                 "weak": sym["st_info"]["bind"] == "STB_WEAK"}
        if sym["st_shndx"] == "SHN_UNDEF": imports.append(entry)
        elif sym["st_info"]["bind"] in ("STB_GLOBAL", "STB_WEAK", "STB_GNU_UNIQUE", "STB_LOOS") and sym["st_other"]["visibility"] in ("STV_DEFAULT", "STV_PROTECTED"):
            exports.append(entry)
    return {"imports": imports, "exports": exports, "versionNeeds": version_needs,
            "versionDefinitions": definitions, **metadata(data)}


def run():
    verify_candidate()
    inputs = read_json(OUT / "inputs.json")
    assert inputs["sourceSha256"] == sha((HERE / "tools/prepare_load_inputs.py").read_bytes())
    baseline = read_json(ROOT / "x1d/research/baseline-manifest.json")
    assert inputs["firmwareSha256"] == baseline["sha256"]
    assert inputs["rootfsSha256"] == next(e["sha256"] for e in baseline["entries"] if e["name"] == "rootfs")
    data, parsed = {}, {}
    for path, item in inputs["files"].items():
        local = (OUT / "inputs" / path).resolve()
        local.relative_to((OUT / "inputs").resolve())
        data[path] = local.read_bytes()
        assert sha(data[path]) == item["sha256"], path
        assert metadata(data[path]) == {k: item[k] for k in ("needed", "interpreter", "searchPaths")}
    bound = read_json(HERE / "artifacts/adapter/manifest.json")
    components = []
    for folder, name in (("full-jpeg-v1", "configstore"), ("jpeg-failure-v1", "jpeg-daemon")):
        path = ROOT / "x1d/artifacts" / folder
        patch = read_json(path / "manifest.json")
        original, candidate = data["usr/bin/" + name], (path / (name + ".elf")).read_bytes()
        assert sha(original) == patch["sourceSha256"]
        assert sha(candidate) == patch["candidateSha256"]
        reconstructed = bytearray(original)
        for edit in patch.get("patches", [patch]):
            offset = edit["offset"]
            before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
            assert len(before) == len(after) and original[offset:offset + len(before)] == before
            reconstructed[offset:offset + len(after)] = after
        assert bytes(reconstructed) == candidate, name
        data["candidate/" + name] = candidate
        components.append({"role": name, "sourcePath": (path / (name + ".elf")).relative_to(ROOT).as_posix(),
                           "sourceSha256": sha(original), "candidateSha256": sha(candidate),
                           "patchBytesExactlyMatch": True,
                           "scope": "构造配置逻辑" if name == "configstore" else "编码失败传播"})
    for name, info in bound["outputs"].items():
        content = (HERE / "artifacts/adapter" / name).read_bytes()
        assert sha(content) == info["sha256"]
        data["candidate/" + name] = content
        components.append({"role": name, "sourcePath": (HERE / "artifacts/adapter" / name).relative_to(ROOT).as_posix(),
                           "candidateSha256": sha(content)})
    # 本地补提取的原文件必须与构建绑定完全相同。
    for path, expected in bound["inputHashes"].items():
        prefix = ".research-cache/x1d-1.25.0/baseline/"
        if path.startswith(prefix): assert sha(data[path[len(prefix):]]) == expected
    assert bound["inputHashes"]["x1d/artifacts/jpeg-failure-v1/jpeg-daemon.elf"] == sha(data["candidate/jpeg-daemon"])

    def get(path):
        if path not in parsed: parsed[path] = symbols(data[path])
        return parsed[path]

    roles = {
        "jpeg-daemon": ["candidate/jpeg-daemon", "candidate/libx1d-jpeg-adapter.so"],
        "victory-gui": ["usr/bin/victory-gui", "candidate/libx1d-replay-provider.so"],
        "configstore": ["candidate/configstore"],
        "storage-daemon": ["usr/bin/storage-daemon"],
    }
    results = {}
    for role, roots in roles.items():
        queue, closure = list(roots), []
        if role in ("jpeg-daemon", "victory-gui"):
            queue.append(inputs["libraryPaths"]["libturbojpeg.so.0"])
        while queue:
            path = queue.pop(0)
            if path in closure: continue
            closure.append(path)
            item = get(path)
            assert not item["searchPaths"], path
            for needed in item["needed"] + item["interpreter"]:
                queue.append(inputs["libraryPaths"][needed])
        available = defaultdict(list)
        for path in closure:
            for export in get(path)["exports"]: available[export["name"]].append((path, export))
        unresolved, weak, resolved, versions = [], [], [], []
        for path in closure:
            item = get(path)
            for requirement in item["versionNeeds"]:
                lib = inputs["libraryPaths"][requirement["library"]]
                assert lib in closure and requirement["version"] in get(lib)["versionDefinitions"], (path, requirement)
                versions.append({"consumer": path, **requirement})
            for imported in item["imports"]:
                matches = [provider for provider, export in available[imported["name"]]
                           if (export["version"] == imported["version"] if imported["version"] else export["default"])]
                detail = {"consumer": path, "symbol": imported["name"], "version": imported["version"]}
                if matches: resolved.append({**detail, "providers": matches})
                elif imported["weak"]: weak.append(detail)
                else: unresolved.append(detail)
        results[role] = {"roots": roots, "closure": closure, "unresolvedStrong": unresolved,
                         "unresolvedWeak": weak, "resolved": resolved, "versionRequirements": versions}
    explicit = []
    lookups = {
        "usr/lib/libturbojpeg.so.0.1.0": ["tjInitDecompress", "tjInitCompress", "tjDestroy", "tjAlloc", "tjFree",
                                             "tjDecompressHeader3", "tjGetScalingFactors", "tjDecompress2", "tjBufSize", "tjCompress2"],
        "usr/lib/libappscommon.so.1.0.0": ["_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile",
                                            "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString"],
        "usr/lib/libQt5Qml.so.5.5.1": ["_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase"],
        "usr/lib/libQt5Quick.so.5.5.1": ["_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform",
                                          "_ZN15QQuickImageBase4loadEv"],
    }
    for path, names in lookups.items():
        exports = {s["name"] for s in get(path)["exports"] if s["default"]}
        for name in names:
            assert name in exports, (path, name)
            explicit.append({"library": path, "symbol": name, "exportExists": True})
    address_assumptions = []
    for path in ("usr/bin/victory-gui", "usr/bin/jpeg-daemon", "usr/lib/libQt5Quick.so.5.5.1"):
        elf = ArmElf(data[path]).elf
        address_assumptions.append({"file": path, "elfType": elf["e_type"],
                                    "linkTimeLoadSegments": [hex(s["p_vaddr"]) for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"],
                                    "actualLoadBias": None})
    dependency_report = {"kind": "per-process-static-symbol-and-version-closure",
                         "cameraAccess": False, "runtimeLinkerExecuted": False,
                         "components": components, "processes": results,
                         "explicitLookupExports": explicit, "addressAssumptions": address_assumptions,
                         "fileHashes": {p: sha(data[p]) for p in sorted(parsed)},
                         "limitations": ["没有执行 ELF 初始化器、重定位或原 Linux 动态链接器",
                                         "未覆盖平台插件、QML 插件及库内部其他运行时 dlopen",
                                         "多个匹配定义不是实际绑定顺序证明；进程注入与 RTLD_NEXT 需后续实测",
                                         "文件摘要不能证明当前进程的映射文件及运行状态"]}
    write_json("dependencies.json", dependency_report)
    assert not any(r["unresolvedStrong"] for r in results.values()), "存在未解析强符号，见 dependencies.json"

    services = {}
    baseline_hashes = {item["path"]: item["sha256"] for item in baseline["files"]}
    for role in roles:
        path = "lib/systemd/system/" + role + ".service"
        content = (BASELINE / path).read_bytes()
        assert sha(content) == baseline_hashes[path]
        lines = content.decode().splitlines()
        services[role] = {"sha256": sha(content), "lines": [{"line": i, "text": line}
                          for i, line in enumerate(lines, 1) if line.startswith(("Exec", "Restart", "After", "Wants", "Environment"))]}
    write_json("services.json", {"firmware": "X1D-50c 1.25.0", "services": services,
                                "executed": False, "deviceState": None})

    qt = CACHE / "qt-public/qtdeclarative-opensource-src-5.5.1.tar.xz"
    source_evidence = read_json(HERE / "artifacts/evidence/source-evidence.json")
    assert sha(qt.read_bytes()) == source_evidence["qtSources"][qt.relative_to(ROOT).as_posix()]
    source = "qtdeclarative-opensource-src-5.5.1/src/quick/scenegraph/util/qsgtexture.cpp"
    with tarfile.open(qt) as archive: content = archive.extractfile(source).read()
    assert sha(content) == source_evidence["qtSources"][source]
    lines = content.decode().splitlines()
    branches = {
        "format": "QImage tmp = (m_image.format() == QImage::Format_RGB32",
        "maximumSize": "if (tmp.width() > max || tmp.height() > max)",
        "npotMipmap": "&& !funcs->hasOpenGLFeature(QOpenGLFunctions::NPOTTextures)",
        "stride": "if (tmp.width() * 4 != tmp.bytesPerLine())",
        "bgra": 'if (context->hasExtension(QByteArrayLiteral("GL_EXT_bgra")))',
        "swizzle": "qsg_swizzleBGRAToRGBA(&tmp);",
        "upload": "funcs->glTexImage2D(GL_TEXTURE_2D, 0, internalFormat",
    }
    found = {label: next(i for i, line in enumerate(lines, 1) if text in line) for label, text in branches.items()}
    (OUT / "qt-texture-path.txt").write_text("\n".join(f"{i + 1}: {lines[i]}" for i in range(618 - 1, 786)) + "\n", encoding="utf-8")
    gui_qml = qml_files(ArmElf(data["usr/bin/victory-gui"]))
    qml_mipmap = [{"resource": path, "line": i, "text": line.strip()} for path, text in gui_qml.items()
                  for i, line in enumerate(text.splitlines(), 1) if "mipmap" in line.lower()]
    gpu = {"kind": "fixed-qt-source-conditional-analysis", "source": source, "sha256": sha(content),
           "branches": found, "cameraAccess": False, "gpuExecuted": False,
           "actualMaxTextureSize": None, "actualBgraExtensions": None,
           "qmlMipmapMentions": qml_mipmap,
           "candidatePixelFormat": "QImage::Format_RGB32", "candidateStride": "width * 4",
           "singleCpuFullPixelBytes": 8176 * 6128 * 4,
           "extraFullCopyBytesIfSwizzledWithoutResize": 8176 * 6128 * 4,
           "conditionalExamples": [
               {"assumedLimit": 8192, "mipmap": False, "qtBgraBranch": True, "sourceSize": [8176, 6128],
                "uploadSize": [8176, 6128], "explicitQtPixelCopy": False},
               {"assumedLimit": 8192, "mipmap": False, "qtBgraBranch": False, "sourceSize": [8176, 6128],
                "uploadSize": [8176, 6128], "explicitQtPixelCopy": True, "reason": "共享/只读 QImage 的通道交换触发 detach"},
               {"assumedLimit": 4096, "mipmap": False, "sourceSize": [8176, 6128],
                "uploadSize": [4096, 4096], "explicitQtPixelCopy": True, "reason": "每个维度分别取 min，不保持 Full 分辨率"},
               {"assumedLimit": 8192, "mipmap": True, "npotSupported": False, "sourceSize": [8176, 6128],
                "uploadSize": [8192, 8192], "resizedPixelBytes": 8192 * 8192 * 4,
                "explicitQtPixelCopy": True, "reason": "两个维度分别扩到下一 2 的幂"}],
           "limits": ["示例是条件推导，不是相机能力或 GPU 模拟测试",
                      "方向 5..8 时尺寸为 6128×8176，最大边条件相同",
                      "无显式 Qt 像素复制也不能排除驱动 staging、GPU 分配与原 provider 分配",
                      "8192×8192 重采样缓冲不含后续 mipmap 存储；总峰值仍未知",
                      "纹理创建返回后 bind 才可能上传；CPU provider 回退不覆盖 GL 上传失败"]}
    write_json("gpu-path.json", gpu)
    report = {"status": "offline-load-preparation-audited-hardware-gates-open", "loadReady": False,
              "cameraAccess": False, "installed": False, "firmwareSource": "X1D-50c 1.25.0",
              "checks": {"inputFiles": len(inputs["files"]), "componentArtifacts": len(components), "explicitLookupExports": len(explicit),
                         "processClosures": len(results), "resolvedSymbolReferences": sum(len(r["resolved"]) for r in results.values()),
                         "unresolvedStrongSymbols": 0, "fixedServiceDefinitions": len(services), "qtTextureBranches": len(found)},
              "remainingBeforeLoad": [
                  {"item": "currentFirmwareAndMappedComponents", "status": "需要后续授权设备窗口确认"},
                  {"item": "authorizedLoadAndRecoveryRoute", "status": "流程约束已整理；实际入口及恢复未验证"},
                  {"item": "standbyUpdateCoordination", "status": "由主任务确认稳定窗口；本任务未处理系统切换"},
                  {"item": "actualGuiTextureAndMemoryCapabilities", "status": "静态分支已定位；实际能力与峰值未知"}],
              "afterLoadIntegration": ["真实 DBus/CloseFile 与记录原子发布", "取消/切图/上下文重建", "写卡及机内耗时"],
              "evidenceHashes": {name: sha((OUT / name).read_bytes()) for name in
                                 ("inputs.json", "dependencies.json", "services.json", "gpu-path.json", "qt-texture-path.txt")},
              "sourceHashes": {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in
                               (Path(__file__), HERE / "tools/prepare_load_inputs.py")},
              "candidateManifestSha256": sha((HERE / "artifacts/adapter/manifest.json").read_bytes())}
    write_json("review.json", report)
    print(json.dumps({"status": report["status"], "loadReady": False, "checks": report["checks"]}, ensure_ascii=False))


if __name__ == "__main__": run()
