"""取得与目标 Qt 同版本的公开头文件；不把它称为相机专有源码/SDK。"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".research-cache" / "x1d-1.25.0" / "qt-public"
PACKAGES = {
    "qtbase": (46_389_212, "dfa4e8a4d7e4c6b69285e7e8833eeecd819987e1bdbe5baa6b6facd4420de916"),
    "qtdeclarative": (18_627_840, "5fd14eefb83fff36fb17681693a70868f6aaf6138603d799c16466a094b26791"),
}


def run(module: str) -> None:
    size, digest = PACKAGES[module]
    name = module + "-opensource-src-5.5.1"
    url = "https://download.qt.io/archive/qt/5.5/5.5.1/submodules/" + name + ".tar.xz"
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / (name + ".tar.xz")
    if archive.exists():
        data = archive.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=45) as response:
            if not response.geturl().startswith("https://"):
                raise ValueError("公开源码下载重定向为非 HTTPS")
            data = response.read(size + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Qt 固定来源大小或 SHA-256 不匹配")
    if not archive.exists():
        archive.write_bytes(data)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as package:
        for member in package:
            if not member.isfile():
                continue
            target = (CACHE / member.name).resolve()
            target.relative_to((CACHE / name).resolve())
            relative = target.relative_to(CACHE / name).as_posix()
            selected = relative.startswith(("include/", "mkspecs/", "src/")) and relative.endswith((".h", ".hpp", ".pri", ".conf", ".in"))
            selected |= relative.startswith("include/") or "/" not in relative and relative.startswith(("LICENSE", "LGPL", "README"))
            if not selected:
                continue
            if member.size > 4_000_000:
                raise ValueError("头文件条目超过边界")
            content = package.extractfile(member).read()
            if target.exists():
                if target.read_bytes() != content:
                    raise ValueError("已存在的 Qt 输入不一致")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            count += 1
    report = {"module": module, "version": "5.5.1", "url": url, "bytes": size,
              "sha256": digest, "selectedFiles": count, "cameraProprietarySources": False}
    (CACHE / (module + "-source.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(module + " 5.5.1 公开头文件已校验：" + str(count) + " 个输入；未构建或启动 Qt 服务。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("module", choices=PACKAGES)
    run(parser.parse_args().module)
