"""官方 Phocus PC 4.1.1 通信库的静态 PE 查看器；不载入或执行 DLL。"""
from pathlib import Path
import argparse
import bisect
import hashlib
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".research-cache/python"))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

SHA256 = "70b697d839378c58de086cb82b81ecefd2b1d723ea7361bcdaef0c8a04a6211a"


class PCBinary:
    def __init__(self):
        self.data = (ROOT / ".research-cache/phocus-pc-files/PhocusApi64.dll").read_bytes()
        if hashlib.sha256(self.data).hexdigest() != SHA256:
            raise ValueError("官方 PC DLL 哈希不匹配")
        self.pe = pefile.PE(data=self.data, fast_load=True)
        self.pe.parse_data_directories(directories=[0, 1, 3])
        if self.pe.FILE_HEADER.Machine != 0x8664:
            raise ValueError("仅支持固定 x64 研究对象")
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.names = {self.base + s.address: s.name.decode() for s in self.pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
        for lib in self.pe.DIRECTORY_ENTRY_IMPORT:
            for s in lib.imports:
                if s.name:
                    self.names[s.address] = s.name.decode() + "@" + lib.dll.decode()
        self.functions = sorted((self.base + e.struct.BeginAddress, self.base + e.struct.EndAddress) for e in self.pe.DIRECTORY_ENTRY_EXCEPTION)
        self.starts = [s for s, e in self.functions]
        self.cs = Cs(CS_ARCH_X86, CS_MODE_64)
        self.cs.skipdata = True

    def read(self, addr, length):
        return self.pe.get_data(addr - self.base, length)

    def function(self, addr):
        i = bisect.bisect_right(self.starts, addr) - 1
        if i >= 0 and addr < self.functions[i][1]:
            return self.functions[i]
        return None

    @staticmethod
    def rip_target(address, size, operands):
        m = re.search(r"\[rip (\+|-) (0x[0-9a-f]+)\]", operands)
        return address + size + int(m[2], 16) * (1 if m[1] == "+" else -1) if m else None

    def dump(self, addr, length=None):
        start, end = self.function(addr) or (addr, addr + (length or 128))
        if length:
            start, end = addr, addr + length
        print(f"function {start:#x}..{end:#x}")
        for a, z, m, o in self.cs.disasm_lite(self.read(start, end - start), start):
            target = self.rip_target(a, z, o)
            label = self.names.get(target, f"{target:#x}" if target else "")
            if m in ("call", "jmp") and o.startswith("0x"):
                label = self.names.get(int(o, 16), "")
            print(f"{a:012x} {m:8} {o:50} {label}")

    def xrefs(self, targets):
        results = []
        for section in self.pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            for a, z, m, o in self.cs.disasm_lite(section.get_data(), self.base + section.VirtualAddress):
                target = self.rip_target(a, z, o)
                if target in targets:
                    results.append((a, m, o, target, self.function(a)))
                elif m in ("call", "jmp") and o.startswith("0x") and int(o, 16) in targets:
                    results.append((a, m, o, int(o, 16), self.function(a)))
        return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("addresses", nargs="+", type=lambda x: int(x, 0))
    p.add_argument("--xrefs", action="store_true")
    p.add_argument("--length", type=lambda x: int(x, 0))
    args = p.parse_args()
    binary = PCBinary()
    if args.xrefs:
        for a, m, o, t, f in binary.xrefs(set(args.addresses)):
            print(hex(a), m, o, "target", hex(t), "function", tuple(hex(x) for x in f) if f else None)
    else:
        for address in args.addresses:
            binary.dump(address, args.length)
