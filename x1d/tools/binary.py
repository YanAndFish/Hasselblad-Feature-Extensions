"""第一代 X1D 固定基线的 ELF/QRC 读取工具；没有设备或固件执行入口。"""
from __future__ import annotations

import io
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".research-cache" / "x1d-1.25.0"
BASELINE = CACHE / "baseline"
sys.path.insert(0, str(CACHE / "python"))

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_INS_BL, ARM_INS_BLX
from elftools.elf.elffile import ELFFile


class ArmElf:
    def __init__(self, data: bytes):
        self.data = data
        self.elf = ELFFile(io.BytesIO(data))
        if self.elf.elfclass != 32 or not self.elf.little_endian or self.elf["e_machine"] != "EM_ARM":
            raise ValueError("仅接受 ARM32 little-endian ELF")
        self.sections = list(self.elf.iter_sections())
        self.symbols = []
        self.direct = {}
        self.plt = {}
        for section in self.sections:
            if section["sh_type"] not in ("SHT_DYNSYM", "SHT_SYMTAB"):
                continue
            for symbol in section.iter_symbols():
                self.symbols.append(symbol)
                if symbol["st_shndx"] != "SHN_UNDEF" and symbol.name:
                    self.direct[symbol["st_value"]] = symbol.name
        for section in self.sections:
            if section.name != ".rel.plt":
                continue
            symbols = self.sections[section["sh_link"]]
            for relocation in section.iter_relocations():
                self.plt[relocation["r_offset"]] = symbols.get_symbol(relocation["r_info_sym"]).name
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        self.decoder.skipdata = True

    @classmethod
    def load(cls, relative: str) -> "ArmElf":
        path = BASELINE / relative
        path.resolve().relative_to(BASELINE.resolve())
        return cls(path.read_bytes())

    def offset(self, address: int, size: int = 1) -> int:
        for section in self.sections:
            if section["sh_type"] == "SHT_NOBITS":
                continue
            start = section["sh_addr"]
            if start <= address and address + size <= start + section["sh_size"]:
                return section["sh_offset"] + address - start
        raise ValueError(f"ELF 地址未映射：{address:#x}")

    def read(self, address: int, size: int) -> bytes:
        offset = self.offset(address, size)
        return self.data[offset:offset + size]

    def word(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    @staticmethod
    def immediate(word: int) -> int:
        value, rotation = word & 255, ((word >> 8) & 15) * 2
        return ((value >> rotation) | (value << (32 - rotation))) & 0xFFFFFFFF if rotation else value

    def name(self, address: int) -> str:
        if address in self.direct:
            return self.direct[address]
        current = None
        try:
            for at in range(address, address + 12, 4):
                word = self.word(at)
                rn, rd = (word >> 16) & 15, (word >> 12) & 15
                if word & 0x0FE00000 == 0x02800000 and rd == 12 and rn in (12, 15):
                    base = at + 8 if rn == 15 else current
                    if base is None:
                        return ""
                    current = (base + self.immediate(word)) & 0xFFFFFFFF
                elif word & 0x0E100000 == 0x04100000 and rn == 12 and rd == 15 and current is not None:
                    slot = current + ((word & 4095) if word & (1 << 23) else -(word & 4095))
                    return self.plt.get(slot & 0xFFFFFFFF, "")
        except ValueError:
            pass
        return ""

    def instructions(self, address: int, size: int):
        return list(self.decoder.disasm(self.read(address, size), address))

    def disassembly(self, address: int, size: int) -> str:
        lines = []
        for instruction in self.instructions(address, size):
            name = ""
            if instruction.id in (ARM_INS_BL, ARM_INS_BLX) and instruction.op_str.startswith("#"):
                name = self.name(int(instruction.op_str[1:], 0))
            lines.append(f"{instruction.address:08x}  {instruction.bytes.hex():8}  {instruction.mnemonic:8} {instruction.op_str}" + (f"  ; {name}" if name else ""))
        return "\n".join(lines)

    def functions(self) -> list[int]:
        section = self.elf.get_section_by_name(".ARM.exidx")
        if section is None:
            return []
        result = []
        for at in range(section["sh_addr"], section["sh_addr"] + section["sh_size"], 8):
            offset = self.word(at) & 0x7FFFFFFF
            if offset & 0x40000000:
                offset -= 0x80000000
            result.append((at + offset) & 0xFFFFFFFF)
        return result

    def direct_calls(self, address: int, size: int):
        for instruction in self.instructions(address, size):
            if instruction.id in (ARM_INS_BL, ARM_INS_BLX) and instruction.op_str.startswith("#"):
                target = int(instruction.op_str[1:], 0)
                yield instruction.address, target, self.name(target)

    def meta_object(self, symbol_name: str) -> dict:
        symbol = next(s for s in self.symbols if s.name == symbol_name and s["st_shndx"] != "SHN_UNDEF")
        pointers = struct.unpack("<6I", self.read(symbol["st_value"], 24))
        header = struct.unpack("<14I", self.read(pointers[2], 56))
        if header[0] != 7:
            raise ValueError("Qt 元对象布局不匹配")

        def name(index: int) -> str:
            at = pointers[1] + index * 16
            _, length, _, offset = struct.unpack("<iIIi", self.read(at, 16))
            if length >= 2000:
                raise ValueError("Qt 元对象字符串越界")
            return self.read(at + offset, length).decode("utf-8")

        methods, properties, enums = [], [], []
        for index in range(header[4]):
            entry = struct.unpack("<5I", self.read(pointers[2] + 4 * (header[5] + 5 * index), 20))
            methods.append({"index": index, "name": name(entry[0]), "arguments": entry[1]})
        for index in range(header[6]):
            entry = struct.unpack("<3I", self.read(pointers[2] + 4 * (header[7] + 3 * index), 12))
            properties.append({"index": index, "name": name(entry[0]), "type": entry[1], "flags": entry[2]})
        for index in range(header[8]):
            entry = struct.unpack("<4I", self.read(pointers[2] + 4 * (header[9] + 4 * index), 16))
            values = []
            for number in range(entry[2]):
                key, value = struct.unpack("<Ii", self.read(pointers[2] + 4 * (entry[3] + number * 2), 8))
                values.append({"name": name(key), "value": value})
            enums.append({"name": name(entry[0]), "values": values})
        return {"address": symbol["st_value"], "dispatch": pointers[3], "methods": methods,
                "properties": properties, "enums": enums}


def qml_files(gui: ArmElf) -> dict[str, str]:
    """仅匹配已绑定 1.25.0 的 Qt 资源布局；返回文本，不运行 QML。"""
    resources = [(0x10C75C, 0x10C5E8, 0x94E20), (0x1EC7F0, 0x1E7E44, 0x10C7F8)]
    result = {}
    for tree, names, data in resources:
        pending = [(0, "")]
        seen = set()
        while pending:
            index, parent = pending.pop()
            if index in seen or len(seen) >= 10000:
                raise ValueError("QRC 索引无效")
            seen.add(index)
            entry = gui.read(tree + 14 * index, 14)
            name_offset, flags = struct.unpack_from(">IH", entry)
            name_len = struct.unpack(">H", gui.read(names + name_offset, 2))[0]
            if name_len >= 1024:
                raise ValueError("QRC 名称超长")
            name = gui.read(names + name_offset + 6, name_len * 2).decode("utf-16be") if index else ""
            path = parent + "/" + name if name else parent
            if flags & 2:
                count, child = struct.unpack_from(">II", entry, 6)
                if count >= 10000:
                    raise ValueError("QRC 子项超出边界")
                pending.extend((number, path) for number in range(child, child + count))
            elif path.endswith((".qml", ".js", ".conf")):
                offset = struct.unpack_from(">I", entry, 10)[0]
                size = struct.unpack(">I", gui.read(data + offset, 4))[0]
                if size >= 300000:
                    raise ValueError("QRC 文本超出范围")
                content = gui.read(data + offset + 4, size)
                if flags & 1:
                    expanded_size = struct.unpack_from(">I", content)[0]
                    if expanded_size >= 1000000:
                        raise ValueError("QRC 展开超出范围")
                    content = zlib.decompress(content[4:])
                    if len(content) != expanded_size:
                        raise ValueError("QRC 展开长度不匹配")
                if path in result:
                    raise ValueError("QRC 文本重复")
                result[path] = content.decode("utf-8")
    return result
