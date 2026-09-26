"""取得正常 USB 诊断链的两个固定官方离线输入；不打开设备或执行固件。"""
from __future__ import annotations
import bz2
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from prepare_baseline import (CACHE, ROOT, SIZE, SHA256, REFERENCE, URL,
                              fetch, keep_baseline, reference_constants, sha)

WANTED = {"usr/bin/msg2dbus", "usr/lib/libAppsMessaging.so"}


def run():
    assert Path.cwd().resolve() == ROOT.resolve(), "必须在当前 Hasselblad local 工作区运行"
    from Crypto.Cipher import AES
    firmware = (CACHE / "X1D_v1_25_0.cim").read_bytes()
    assert len(firmware) == SIZE and sha(firmware) == SHA256
    constants = reference_constants(fetch(REFERENCE, 65536))
    match = re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})", firmware[:128])
    assert match is not None and firmware.startswith(b"VHABCIM\r\n")
    year, month, day, hour, minute, second = map(int, match.groups())
    initial = hashlib.md5(constants["IV_SALT"] + bytes([
        year // 100, year % 100, month, day, hour, minute, second]) + bytes(9)).digest()
    payload = bytearray()
    for pos in range(0, 63123278, 4096):
        count = min(4096, 63123278 - pos)
        block = firmware[0x2600 + pos:0x2600 + pos + ((count + 15) // 16) * 16]
        payload.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(block)[:count])
    assert sha(payload) == "8e9ef7f19411a355eeef7b44361d35635c80a248cc9753b0a8456cf1008583ca"
    files = []
    with bz2.BZ2File(io.BytesIO(payload)) as expanded, tarfile.open(fileobj=expanded, mode="r|") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name not in WANTED: continue
            assert member.isfile() and 0 < member.size < 1000000
            content = archive.extractfile(member).read()
            keep_baseline(CACHE / "usb-diagnostic-inputs" / name, content)
            files.append({"path": name, "bytes": len(content), "sha256": sha(content)})
    assert {x["path"] for x in files} == WANTED and len(files) == len(WANTED)
    report = {"firmware": "X1D-50c 1.25.0", "url": URL, "sha256": SHA256,
              "rootfsSha256": sha(payload), "executedFirmware": False, "cameraAccess": False,
              "files": files, "scope": "正常 Phocus/Usbif 消息链的补充静态输入"}
    destination = ROOT / "x1d/research/usb-diagnostic-input-manifest.json"
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if destination.exists(): assert destination.read_bytes() == encoded
    else:
        with destination.open("xb") as output: output.write(encoded)
    print(f"正常 USB 链补充输入已校验：{len(files)} 文件；未执行固件或请求设备。")


if __name__ == "__main__":
    try: run()
    except Exception as error:
        print("补充输入准备失败：" + type(error).__name__)
        raise SystemExit(1)
