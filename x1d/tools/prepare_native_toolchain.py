"""项目内的固定 C/ARM 交叉编译器；不安装到系统，不运行相机组件。"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".research-cache" / "x1d-1.25.0" / "toolchain"
URL = "https://ziglang.org/download/0.13.0/zig-windows-x86_64-0.13.0.zip"
SHA256 = "d859994725ef9402381e557c60bb57497215682e355204d754ee3df75ee3c158"
SIZE = 79_163_968
PACKAGE = "zig-windows-x86_64-0.13.0"


def run() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / (PACKAGE + ".zip")
    if archive.exists():
        data = archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=45) as response:
            if response.geturl() != URL:
                raise ValueError("编译器下载发生重定向")
            data = response.read(SIZE + 1)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("编译器固定校验失败")
    if not archive.exists():
        archive.write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        for entry in package.infolist():
            if entry.is_dir():
                continue
            target = (CACHE / entry.filename).resolve()
            target.relative_to((CACHE / PACKAGE).resolve())
            if entry.file_size > 200_000_000:
                raise ValueError("工具链条目过大")
            content = package.read(entry)
            if target.exists():
                if target.read_bytes() != content:
                    raise ValueError("已有工具链文件不一致")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    print("固定 Zig 0.13.0 已在 X1D 独立缓存中校验；未更改系统 PATH。")


if __name__ == "__main__":
    run()
