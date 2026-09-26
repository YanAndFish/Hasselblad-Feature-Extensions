"""固定离线 ELF 的符号/反汇编查看器；绝不运行固件。"""
from pathlib import Path
import argparse
import hashlib
import io
import lzma
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".research-cache/python"))
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN


HASHES = {
    "phocus": "56c9a777fb9c5ed228fc32b47013822b34bd9109822871089700d23dd40a1516",
    "camera-system": "bf854a21881148565ff2cc00376426c37a2b82fed94c653abf024e23ed4ceda6",
    "camera-service": "fbcf828f73bca13f0c8b95e7dd0b95ac483ae36954ec06179098c8a1a65f9f82",
    "librcam.so": "72ebc8deebce4a29047c475e77ab4edbf2860abb1f572fea45260fe17ad0bda5",
    "bulk": "d1b9e624e4587e19a1cb9f0616de3536bc30ce096b93651e9512972e54ea3266",
    "lib_usb_transfer.so": "ae80afb6415366effd214b8a85e0c27caadbbde518ec7ceaf2a2e07a357d849d",
    "msg2dbus": "c02c2cd83ec9e5d7862659f05328927b7faa3e57789dd4aa0fd9bc427ad13a43",
    "libdcam_base.so": "b6e33f0ee76e4d056e519574a0a2f3860935252010fec676be320e304a7ff81c",
    "libdcam_frwk.so": "6d26f038175fc736dfc3e6b67c93f2d997895014be8e5c3040654cfb26bb501e",
    "libduml_frwk.so": "bb110a2c94e6ed5b69a99048f3a30db5760754ec12ff4d1bdd7f6f431139b81d",
    "libduml_hal.so": "77875f6f47a2137e5461c61789d44fdd8537e7359c8d7b43ec7ee4737fd15bb3",
    "dji_sys": "e20a9060550c23ae60f8bb3e7ce74de065c24da969c2502038ffadc3ebf065c7",
    "libduml_util.so": "71dcc8de23133d25c415be948b02b6f43f02f05408a5349463a3dc51cc419d11",
    "usb_bulk_raw_hbl": "918d1c96a7e269a16b7759f93fb79bc5f47a2b6d973fc96e637e516a95afa90f"
}


class Binary:
    def __init__(self, binary="phocus"):
        if binary not in HASHES:
            raise ValueError("只支持固定研究对象")
        self.data = (ROOT / (".research-cache/system-" + binary)).read_bytes()
        if hashlib.sha256(self.data).hexdigest() != HASHES[binary]:
            raise ValueError("研究 ELF 哈希不匹配")
        self.elf = ELFFile(io.BytesIO(self.data))
        if self.elf["e_machine"] != "EM_AARCH64":
            raise ValueError("当前查看器只反汇编 AArch64，拒绝以错误架构解释固件")
        symbols_elf = self.elf
        if not symbols_elf.get_section_by_name(".symtab"):
            debug = self.elf.get_section_by_name(".gnu_debugdata")
            if debug:
                symbols_elf = ELFFile(io.BytesIO(lzma.decompress(debug.data())))
        static_symbols = symbols_elf.get_section_by_name(".symtab")
        self.symbols = list(static_symbols.iter_symbols()) if static_symbols else []
        dynamic_symbols = self.elf.get_section_by_name(".dynsym")
        if dynamic_symbols:
            self.symbols.extend(dynamic_symbols.iter_symbols())
        if not self.symbols:
            raise ValueError("缺少离线符号")
        self.names = {s["st_value"]: s.name for s in self.symbols if s["st_value"] and s.name}
        relplt = self.elf.get_section_by_name(".rela.plt")
        plt = self.elf.get_section_by_name(".plt")
        if relplt and plt:
            dynamic = self.elf.get_section(relplt["sh_link"])
            for index, relocation in enumerate(relplt.iter_relocations()):
                self.names[plt["sh_addr"] + 32 + index * 16] = dynamic.get_symbol(relocation["r_info_sym"]).name + "@plt"
        self.cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        self.cs.detail = True

    def read(self, address, size):
        for segment in self.elf.iter_segments():
            start = segment["p_vaddr"]
            if segment["p_type"] == "PT_LOAD" and start <= address < start + segment["p_filesz"]:
                offset = address - start + segment["p_offset"]
                return self.data[offset:offset + min(size, start + segment["p_filesz"] - address)]
        return b""

    def label(self, address):
        if address in self.names:
            return self.names[address]
        raw = self.read(address, 180).split(b"\0", 1)[0]
        # 仅自动显示 API 名称、参数名及普通错误文案，不转储其他数据。
        if raw and all(32 <= c < 127 for c in raw):
            s = raw.decode("ascii")
            if re.match(r"(?:/v1/|[A-Z][a-zA-Z0-9_]{2,40}$|client_id$|[Pp]arameters?$|[Cc]lient|[Hh]eartbeat|[Ff]irmware|[Ll]ens|[Aa]ctive|[Rr]ead|[Ww]rite|[Pp]hocus|[Vv]alue|[Uu]nit)", s):
                return repr(s)
        return ""

    def dump(self, symbol, brief=False):
        start, size = symbol["st_value"], symbol["st_size"]
        print(f"\n{start:#x} size={size} {symbol.name}")
        registers = {}
        for ins in self.cs.disasm(self.read(start, size), start):
            comment = ""
            ops = ins.operands
            if ins.mnemonic in ("adrp", "adr"):
                registers[ops[0].reg] = ops[1].imm
                comment = self.label(ops[1].imm)
            elif ins.mnemonic == "add" and len(ops) == 3 and ops[2].type == 2:
                if ops[1].reg in registers:
                    value = registers[ops[1].reg] + ops[2].imm
                    registers[ops[0].reg] = value
                    comment = self.label(value)
            elif ins.mnemonic in ("bl", "b") and ops and ops[0].type == 2:
                comment = self.names.get(ops[0].imm, "")
                if ins.mnemonic == "bl":
                    registers = {r: v for r, v in registers.items() if self.cs.reg_name(r) not in [f"x{i}" for i in range(19)]}
            if not brief or comment and (not comment.startswith("_ZN1Q") and not comment.startswith("_ZN9Q")):
                print(f"{ins.address:08x}  {ins.mnemonic:8} {ins.op_str:32} {comment}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern")
    parser.add_argument("--dump", action="store_true")
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--binary", choices=HASHES, default="phocus")
    args = parser.parse_args()
    binary = Binary(args.binary)
    seen = set()
    for symbol in binary.symbols:
        if args.dump and symbol["st_info"]["type"] != "STT_FUNC":
            continue
        if re.search(args.pattern, symbol.name) and symbol["st_value"] not in seen:
            seen.add(symbol["st_value"])
            if args.dump:
                binary.dump(symbol, args.brief)
            else:
                print(hex(symbol["st_value"]), symbol["st_size"], symbol.name)
