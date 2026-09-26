"""固定官方 4.2.0 输入；仅下载与离线解析，不访问任何设备。"""
from pathlib import Path
import ast
import hashlib
import json
import re
import struct
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache"
sys.path.insert(0, str(CACHE / "python"))
URL = "https://cdn.hasselblad.com/firmware/X2D-100C-Firmware/4.2.0/X2D_100C_v4_2_0.cim"
SHA256 = "5ae67d16a24b00f9300e3e9c1323e7d149248ad36975e12c4fa8da633b438e03"
SIZE = 175245312
REVISION = "768664267cb44621c3c12595ee9cc538020b1b94"
REFERENCE = f"https://raw.githubusercontent.com/YuHaoyua/hasselblad-cim-firmware-extractor/{REVISION}/hasselblad_extract.py"
REFERENCE_BLOB = "35469a59ee6357de7bfe90dbbafe03d248e3b7e9"
EXPECTED_NAMES = {"ota.zip", "exMCU_x2.cont", "exMCU_cfv.cont", "exMCUloader.cont", "ccg3_2.cont", "hbl-upgrade", "hbl-post-upgrade", "ec2107_cpld.bit"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("下载拒绝重定向")


def download(url, path, limit):
    if url not in (URL, REFERENCE):
        raise ValueError("下载源不在白名单")
    if path.exists():
        return path.read_bytes()
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "Hasselblad-offline-research/0.1"})
    with opener.open(req, timeout=30) as response:
        data = bytearray()
        while chunk := response.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("下载超出固定大小上限")
    path.write_bytes(data)
    return bytes(data)


def reference_constants(source):
    """只解析三个字面量；不 import、eval 或执行第三方脚本，不输出材料。"""
    wanted = {"STATIC_KEY", "IV_SALT", "MAGIC_HASH_SALT"}
    result = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and target.id in wanted:
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id == "bytes" and len(value.args) == 1 and not value.keywords):
                raise ValueError("参考常量格式变化")
            result[target.id] = bytes(ast.literal_eval(value.args[0]))
    if set(result) != wanted or any(len(x) != 16 for x in result.values()):
        raise ValueError("参考常量不完整")
    return result


def run():
    from Crypto.Cipher import AES
    CACHE.mkdir(exist_ok=True)
    data = download(URL, CACHE / "X2D_100C_v4_2_0.cim", SIZE)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("官方固件校验失败，停止")
    source = download(REFERENCE, CACHE / "reference-source.txt", 65536)
    if hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest() != REFERENCE_BLOB:
        raise ValueError("参考源码版本校验失败")
    constants = reference_constants(source)
    header = data[:128].split(b"\x1a", 1)[0].decode("ascii")
    date = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", header)
    time = re.search(r"\b(\d{2}):(\d{2}):(\d{2})\b", header)
    if not data.startswith(b"VHABCIM\r\n") or not date or not time:
        raise ValueError("固件头格式不匹配")
    year, month, day = map(int, date.groups())
    stamp = bytes([year // 100, year % 100, month, day, *map(int, time.groups())]) + bytes(9)
    initial = hashlib.md5(constants["IV_SALT"] + stamp).digest()

    def decrypt(offset, size):
        if offset < 128 or size <= 0 or offset + ((size + 15) // 16 * 16) > len(data):
            raise ValueError("条目越界")
        out = bytearray()
        for pos in range(0, size, 4096):
            count = min(4096, size - pos)
            encrypted = data[offset + pos:offset + pos + ((count + 15) // 16 * 16)]
            out.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(encrypted)[:count])
        return bytes(out)

    table = decrypt(0x80, 0x2000)
    entries = []
    for match in re.finditer(rb"\x00{16,}(?P<name>[\x20-\x7e]{3,})\x00", table):
        begin = match.start() - 24
        if begin < 0:
            continue
        offset, size, expected = struct.unpack_from(">II16s", table, begin)
        name = match.group("name").decode("ascii")
        if name not in EXPECTED_NAMES:
            continue
        content = decrypt(offset, size)
        if hashlib.md5(content + constants["MAGIC_HASH_SALT"]).digest() != expected:
            raise ValueError("条目内容校验失败")
        entries.append({"name": name, "offset": offset, "size": size, "checksumVerified": True,
                        "sha256": hashlib.sha256(content).hexdigest()})
        if name == "ota.zip":
            (CACHE / name).write_bytes(content)
    if len(entries) != 8 or {e["name"] for e in entries} != EXPECTED_NAMES:
        raise ValueError("未找到全部八个条目，禁止猜测回退")
    manifest = {"schemaVersion": 1, "source": "official-firmware-static", "model": "X2D 100C",
                "firmware": "4.2.0", "url": URL, "bytes": SIZE, "sha256": SHA256,
                "referenceRevision": REVISION, "entries": entries}
    (ROOT / "research").mkdir(exist_ok=True)
    (ROOT / "research" / "firmware-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("官方 4.2.0 SHA-256 与全部八个条目校验通过。")
    with zipfile.ZipFile(CACHE / "ota.zip") as ota:
        print(json.dumps([{"name": x.filename, "size": x.file_size} for x in ota.infolist()], indent=2))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        # 不输出底层异常中的潜在材料、网络响应或文件内容。
        print("离线准备失败：" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
