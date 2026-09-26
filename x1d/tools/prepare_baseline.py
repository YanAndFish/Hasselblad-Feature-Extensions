"""取得第一代 X1D-50c 1.25.0 的固定离线输入，不执行包内程序。"""
from __future__ import annotations

import ast
import bz2
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".research-cache" / "x1d-1.25.0"
BASELINE = CACHE / "baseline"
sys.path.insert(0, str(CACHE / "python"))
URL = "https://cdn.hasselblad.com/firmware/X1D-50c_Firmware/1.25.0/X1D_v1_25_0.cim"
SIZE = 63_410_176
SHA256 = "1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2"
REVISION = "768664267cb44621c3c12595ee9cc538020b1b94"
REFERENCE = f"https://raw.githubusercontent.com/YuHaoyua/hasselblad-cim-firmware-extractor/{REVISION}/hasselblad_extract.py"
REFERENCE_BLOB = "35469a59ee6357de7bfe90dbbafe03d248e3b7e9"
PARTS = {"hbl-upgrade": (0x600, 7783), "rootfs": (0x2600, 63123278),
         "uboot": (0x3C35600, 269312), "hbl-kks-revisions": (0x3C77400, 7030)}
EXPECTED_ELF = {
    "usr/bin/jpeg-daemon": "ad4092c0a36344427d018af03c9ff8b5524c02627edadaab7217641ac3bf274a",
    "usr/bin/camera-daemon": "bd7a0f7035f499b761a6994e370237bb11d2151801afd3de545b5cfd26db705a",
    "usr/bin/storage-daemon": "5dd2000254b926cacae97acca5dcf3b4b677633b8baddd2a3e6ef6785427396a",
    "usr/bin/victory-gui": "d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("固定输入拒绝重定向")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, limit: int) -> bytes:
    if url not in (URL, REFERENCE):
        raise ValueError("输入 URL 不在白名单")
    request = urllib.request.Request(url, headers={"User-Agent": "X1D-offline-research/0.1"})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("输入大小超过固定边界")
    return data


def keep_baseline(path: Path, data: bytes) -> None:
    """已存在的输入只能一致；不覆盖不同内容，也不覆盖实验产物。"""
    path.resolve().relative_to(CACHE.resolve())
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("已有基线内容不同，停止")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def reference_constants(source: bytes) -> dict[str, bytes]:
    if hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest() != REFERENCE_BLOB:
        raise ValueError("参考源码版本校验失败")
    wanted = {"STATIC_KEY", "IV_SALT", "MAGIC_HASH_SALT"}
    result = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name) or target.id not in wanted:
            continue
        if target.id in result or not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "bytes" and len(value.args) == 1 and not value.keywords):
            raise ValueError("参考字面量结构变化")
        material = ast.literal_eval(value.args[0])
        if not isinstance(material, list) or len(material) != 16 or any(type(v) is not int or not 0 <= v <= 255 for v in material):
            raise ValueError("参考字面量不符合边界")
        result[target.id] = bytes(material)
    if set(result) != wanted:
        raise ValueError("参考字面量不完整")
    return result


def selected(path: str, size: int) -> bool:
    if path in EXPECTED_ELF:
        return True
    if path in {"usr/bin/upgrade_from_slot.sh", "usr/bin/hbl-post-upgrade",
                "usr/bin/program_nodes.sh", "usr/bin/upgrade.sh"}:
        return True
    if path.startswith("usr/bin/") and re.search(r"/(?:configstore|upgrade-daemon|bodysync[^/]*|suc[^/]*|farm[^/]*|phocus-daemon|is_[^/]*)$", path):
        return True
    if path.startswith("usr/lib/") and re.search(r"/(?:libappscommon|libvpu|libjpeg|libturbojpeg|libQt5(?:Core|Gui|DBus|Quick|Qml|Network)|libstdc\+\+)\.so\.", path):
        return True
    if path in {"lib/libgcc_s.so.1", "lib/libc-2.22.so", "lib/libdl-2.22.so",
                "lib/libm-2.22.so", "lib/libpthread-2.22.so", "lib/librt-2.22.so", "lib/ld-2.22.so"}:
        return True
    if path.startswith(("etc/", "lib/systemd/")) and size < 200_000:
        return True
    return path.endswith(".dtb") or (path.startswith("lib/firmware/hbl/su-control/") and path.endswith(".bin"))


def run() -> None:
    from Crypto.Cipher import AES

    input_path = CACHE / "X1D_v1_25_0.cim"
    firmware = input_path.read_bytes() if input_path.exists() else fetch(URL, SIZE)
    if len(firmware) != SIZE or sha(firmware) != SHA256:
        raise ValueError("官方固件大小或 SHA-256 不匹配")
    keep_baseline(input_path, firmware)
    # 参考脚本只在内存中解析三个字面量；不保存、导入或执行它。
    constants = reference_constants(fetch(REFERENCE, 65536))
    match = re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})", firmware[:128])
    if not firmware.startswith(b"VHABCIM\r\n") or match is None:
        raise ValueError("固定固件头格式不匹配")
    year, month, day, hour, minute, second = map(int, match.groups())
    initial = hashlib.md5(constants["IV_SALT"] + bytes([year // 100, year % 100, month, day, hour, minute, second]) + bytes(9)).digest()

    def decrypt(offset: int, size: int) -> bytes:
        if offset < 0x80 or size <= 0 or offset + ((size + 15) // 16) * 16 > len(firmware):
            raise ValueError("条目范围无效")
        result = bytearray()
        for pos in range(0, size, 4096):
            count = min(4096, size - pos)
            block = firmware[offset + pos:offset + pos + ((count + 15) // 16) * 16]
            result.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(block)[:count])
        return bytes(result)

    table = decrypt(0x80, 0x580)
    # 官方 1.25.0 upgrade-daemon 的 format 3 路径：
    # PrivateHeader::read 0x30314 -> 0x30a40 -> 0x2d6ac。
    # 只验证固定原包；没有重新封装或生成可刷包的入口。
    if int.from_bytes(firmware[60:64], "big") != 3 or int.from_bytes(firmware[68:72], "big") != len(firmware):
        raise ValueError("固定包格式或声明长度变化")
    container_digest = hashlib.md5(firmware[0x200:] + constants["MAGIC_HASH_SALT"]).digest()
    private_digest = hashlib.md5(container_digest + table[32:384]).digest()
    if private_digest != table[16:32] or int.from_bytes(table[60:64], "big") != 4:
        raise ValueError("私有头内容校验或条目数量不匹配")
    payload = {}
    entries = []
    for match in re.finditer(rb"\x00{16,}(?P<name>[\x20-\x7e]{3,})\x00", table):
        begin = match.start() - 24
        if begin < 0:
            continue
        name = match.group("name").decode("ascii")
        if name not in PARTS or name in payload:
            raise ValueError("条目名称发生变化")
        offset, size, expected = struct.unpack_from(">II16s", table, begin)
        if (offset, size) != PARTS[name]:
            raise ValueError("固定条目位置发生变化")
        content = decrypt(offset, size)
        if hashlib.md5(content + constants["MAGIC_HASH_SALT"]).digest() != expected:
            raise ValueError("包内条目内容校验失败")
        payload[name] = content
        entries.append({"name": name, "offset": offset, "bytes": size, "sha256": sha(content), "contentChecksumVerified": True})
    if set(payload) != set(PARTS):
        raise ValueError("四个条目不完整")

    files = []
    inventory = []
    with bz2.BZ2File(io.BytesIO(payload["rootfs"])) as expanded, tarfile.open(fileobj=expanded, mode="r|") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError("归档路径不符合边界")
            inventory.append({"path": name, "bytes": member.size, "kind": member.type.decode("ascii", "replace")})
            if not member.isfile() or not selected(name, member.size):
                continue
            if member.size > 16 * 1024 * 1024:
                raise ValueError("单个研究输入超过选择边界")
            content = archive.extractfile(member).read()
            if name in EXPECTED_ELF and sha(content) != EXPECTED_ELF[name]:
                raise ValueError("已定位 ELF 与静态基线不一致")
            keep_baseline(BASELINE / name, content)
            files.append({"path": name, "bytes": len(content), "sha256": sha(content)})
    if not set(EXPECTED_ELF).issubset({item["path"] for item in files}):
        raise ValueError("必需 ELF 不完整")
    keep_baseline(BASELINE / "hbl-kks-revisions", payload["hbl-kks-revisions"])
    keep_baseline(BASELINE / "hbl-upgrade", payload["hbl-upgrade"])
    keep_baseline(BASELINE / "uboot.bin", payload["uboot"])
    report = {"schemaVersion": 1, "model": "X1D-50c (first generation)", "firmware": "1.25.0",
              "url": URL, "bytes": SIZE, "sha256": SHA256, "referenceRevision": REVISION,
              "executedFirmware": False, "cameraAccess": False, "entries": entries, "files": files,
              "cimFormat": 3, "declaredFileSizeMatches": True, "privateHeaderChecksumVerified": True,
              "sourceScope": "官方二进制包；嵌入 QML/脚本不等于专有原生组件源码"}
    output = ROOT / "x1d" / "research"
    output.mkdir(parents=True, exist_ok=True)
    (output / "baseline-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    keep_baseline(CACHE / "rootfs-inventory.json", (json.dumps(inventory, indent=2) + "\n").encode())
    print(f"第一代 X1D 1.25.0 输入校验完成：{len(files)} 个独立研究输入，{len(inventory)} 个归档条目；未执行固件。")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        run()
    except Exception as error:
        print("X1D 离线输入准备失败：" + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
