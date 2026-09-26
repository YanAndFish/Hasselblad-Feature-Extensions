"""从固定原包补齐装载审计输入；只写本候选，不执行 ELF 或接触相机。

首次 --fetch-reference 只读取既有解包器的固定 Git blob，在内存中解析常量。
不保存参考源码/密钥，不生成修改 CIM；此后普通运行完全使用本地输入。
"""
from __future__ import annotations
import argparse
import bz2
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import sys
import tarfile

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
OUT = HERE / "artifacts/load-preparation"
sys.path.insert(0, str(ROOT / "x1d/tools"))
from binary import ArmElf, CACHE
import prepare_baseline as baseline


def sha(data): return hashlib.sha256(data).hexdigest()


def metadata(data):
    elf = ArmElf(data).elf
    dynamic = elf.get_section_by_name(".dynamic")
    tags = list(dynamic.iter_tags()) if dynamic else []
    return {
        "needed": [t.needed for t in tags if t.entry.d_tag == "DT_NEEDED"],
        "interpreter": [s.get_interp_name() for s in elf.iter_segments() if s["p_type"] == "PT_INTERP"],
        "searchPaths": [getattr(t, "rpath", getattr(t, "runpath", "")) for t in tags
                        if t.entry.d_tag in ("DT_RPATH", "DT_RUNPATH")],
    }


def run(fetch_reference=False):
    manifest_path = OUT / "inputs.json"
    if manifest_path.exists():
        report = json.loads(manifest_path.read_text(encoding="utf-8"))
        for path, item in report["files"].items():
            local = (OUT / "inputs" / path).resolve()
            local.relative_to((OUT / "inputs").resolve())
            assert sha(local.read_bytes()) == item["sha256"], path
        print("既有固定装载输入摘要一致；未访问网络或相机。")
        return
    if not fetch_reference:
        raise SystemExit("缺少本地补充输入；首次运行需显式 --fetch-reference 读取固定参考 blob。")
    firmware = (CACHE / "X1D_v1_25_0.cim").read_bytes()
    assert len(firmware) == baseline.SIZE and sha(firmware) == baseline.SHA256
    constants = baseline.reference_constants(baseline.fetch(baseline.REFERENCE, 65536))
    from Crypto.Cipher import AES
    stamp = re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})", firmware[:128])
    assert stamp
    year, month, day, hour, minute, second = map(int, stamp.groups())
    initial = hashlib.md5(constants["IV_SALT"] + bytes([year // 100, year % 100, month, day, hour, minute, second]) + bytes(9)).digest()
    offset, size = baseline.PARTS["rootfs"]
    payload = bytearray()
    for pos in range(0, size, 4096):
        count = min(4096, size - pos)
        block = firmware[offset + pos:offset + pos + ((count + 15) // 16) * 16]
        payload.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(block)[:count])
    del constants, initial
    original_manifest = json.loads((ROOT / "x1d/research/baseline-manifest.json").read_text(encoding="utf-8"))
    wanted = next(e["sha256"] for e in original_manifest["entries"] if e["name"] == "rootfs")
    assert sha(payload) == wanted
    programs = {"usr/bin/" + p for p in ("jpeg-daemon", "victory-gui", "configstore", "storage-daemon")}
    data, aliases = {}, {}
    with tarfile.open(fileobj=io.BytesIO(bz2.decompress(payload)), mode="r:") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name.startswith("/") or ".." in PurePosixPath(name).parts:
                raise ValueError("原包路径越界")
            if not (name.startswith(("lib/", "usr/lib/")) or name in programs):
                continue
            if member.issym() or member.islnk():
                target = member.linkname
                absolute = target.lstrip("/") if target.startswith("/") else posixpath.join(posixpath.dirname(name), target) if member.issym() else target.removeprefix("./")
                absolute = posixpath.normpath(absolute)
                assert not absolute.startswith("../") and not absolute.startswith("/")
                aliases[name] = absolute
            elif member.isfile() and (".so" in PurePosixPath(name).name or name in programs):
                assert member.size <= 32 * 1024 * 1024
                content = archive.extractfile(member).read()
                if content.startswith(b"\x7fELF"):
                    data[name] = content

    used_aliases = {}
    def resolve(path):
        seen = set()
        while path in aliases:
            assert path not in seen, "符号链接循环"
            seen.add(path)
            used_aliases[path] = aliases[path]
            path = aliases[path]
        if path not in data: raise ValueError("依赖文件缺失：" + path)
        return path

    def library(name):
        if "/" in name: return resolve(name.lstrip("/"))
        found = []
        for folder in ("lib", "usr/lib"):
            path = folder + "/" + name
            if path in data or path in aliases: found.append(resolve(path))
        if not found: raise ValueError("依赖名缺失：" + name)
        assert len({sha(data[p]) for p in found}) == 1, "不同内容的重复依赖：" + name
        return found[0]

    library_paths, roots = {}, sorted(programs)
    # codec 是候选显式 dlopen 的唯一固定额外库；平台插件运行选择另作边界记录。
    library_paths["libturbojpeg.so.0"] = library("libturbojpeg.so.0")
    queue = roots + [library_paths["libturbojpeg.so.0"]]
    for name in ("libx1d-jpeg-adapter.so", "libx1d-replay-provider.so"):
        for needed in metadata((HERE / "artifacts/adapter" / name).read_bytes())["needed"]:
            library_paths[needed] = library(needed)
            queue.append(library_paths[needed])
    selected = {}
    while queue:
        path = resolve(queue.pop(0))
        if path in selected: continue
        info = metadata(data[path])
        # 此审计仅适用于已观察的默认目录，不静默忽略其他搜索路径。
        assert not info["searchPaths"], (path, info["searchPaths"])
        selected[path] = {"sha256": sha(data[path]), "bytes": len(data[path]), **info}
        for needed in info["needed"] + info["interpreter"]:
            library_paths[needed] = library(needed)
            queue.append(library_paths[needed])
    OUT.mkdir(parents=True, exist_ok=True)
    for path in selected:
        local = (OUT / "inputs" / path).resolve()
        local.relative_to((OUT / "inputs").resolve())
        local.parent.mkdir(parents=True, exist_ok=True)
        if local.exists(): assert local.read_bytes() == data[path], path
        else: local.write_bytes(data[path])
    report = {"firmware": "X1D-50c 1.25.0", "firmwareSha256": baseline.SHA256,
              "rootfsSha256": wanted, "referenceRevision": baseline.REVISION,
              "referenceBlob": baseline.REFERENCE_BLOB, "cameraAccess": False,
              "executedFirmware": False, "files": selected, "libraryPaths": library_paths,
              "aliases": used_aliases, "roots": roots,
              "scope": "四个进程及两个候选的 DT_NEEDED 闭包、PT_INTERP、显式 TurboJPEG；不执行初始化器或模拟动态插件加载",
              "sourceSha256": sha(Path(__file__).read_bytes())}
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixedInputFiles": len(selected), "aliases": len(used_aliases), "cameraAccess": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-reference", action="store_true")
    run(parser.parse_args().fetch_reference)
