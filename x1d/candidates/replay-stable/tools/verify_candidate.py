"""汇总本候选实际报告并核对源/组件摘要；不代替报告中未执行的真实组件。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative): return json.loads((HERE / relative).read_text(encoding="utf-8"))


def check_sources(values):
    for relative, expected in values.items():
        path = (ROOT / relative).resolve()
        path.relative_to(ROOT.resolve())
        assert sha(path) == expected, relative


def run():
    manifest = read("artifacts/adapter/manifest.json")
    check_sources(manifest["sources"])
    check_sources(manifest["inputHashes"])
    for name, metadata in manifest["outputs"].items():
        assert sha(HERE / "artifacts/adapter" / name) == metadata["sha256"]
    paths = {
        "pixels": "artifacts/pixels/validation.json",
        "armPixels": "artifacts/pixels/arm-validation.json",
        "cache": "artifacts/checks/validation.json",
        "provider": "artifacts/provider/validation.json",
        "providerEdges": "artifacts/provider-edges/validation.json",
        "adapter": "artifacts/adapter-tests/validation.json",
    }
    reports = {name: read(path) for name, path in paths.items()}
    for name, report in reports.items():
        assert report.get("passed") is True or report.get("status") == "passed", name
        check_sources(report.get("sources", report.get("sourceHashes", {})))
    for name in ("provider", "providerEdges", "adapter"):
        module = "libx1d-jpeg-adapter.so" if name == "adapter" else "libx1d-replay-provider.so"
        assert reports[name]["moduleHashes"]["candidate"] == manifest["outputs"][module]["sha256"]
    for name, expected in reports["armPixels"]["outputs"].items():
        assert sha(HERE / "artifacts/pixels" / name) == expected
    frozen = read("artifacts/evidence/frozen-baseline-verification.json")
    assert set(frozen) == {"v1", "v2", "v3"} and all(value["allMatch"] for value in frozen.values())
    for version, checked in frozen.items():
        path = ROOT / "x1d/artifacts" / ("replay-adapter-" + version) / "manifest.json"
        assert sha(path) == checked["manifestSha256"]
        fixed = json.loads(path.read_text(encoding="utf-8"))
        check_sources(fixed["sources"])
        for name, metadata in fixed["outputs"].items(): assert sha(path.parent / name) == metadata["sha256"]
    evidence = read("artifacts/evidence/source-evidence.json")
    check_sources(evidence["sourceHashes"])
    abi = read("artifacts/adapter/abi-audit.json")
    assert abi["kind"] == "static-abi-and-callsite-audit"
    assert abi["buildManifestSha256"] == sha(HERE / "artifacts/adapter/manifest.json")
    assert abi["auditSourceSha256"] == sha(HERE / "tools/audit_replay_adapter.py")
    for module in abi["modules"]:
        assert module["sha256"] == manifest["outputs"][module["file"]]["sha256"]
    pixels, cache = reports["pixels"], reports["cache"]
    summary = {
        "status": "offline-candidate-evidence-matches-current-sources-and-modules",
        "firmwareSource": "X1D-50c 1.25.0", "cameraAccess": False, "installed": False,
        "checks": {"hostPixelAssertions": pixels["checks"], "allRgbColors": pixels["allRgbColors"],
                   "armOrientationCases": reports["armPixels"]["orientationCases"], "armColorSamples": reports["armPixels"]["armColorSamples"],
                   "hostCacheAssertions": cache["checks"], "providerCaseGroups": reports["provider"]["caseGroups"],
                   "providerEdgeCaseGroups": reports["providerEdges"]["caseGroups"], "adapterCaseGroups": reports["adapter"]["caseGroups"]},
        "hostOnlyStageMedianMs": {"adobeV3": pixels["hostV3AdobeMedianMs"], "adobeNext": pixels["hostNextAdobeMedianMs"],
                                  "orientation6V3": pixels["hostV3Orientation6MedianMs"], "orientation6Next": pixels["hostNextOrientation6MedianMs"]},
        "performanceScope": "同机人工 Full BGRA 的独立 C 像素阶段；没有 JPEG/Storage/Qt/GPU；不是相机延迟",
        "fullPixelBytes": pixels["fullCpuPixelBytes"], "orientationScratchBytes": pixels["newOrientationScratchBytes"],
        "notValidated": ["实际 Qt/DBus/写卡关闭及记录发布", "真实取消/切图时序", "GPU 尺寸/复制/上传", "机内总峰值与速度", "装载和恢复"],
        "artifacts": {relative: sha(HERE / relative) for relative in paths.values()},
        "moduleHashes": {name: value["sha256"] for name, value in manifest["outputs"].items()},
        "sourceHashes": {Path(__file__).relative_to(ROOT).as_posix(): sha(Path(__file__))},
    }
    (HERE / "artifacts/review-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "checks": summary["checks"], "cameraAccess": False}, ensure_ascii=False))


if __name__ == "__main__": run()
