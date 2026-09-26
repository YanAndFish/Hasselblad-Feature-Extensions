"""将固定 OTA 的 new 数据重建为本地只读研究镜像；不挂载、不执行固件。"""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache"
sys.path.insert(0, str(CACHE / "python"))
import brotli
from dissect.extfs import ExtFS
from dissect.extfs.exceptions import FileNotFoundError as ExtFileNotFoundError


def ranges(text):
    parts = list(map(int, text.split(",")))
    if parts[0] != len(parts) - 1 or parts[0] % 2:
        raise ValueError("transfer range 格式错误")
    result = list(zip(parts[1::2], parts[2::2]))
    if any(not 0 <= a < b <= 131072 for a, b in result):
        raise ValueError("transfer range 超出固定研究上限")
    return result


def reconstruct(ota, name):
    lines = ota.read(name + ".transfer.list").decode("ascii").splitlines()
    if lines[0] != "4" or lines[2:4] != ["0", "0"]:
        raise ValueError("只支持已核对的非增量 transfer v4")
    commands = [line.split() for line in lines[4:] if line.strip()]
    if any(len(c) != 2 or c[0] not in ("new", "zero", "erase") for c in commands):
        raise ValueError("未知 transfer 命令")
    parsed = [(command, ranges(r)) for command, r in commands]
    size = max(b for _, rs in parsed for a, b in rs) * 4096
    payload = brotli.decompress(ota.read(name + ".new.dat.br"))
    expected = sum((b - a) * 4096 for command, rs in parsed if command == "new" for a, b in rs)
    if len(payload) != expected:
        raise ValueError("new 数据大小不匹配")
    image = CACHE / (name + ".img")
    with image.open("wb") as out:
        out.truncate(size)
        pos = 0
        for command, rs in parsed:
            if command != "new":
                continue
            for a, b in rs:
                length = (b - a) * 4096
                out.seek(a * 4096)
                out.write(payload[pos:pos + length])
                pos += length
    return image


def run():
    manifest = json.loads((ROOT / "research/firmware-manifest.json").read_text())
    ota_entry = next(x for x in manifest["entries"] if x["name"] == "ota.zip")
    if hashlib.sha256((CACHE / "ota.zip").read_bytes()).hexdigest() != ota_entry["sha256"]:
        raise ValueError("OTA 校验失败")
    binaries = []
    with zipfile.ZipFile(CACHE / "ota.zip") as ota:
        for part in ("system", "vendor"):
            image = reconstruct(ota, part)
            with image.open("rb") as fh:
                fs = ExtFS(fh)
                for path in ("/bin/phocus", "/lib64/librcam.so", "/bin/camera-system", "/bin/camera-service", "/bin/bulk", "/lib64/lib_usb_transfer.so", "/bin/msg2dbus", "/bin/usb_bulk_raw_hbl",
                             "/lib64/libdcam_base.so", "/lib64/libdcam_frwk.so", "/lib64/libduml_frwk.so", "/lib64/libduml_hal.so", "/lib64/libduml_util.so", "/bin/dji_sys"):
                    try:
                        node = fs.get(path)
                    except (FileNotFoundError, ExtFileNotFoundError):
                        continue
                    # 只提取固定路径白名单；允许某个分区不含这些文件。
                    content = node.open().read()
                    target = CACHE / (part + "-" + Path(path).name)
                    target.write_bytes(content)
                    binaries.append({"partition": part, "path": path, "size": len(content),
                                     "sha256": hashlib.sha256(content).hexdigest()})
    (ROOT / "research/binary-manifest.json").write_text(json.dumps({"firmware": "4.2.0", "binaries": binaries}, indent=2) + "\n")
    print(json.dumps(binaries, indent=2))


if __name__ == "__main__":
    run()
