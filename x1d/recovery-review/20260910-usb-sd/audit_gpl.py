"""枚举固定官方 GPL 归档，只保存清单与摘要，不展开源文件到工作区。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
assert Path.cwd().resolve() == HERE.parents[2]
URL = "https://cdn.hasselblad.com/firmware/X1D-50c-Firmware/1.24.0/X1D_v1_24_0.tar.xz"


class HashedReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes = 0

    def read(self, size):
        block = self.stream.read(size)
        self.bytes += len(block)
        if self.bytes > 415113824:
            raise ValueError("官方归档长度变化")
        self.digest.update(block)
        return block


with urllib.request.urlopen(URL, timeout=45) as response:
    assert response.status == 200
    reader = HashedReader(response)
    members, components = [], set()
    with tarfile.open(fileobj=reader, mode="r|xz") as archive:
        for member in archive:
            path = member.name.removeprefix("./")
            parts = path.split("/")
            if len(parts) >= 2 and parts[0] == "source-release" and parts[1]:
                components.add(parts[1])
            members.append({"path": path, "bytes": member.size, "type": member.type.decode("ascii")})
    while reader.read(1024 * 1024):
        pass
    assert reader.bytes == 415113824
result = {
    "url": URL, "firmwareSourceRelease": "X1D 1.24.0", "bytes": reader.bytes,
    "sha256": reader.digest.hexdigest(), "memberCount": len(members),
    "componentCount": len(components), "components": sorted(components),
    "matchingBoardSourcePaths": [m["path"] for m in members
        if any(s in m["path"].lower() for s in ("wedge", "umbrella", "u-boot", "uboot", "/linux-imx/", "/linux-hbl/"))],
    "members": members,
    "scope": "官方公开归档目录；没有执行其中源码、没有读取相机、没有把归档落盘。"
}
(HERE / "gpl-inventory.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k != "members"}, ensure_ascii=False, indent=2))
