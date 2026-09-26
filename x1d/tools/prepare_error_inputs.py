"""从固定官方 1.25.0 原包取得错误/日志/网络的补充离线输入；不执行固件。"""
from __future__ import annotations

import bz2
import hashlib
import io
import json
import re
import tarfile
from prepare_baseline import (CACHE, ROOT, SIZE, SHA256, REFERENCE, URL,
                              fetch, keep_baseline, reference_constants, sha)

OUT = CACHE / "error-inputs"
WANTED = {
    "usr/bin/system-manager", "usr/bin/hbl-collect-logs.sh",
    "usr/bin/hbl-save-error-logs.sh", "usr/bin/network-manager",
    "usr/bin/phocus-mobile-server", "usr/bin/program_fx3.sh",
}


def run():
    from Crypto.Cipher import AES
    firmware = (CACHE / "X1D_v1_25_0.cim").read_bytes()
    assert len(firmware) == SIZE and sha(firmware) == SHA256
    constants = reference_constants(fetch(REFERENCE, 65536))
    match = re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})", firmware[:128])
    assert match is not None and firmware.startswith(b"VHABCIM\r\n")
    year, month, day, hour, minute, second = map(int, match.groups())
    initial = hashlib.md5(constants["IV_SALT"] + bytes([
        year // 100, year % 100, month, day, hour, minute, second]) + bytes(9)).digest()
    offset, size = 0x2600, 63123278
    payload = bytearray()
    for pos in range(0, size, 4096):
        count = min(4096, size - pos)
        block = firmware[offset + pos:offset + pos + ((count + 15) // 16) * 16]
        payload.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(block)[:count])
    assert sha(payload) == "8e9ef7f19411a355eeef7b44361d35635c80a248cc9753b0a8456cf1008583ca"
    files, links = [], []
    with bz2.BZ2File(io.BytesIO(payload)) as expanded, tarfile.open(fileobj=expanded, mode="r|") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            assert not name.startswith("/") and ".." not in name.split("/")
            if member.issym() and name.startswith("etc/systemd/") and (
                    "verylate" in name or name.endswith(("default.target", "system-manager.service"))):
                links.append({"path": name, "target": member.linkname})
            if name not in WANTED:
                continue
            assert member.isfile() and 0 < member.size < 1000000
            content = archive.extractfile(member).read()
            keep_baseline(OUT / name, content)
            files.append({"path": name, "bytes": len(content), "sha256": sha(content)})
    assert {x["path"] for x in files} == WANTED and len(files) == len(WANTED)
    report = {"firmware": "X1D-50c 1.25.0", "url": URL, "sha256": SHA256,
              "rootfsSha256": sha(payload), "executedFirmware": False, "cameraAccess": False,
              "files": files, "systemdLinks": links,
              "scope": "错误/日志/网络补充静态输入；不覆盖原基线清单或增强候选"}
    destination = ROOT / "x1d/research/error-input-manifest.json"
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if destination.exists():
        assert destination.read_bytes() == encoded
    else:
        with destination.open("xb") as output:
            output.write(encoded)
    print(f"补充离线输入已校验：{len(files)}文件、{len(links)}个启动链接；未执行固件。")


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        print("补充输入准备失败：" + type(error).__name__)
        raise SystemExit(1)
