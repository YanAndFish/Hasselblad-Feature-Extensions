"""固定原包 SUC 程序的离线读取；不执行固件或访问设备。"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct

from binary import ROOT, Cs, CS_ARCH_ARM, CS_MODE_LITTLE_ENDIAN
from capstone import CS_MODE_THUMB

SUC_PATH = "lib/firmware/hbl/su-control/camera-control-v1.25.0-14903-666e0d4.bin"
SUC_SHA = "6bce5b264f431250be952dcfcaefee45a435a6355ebc22b45c9e824c165725a7"


class SucImage:
    base = 0x08000000

    def __init__(self):
        assert Path.cwd().resolve() == ROOT.resolve()
        path = ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py"
        spec = importlib.util.spec_from_file_location("x1d_suc_diagnostic_input", path)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        reader.WANTED = {SUC_PATH}
        self.data = reader.inputs()[SUC_PATH]
        assert len(self.data) == 241708
        assert hashlib.sha256(self.data).hexdigest() == SUC_SHA
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
        self.decoder.skipdata = True

    def read(self, address, size):
        offset = address - self.base
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("固定 SUC 程序地址越界")
        return self.data[offset:offset + size]

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def instructions(self, address, size):
        return list(self.decoder.disasm(self.read(address, size), address))
