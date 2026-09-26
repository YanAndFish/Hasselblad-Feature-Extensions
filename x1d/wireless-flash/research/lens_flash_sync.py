"""共享镜头 1.9.11 固件的离线同步研究读取器；没有设备接口。

输入来自已保存的官方共享包，不能据此确定当前镜头运行版本。
"""
import hashlib
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

HERE = Path(__file__).resolve().parents[1]
HEX_SHA = "d1e71cf4ab3fc051a4b9ae5331ba3efe1cd6d4b7fecc8ad09a2595854ae76ce4"
IMAGE_SHA = "ea5fbae70c5c07a3efdc7127b4d858e0b1f57262dfb134b0f92694c1ca602aaf"


class SharedLensImage:
    def __init__(self):
        raw = (HERE / 'research/lens-speed-reference/artifact.hex').read_bytes()
        if hashlib.sha256(raw).hexdigest() != HEX_SHA:
            raise ValueError('fixed lens HEX mismatch')
        memory, upper, eof = {}, 0, False
        for line in raw.decode('ascii').splitlines():
            if eof or not line.startswith(':'):
                raise ValueError('HEX record boundary')
            row = bytes.fromhex(line[1:])
            if len(row) != row[0] + 5 or sum(row) & 255:
                raise ValueError('HEX record checksum')
            count, address, kind, data = row[0], int.from_bytes(row[1:3], 'big'), row[3], row[4:-1]
            if kind == 0:
                for index, value in enumerate(data):
                    key = upper + address + index
                    if key in memory:
                        raise ValueError('overlapping HEX data')
                    memory[key] = value
            elif kind == 1 and count == 0:
                eof = True
            elif kind == 4 and count == 2:
                upper = int.from_bytes(data, 'big') << 16
            elif kind == 5 and count == 4:
                self.start_linear = int.from_bytes(data, 'big')
            else:
                raise ValueError('unreviewed HEX record kind')
        if not eof or min(memory) != 0x60014c00 or max(memory) + 1 != 0x6004b0e8:
            raise ValueError('fixed lens image bounds')
        self.base = min(memory)
        self.data = bytes(memory.get(a, 0xff) for a in range(self.base, max(memory) + 1))
        if hashlib.sha256(self.data).hexdigest() != IMAGE_SHA or self.start_linear != 0x60015471:
            raise ValueError('fixed decoded lens image mismatch')
        # 0x60015470 启动代码使用的复制表；两段 ITCM 在源、目的均连续。
        table = struct.unpack('<19I', self.read(0x60015544, 76))
        if table != (0x60049034, 0x20200000, 0x202020b4,
                     0x202020b4, 0x202062b4,
                     0x60015c00, 0x400, 0x400,
                     0x60015c00, 0x400, 0x408,
                     0x60015c08, 0x410, 0x2a0d0,
                     0x6003f8c8, 0x2a0d0, 0x33834, 0, 0x400):
            raise ValueError('fixed startup copy table mismatch')
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
        self.decoder.detail = True

    def read(self, address, length):
        if 0x410 <= address and address + length <= 0x33834:
            address = 0x60015c08 + address - 0x410
        offset = address - self.base
        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise ValueError('outside fixed image')
        return self.data[offset:offset + length]

    def initial_read(self, address, length):
        """仅返回启动复制前的 .data 模板，不能代表镜头当前 RAM。"""
        if length < 0 or not 0x20200000 <= address <= address + length <= 0x202020b4:
            raise ValueError('outside initialized data template')
        return self.read(0x60049034 + address - 0x20200000, length)

    def initial_word(self, address):
        return struct.unpack('<I', self.initial_read(address, 4))[0]

    def word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def instructions(self, address, length):
        return list(self.decoder.disasm(self.read(address, length), address))
