"""固定原包 FARM 应用的离线读取；不运行固件、不提供设备访问接口。"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct

from binary import ROOT, Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

PREFIX = "lib/firmware/hbl/farm/bootimage_"
SUFFIX = "-wedge-v1.25.0-13075-c9bb91d.bin"
HASHES = {
    PREFIX + "even" + SUFFIX: "e0575442e0831f0ba6cd65a5beedfc64bff2c992182220b7832a27e49928cac0",
    PREFIX + "odd" + SUFFIX: "2c1ff341653f6548c04c0cfb10db7e864887135f259e278066de49ae1c7967be",
}


class FarmApplication:
    base = 0x100000

    def __init__(self):
        assert Path.cwd().resolve() == ROOT.resolve()
        path = ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py"
        spec = importlib.util.spec_from_file_location("x1d_farm_diagnostic_input", path)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        reader.WANTED = set(HASHES)
        found = reader.inputs()
        for name, expected in HASHES.items():
            assert len(found[name]) == 3954444
            assert hashlib.sha256(found[name]).hexdigest() == expected
        even, odd = (found[PREFIX + part + SUFFIX] for part in ("even", "odd"))
        spread = [sum(((v >> bit) & 1) << (2 * bit) for bit in range(8)) for v in range(256)]
        combined = b"".join((spread[e] | (spread[o] << 1)).to_bytes(2, "big") for e, o in zip(even, odd))
        # 整幅哈希与此前独立核查相同；此处只读取第三分区，不重做启动介质研究。
        assert hashlib.sha256(combined).hexdigest() == "96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5"
        header = struct.unpack_from("<16I", combined, 0xD00)
        assert sum(header) & 0xFFFFFFFF == 0xFFFFFFFF
        offset, size, load, entry = header[5] * 4, header[2] * 4, header[3], header[4]
        assert (offset, size, load, entry) == (0x5D1680, 1808280, self.base, self.base)
        assert offset + size <= len(combined)
        self.data = combined[offset:offset + size]
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        self.decoder.skipdata = True

    def read(self, address, size):
        offset = address - self.base
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("固定 FARM 应用地址越界")
        return self.data[offset:offset + size]

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def instructions(self, address, size):
        return list(self.decoder.disasm(self.read(address, size), address))

    def disassembly(self, address, size):
        return "\n".join(f"{i.address:08x}  {i.bytes.hex()}  {i.mnemonic:8} {i.op_str}"
                         for i in self.instructions(address, size))
