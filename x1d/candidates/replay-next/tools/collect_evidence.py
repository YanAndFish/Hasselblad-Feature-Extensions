"""从既有固定固件、Qt 源码包和候选抽取回放证据，不执行原程序。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts/evidence"
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, CACHE, qml_files


def digest(data):
    return hashlib.sha256(data).hexdigest()


def excerpts(text, needles, before=4, after=8):
    lines = text.splitlines()
    wanted = set()
    for index, line in enumerate(lines):
        if any(needle in line for needle in needles):
            wanted.update(range(max(0, index - before), min(len(lines), index + after + 1)))
    return "\n".join(f"{index + 1}: {lines[index]}" for index in sorted(wanted))


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    firmware = CACHE / "X1D_v1_25_0.cim"
    firmware_hash = digest(firmware.read_bytes())
    assert firmware_hash == "1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2"
    gui = ArmElf.load("usr/bin/victory-gui")
    qml = qml_files(gui)
    snippets = []
    qml_hashes = {}
    for name, needles in {
        "/settings/Photo.qml": ["cache:", "asynchronous:", "img.source ="],
        "/components/MediaBrowseView.qml": ["cacheBuffer:", "list_delegate_loader", "onPrepareScaling:", "flick_fullimg.source =", "id: flick_fullimg"],
        "/browseview/MediaListViewImageDelegate.qml": ["source: list_delegate.loadImage", "onStatusChanged:"],
    }.items():
        text = qml[name]
        qml_hashes[name] = digest(text.encode())
        snippets.append(f"[{name}] sha256={qml_hashes[name]}\n" + excerpts(text, needles))
    (OUT / "original-qml-excerpts.txt").write_text("\n\n".join(snippets) + "\n", encoding="utf-8")

    qt_specs = {
        "qtdeclarative": {
            "src/quick/util/qquickpixmapcache.cpp": ["void QQuickPixmapReader::processJobs()", "processJob(runningJob", "provider->requestTexture(", "if (!cancelled.contains(runningJob))", "If Cache is disabled"],
            "src/quick/scenegraph/util/qsgtexture.cpp": ["void QSGPlainTexture::setImage", "Downscale the texture", "tmp = tmp.scaled", "funcs->glTexImage2D", "if (!m_retain_image)", "qsg_swizzleBGRAToRGBA(&tmp)", "QImage tmp =", "GL_EXT_texture_format_BGRA8888"],
        },
        "qtbase": {
            "src/corelib/thread/qsemaphore.cpp": ["bool QSemaphore::tryAcquire", "timeout", "QMutexLocker"],
            "src/gui/image/qimage.cpp": ["QImageData *QImageData::create(uchar", "d->cleanupFunction = cleanupFunction", "void QImage::detach()", "d->ref.load() != 1 || d->ro_data"],
        },
    }
    qt_hashes = {}
    qt_snippets = []
    for package, specs in qt_specs.items():
        tar_path = CACHE / "qt-public" / f"{package}-opensource-src-5.5.1.tar.xz"
        qt_hashes[tar_path.relative_to(ROOT).as_posix()] = digest(tar_path.read_bytes())
        with tarfile.open(tar_path) as archive:
            for suffix, needles in specs.items():
                member = archive.getmember(f"{package}-opensource-src-5.5.1/{suffix}")
                data = archive.extractfile(member).read()
                qt_hashes[member.name] = digest(data)
                qt_snippets.append(f"[{member.name}] sha256={digest(data)}\n" + excerpts(data.decode(), needles))
    (OUT / "qt-5.5.1-excerpts.txt").write_text("\n\n".join(qt_snippets) + "\n", encoding="utf-8")
    # 原厂纹理同样查询 GL_MAX_TEXTURE_SIZE，但不是 QSGPlainTexture 的 QImage 路径。
    assert gui.word(0x47aa4) == 0xe3000d33  # movw r0, #GL_MAX_TEXTURE_SIZE
    gpu_calls = list(gui.direct_calls(0x47a70, 0xc28))
    assert any(name == "glGetIntegerv" for _, _, name in gpu_calls)
    assert any(name == "glTexImage2D" for _, _, name in gpu_calls)
    (OUT / "original-texture-bind.txt").write_text(gui.disassembly(0x47a70, 0xc28) + "\n", encoding="utf-8")

    baselines = {}
    for version in ("v1", "v2", "v3"):
        path = ROOT / f"x1d/artifacts/replay-adapter-{version}/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        sources = {relative: digest((ROOT / relative).read_bytes()) == expected
                   for relative, expected in manifest["sources"].items()}
        outputs = {filename: digest((path.parent / filename).read_bytes()) == record["sha256"]
                   for filename, record in manifest["outputs"].items()}
        baselines[version] = {"manifestSha256": digest(path.read_bytes()), "sources": sources, "outputs": outputs,
                              "allMatch": all(sources.values()) and all(outputs.values())}
        assert baselines[version]["allMatch"], f"{version} baseline changed"
    (OUT / "frozen-baseline-verification.json").write_text(json.dumps(baselines, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    new_manifest = json.loads((HERE / "artifacts/adapter/manifest.json").read_text(encoding="utf-8"))
    old_manifest = json.loads((ROOT / "x1d/artifacts/replay-adapter-v3/manifest.json").read_text(encoding="utf-8"))
    name = "libx1d-replay-provider.so"
    assert "_ZN10QSemaphore10tryAcquireEii" in old_manifest["outputs"][name]["dynamicImports"]
    assert "_ZN10QSemaphore10tryAcquireEi" in new_manifest["outputs"][name]["dynamicImports"]
    assert "_ZN10QSemaphore10tryAcquireEii" not in new_manifest["outputs"][name]["dynamicImports"]
    original = (ROOT / "x1d/candidates/replay-v3/native/replay_provider.cpp").read_text(encoding="utf-8")
    candidate = (HERE / "native/replay_provider.cpp").read_text(encoding="utf-8")
    assert "fullBuffers.tryAcquire(1, 1500)" in original
    assert "fullBuffers.tryAcquire(1)" in candidate
    # 这是对已知候选版本的静态控制流约束，不冒充运行 provider。
    barrier = candidate.index('if (color >= 0 && ok && tail == QByteArray("\\xff\\xd9", 2))')
    assert candidate.index("X1D::sameSource(source, record)") < barrier
    assert candidate.index("headerMatches(header, record, &info)") < barrier
    assert barrier < candidate.index("previews.get(key, &cached)")
    assert candidate.index("if (!full)", barrier) < candidate.index("previews.get(key, &cached)")
    report = {
        "kind": "fixed-input-static-evidence-not-camera-profiling",
        "firmware": "X1D-50c 1.25.0", "firmwareSha256": firmware_hash, "firmwareBytes": firmware.stat().st_size,
        "guiSha256": digest(gui.data), "qmlSources": qml_hashes, "qtSources": qt_hashes,
        "baselineVersionsPreserved": baselines.keys(),
        "v3FullAdmissionTimeoutMilliseconds": 1500,
        "nextFullAdmission": "QSemaphore::tryAcquire(int), no timed wait overload",
        "providerCacheLookupAfterSameSourceHeaderAndTail": True,
        "cachedImages": "preview/thumb only; never Full; prefix hash is reverified each request",
        "cameraRequests": 0, "targetProviderRun": False, "targetGpuRun": False,
        "defaultQtUploadRisks": ["超过 GL_MAX_TEXTURE_SIZE 时缩图", "无受支持 BGRA 扩展时可因 QImage detach 复制 Full 像素"],
        "originalTextureBind": "victory-gui 1.25.0 0x47a70; GL_MAX_TEXTURE_SIZE 查询和专用上传分支，详见反汇编证据",
        "sourceHashes": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in
                         [Path(__file__), HERE / "native/replay_provider.cpp", HERE / "native/preview_cache.h"]},
    }
    report["baselineVersionsPreserved"] = list(report["baselineVersionsPreserved"])
    (OUT / "source-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixedFirmware": "X1D-50c 1.25.0", "oldVersionsUnchanged": list(baselines), "timedSemaphoreImportRemoved": True, "cameraRequests": 0}))


if __name__ == "__main__":
    run()
