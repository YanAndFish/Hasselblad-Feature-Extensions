"""固定 1.25.0 包内 U-Boot 与 FDT 的只读解析；不执行固件或命令。"""
from __future__ import annotations
import hashlib
import struct
from binary import BASELINE, Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN


class Uboot:
    base = 0x177FF400

    def __init__(self):
        self.data = (BASELINE / "uboot.bin").read_bytes()
        if hashlib.sha256(self.data).hexdigest() != "bad3ab600873fa78adb7cc06190ff092052ff11b20f012da9c18cf22cddba8d3":
            raise ValueError("包内 U-Boot 输入不同")
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        self.decoder.skipdata = True

    def read(self, address, size):
        offset = address - self.base
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError("U-Boot 地址范围错误")
        return self.data[offset:offset + size]

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def string(self, address):
        data = self.read(address, min(4096, self.base + len(self.data) - address))
        end = data.index(0)
        return data[:end].decode("ascii")

    def pointer_refs(self, address):
        return [self.base + p for p in range(0, len(self.data) - 3, 4)
                if struct.unpack_from("<I", self.data, p)[0] == address]

    def literal_loads(self, literal_address):
        found = []
        for offset in range(0xC00, 0x2F460, 4):
            address = self.base + offset
            word = self.word(address)
            if word & 0x0F7F0000 == 0x051F0000:
                delta = word & 0xFFF
                target = address + 8 + (delta if word & 0x800000 else -delta)
                if target == literal_address:
                    found.append(address)
        return found

    def disassembly(self, address, size):
        return "\n".join(f"{i.address:08x}  {bytes(i.bytes).hex()}  {i.mnemonic:8s} {i.op_str}"
                         for i in self.decoder.disasm(self.read(address, size), address))

    def commands(self):
        """读取本包实际 28 字节命令表；usage/help 可以为 NULL。"""
        found = []
        for address in range(0x1783A1C0, 0x1783AA48, 28):
            fields = struct.unpack("<7I", self.read(address, 28))
            if not (self.base <= fields[0] < self.base + len(self.data) and
                    1 <= fields[1] <= 255 and fields[2] in (0, 1) and
                    0x17800000 <= fields[3] < 0x1782E860):
                raise ValueError(f"固定命令表结构不符：{address:#x}")
            name = self.string(fields[0])
            usage, help_text = [self.string(fields[i]) if fields[i] else None for i in (4, 5)]
            if not name or len(name) > 32 or not all(c.islower() or c.isdigit() or c in "_?" for c in name):
                raise ValueError(f"固定命令名称不符：{address:#x}")
            found.append({"entry": address, "name": name, "maxargs": fields[1],
                          "repeatable": fields[2], "handler": fields[3], "usage": usage, "help": help_text})
        return found


def fdt_nodes(data):
    if len(data) < 40 or struct.unpack_from(">I", data)[0] != 0xD00DFEED:
        raise ValueError("FDT 头错误")
    header = struct.unpack_from(">10I", data)
    if header[1] != len(data):
        raise ValueError("FDT 声明长度错误")
    position, strings = header[2], header[3]
    stack, result = [], {}
    while position + 4 <= len(data):
        token = struct.unpack_from(">I", data, position)[0]
        position += 4
        if token == 1:
            end = data.index(0, position)
            name = data[position:end].decode("ascii")
            position = (end + 4) & ~3
            stack.append(name)
            result["/".join(stack)] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, offset = struct.unpack_from(">2I", data, position)
            position += 8
            start = strings + offset
            key = data[start:data.index(0, start)].decode("ascii")
            if position + size > len(data):
                raise ValueError("FDT 属性范围错误")
            result["/".join(stack)][key] = data[position:position + size]
            position = (position + size + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            return result
        else:
            raise ValueError("FDT token 错误")
    raise ValueError("FDT 未终止")
