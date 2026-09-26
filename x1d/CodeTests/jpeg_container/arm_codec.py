"""在 ARM 仿真中运行原包 TurboJPEG；只有 libc 内存/错误函数使用有界替身。"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

X1D = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(X1D / "tools"))
from binary import ArmElf
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as R

CORE = X1D / "artifacts" / "jpeg-container-v1" / "libx1d-jpeg-container.so"
LIBRARY = "usr/lib/libturbojpeg.so.0.1.0"
TBASE = 0x40000000
SHIM = 0x50000000
HEAP = 0x30000000
HEAP_BYTES = 0x2000000
DATA = 0x10000000
STACK = 0x200F0000
STOP = 0x200FF000


class ArmCodec:
    def __init__(self, fail_allocation=0, fail_allocation_size=0):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.core = ArmElf(CORE.read_bytes())
        self.codec = ArmElf.load(LIBRARY)
        self.codec_sha = hashlib.sha256(self.codec.data).hexdigest()
        self.uc.mem_map(0, 0x80000)
        self.uc.mem_map(TBASE, 0x80000)
        self.uc.mem_map(SHIM, 0x10000)
        self.uc.mem_map(HEAP, HEAP_BYTES)
        self.uc.mem_map(DATA, 0x1400000)
        self.uc.mem_map(0x20000000, 0x100000)
        self.uc.reg_write(R.UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.uc.reg_write(R.UC_ARM_REG_FPEXC, 0x40000000)
        self.uc.mem_write(SHIM + 0x8000, b"1\0")
        self.uc.mem_write(SHIM + 0x8100, struct.pack("<I", SHIM + 0x8200))
        self.imports = {}
        self.jumps = {}
        self.heap_next = HEAP
        self.live = {}
        self.free_blocks = []
        self.peak = self.maximum_allocation = self.allocation_count = 0
        self.current = 0
        self.fail_allocation = fail_allocation
        self.fail_allocation_size = fail_allocation_size
        self.calls = {}
        self.allowed = {"malloc", "calloc", "free", "memcpy", "memset", "getenv", "_setjmp", "longjmp",
                        "sprintf", "snprintf", "fprintf", "fwrite", "__cxa_finalize"}
        self.load(self.core, 0)
        self.load(self.codec, TBASE)
        self.exports = {s.name: s["st_value"] for s in self.core.symbols if s["st_value"] and s.name.startswith("xj_")}
        self.tj = {s.name: TBASE + s["st_value"] for s in self.codec.symbols if s["st_value"] and s.name.startswith("tj")}
        self.uc.hook_add(UC_HOOK_CODE, self.shim, begin=SHIM, end=SHIM + 0x7000)
        names = ["tjInitDecompress", "tjInitCompress", "tjDestroy", "tjAlloc", "tjFree", "tjDecompressHeader3",
                 "tjGetScalingFactors", "tjDecompress2", "tjBufSize", "tjCompress2"]
        self.uc.mem_write(DATA + 0xE00000, struct.pack("<12I", 48, 1, *[self.tj[n] for n in names]))

    def load(self, elf, base):
        for segment in elf.elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                self.uc.mem_write(base + segment["p_vaddr"], segment.data())
        for section in elf.sections:
            if section["sh_type"] != "SHT_REL":
                continue
            symbols = elf.elf.get_section(section["sh_link"])
            for rel in section.iter_relocations():
                at = base + rel["r_offset"]
                kind = rel["r_info_type"]
                if kind == 23:  # R_ARM_RELATIVE
                    self.put(at, base + self.word(at))
                    continue
                symbol = symbols.get_symbol(rel["r_info_sym"])
                if symbol["st_shndx"] != "SHN_UNDEF":
                    value = base + symbol["st_value"]
                elif symbol.name == "stderr":
                    value = SHIM + 0x8100
                elif symbol["st_info"]["bind"] == "STB_WEAK":
                    value = 0
                else:
                    previous = next((p for p, name in self.imports.items() if name == symbol.name), None)
                    value = previous if previous is not None else SHIM + len(self.imports) * 0x100
                    self.imports[value] = symbol.name
                if kind == 2: value += self.word(at)  # R_ARM_ABS32
                elif kind not in (21, 22): raise AssertionError(("unhandled relocation", kind, symbol.name))
                self.put(at, value)

    def put(self, at, value):
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def word(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def arg(self, number):
        if number < 4: return self.uc.reg_read([R.UC_ARM_REG_R0, R.UC_ARM_REG_R1, R.UC_ARM_REG_R2, R.UC_ARM_REG_R3][number])
        return self.word(self.uc.reg_read(R.UC_ARM_REG_SP) + (number - 4) * 4)

    def ret(self, value=0):
        self.uc.reg_write(R.UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(R.UC_ARM_REG_PC, self.uc.reg_read(R.UC_ARM_REG_LR))

    def allocate(self, size, zero=False):
        self.allocation_count += 1
        if self.fail_allocation == self.allocation_count or size == self.fail_allocation_size: return 0
        size = max(size, 1)
        assert size <= 2044 * 1532 * 3, "仿真拒绝超过 1/4 DCT 缩放图的单次 RGB 分配"
        choice = next(((i, p, n) for i, (p, n) in enumerate(self.free_blocks) if n >= size), None)
        if choice:
            i, at, reserved = choice
            del self.free_blocks[i]
        else:
            reserved = (size + 15) & ~15
            at = self.heap_next
            self.heap_next += reserved
            assert self.heap_next < HEAP + HEAP_BYTES
        self.live[at] = (size, reserved)
        self.current += size
        self.peak = max(self.peak, self.current)
        self.maximum_allocation = max(self.maximum_allocation, size)
        self.uc.mem_write(at, bytes(size) if zero else b"\xcd" * size)
        return at

    def cstring(self, at):
        result = bytearray()
        for _ in range(128):
            c = self.uc.mem_read(at + len(result), 1)[0]
            if c == 0: return result.decode("ascii")
            result.append(c)
        raise AssertionError("未预期的长环境变量名称")

    def shim(self, uc, at, size, context):
        name = self.imports.get(at)
        assert name in self.allowed, "离线仿真拒绝未声明 libc 调用：" + str(name)
        self.calls[name] = self.calls.get(name, 0) + 1
        a, b, c = self.arg(0), self.arg(1), self.arg(2)
        if name == "malloc": self.ret(self.allocate(a))
        elif name == "calloc": self.ret(self.allocate(a * b, True))
        elif name == "free":
            if a:
                used, reserved = self.live.pop(a)
                self.current -= used
                self.free_blocks.append((a, reserved))
            self.ret()
        elif name == "memcpy":
            assert c < 8 * 1024 * 1024
            self.uc.mem_write(a, bytes(self.uc.mem_read(b, c)))
            self.ret(a)
        elif name == "memset":
            assert c < 8 * 1024 * 1024
            self.uc.mem_write(a, bytes([b & 255]) * c)
            self.ret(a)
        elif name == "getenv":
            key = self.cstring(a)
            assert key in {"JSIMD_FORCENONE", "JSIMD_FORCENEON", "JPEGMEM", "TJ_OPTIMIZE",
                           "TJ_ARITHMETIC", "TJ_PROGRESSIVE", "TJ_RESTART"}, key
            self.ret(SHIM + 0x8000 if key == "JSIMD_FORCENONE" else 0)
        elif name == "_setjmp":
            regs = [getattr(R, "UC_ARM_REG_R" + str(i)) for i in range(4, 12)]
            regs += [R.UC_ARM_REG_SP, R.UC_ARM_REG_LR]
            regs += [getattr(R, "UC_ARM_REG_D" + str(i)) for i in range(8, 16)]
            self.jumps[a] = {reg: uc.reg_read(reg) for reg in regs}
            self.ret()
        elif name == "longjmp":
            for reg, value in self.jumps[a].items(): uc.reg_write(reg, value)
            self.ret(b or 1)
        elif name in ("sprintf", "snprintf"):
            content = b"codec-error\0"
            if name == "snprintf": content = content[:max(0, b - 1)] + (b"\0" if b else b"")
            self.uc.mem_write(a, content)
            self.ret(len(content) - 1)
        else:
            # 库内部错误日志不输出，避免引入任意字符串或 I/O。
            self.ret()

    def generate(self, source, capacity=3 * 1024 * 1024):
        assert len(source) < 0xD00000
        self.uc.mem_write(DATA, source)
        self.uc.mem_write(DATA + 0x1000000, b"\xa5" * (3 * 1024 * 1024))
        args = [DATA, len(source), DATA + 0x1000000, capacity, DATA + 0xE00100, DATA + 0xE00000]
        for register, value in zip([R.UC_ARM_REG_R0, R.UC_ARM_REG_R1, R.UC_ARM_REG_R2, R.UC_ARM_REG_R3], args):
            self.uc.reg_write(register, value)
        self.put(STACK, args[4]); self.put(STACK + 4, args[5])
        self.uc.reg_write(R.UC_ARM_REG_SP, STACK)
        self.uc.reg_write(R.UC_ARM_REG_LR, STOP)
        self.uc.emu_start(self.exports["xj_make_preview"], STOP, count=2_000_000_000)
        assert self.uc.reg_read(R.UC_ARM_REG_PC) == STOP, "ARM 指令预算耗尽"
        assert self.uc.reg_read(R.UC_ARM_REG_SP) == STACK
        status = self.uc.reg_read(R.UC_ARM_REG_R0)
        fields = struct.unpack("<7I", self.uc.mem_read(DATA + 0xE00100, 28))
        stats = dict(zip(["bytes", "width", "height", "quality", "attempts", "decodedRgbBytes", "scratchBytes"], fields))
        stats.update({"codecAllocatedPeakBytes": self.peak, "maximumAllocationBytes": self.maximum_allocation,
                      "remainingAllocations": len(self.live), "codecSha256": self.codec_sha,
                      "simd": "portable C selected by bounded getenv replacement"})
        if status != 0:
            assert bytes(self.uc.mem_read(DATA + 0x1000000, 3 * 1024 * 1024)) == b"\xa5" * (3 * 1024 * 1024)
        return status, bytes(self.uc.mem_read(DATA + 0x1000000, stats["bytes"])), stats
