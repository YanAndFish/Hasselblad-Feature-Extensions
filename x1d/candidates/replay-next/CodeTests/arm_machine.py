"""执行候选与选定原 Qt/codec ARM 函数；未声明的外部调用一律拒绝。

这里没有 Linux、事件循环、DBus 或 GPU。内存、同步和明确列出的宿主边界是替身。
所有输入都是测试生成的字节，不读取相机或用户照片。
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parents[1]
X1D = HERE.parents[1]
sys.path.insert(0, str(X1D / "tools"))
from binary import ArmElf
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as R

NATIVE = 0x01000000
TURBO = 0x40000000
HEAP = 0x20000000
SHIM = 0x60000000
STACK = 0x700F0000
STOP = 0x700FF000
REGS = [R.UC_ARM_REG_R0, R.UC_ARM_REG_R1, R.UC_ARM_REG_R2, R.UC_ARM_REG_R3]
SAVED = [getattr(R, "UC_ARM_REG_R" + str(i)) for i in range(4, 12)]


class ArmMachine:
    def __init__(self, module="jpeg", version="next", qt_gui=False, force_neon=False):
        self.force_neon = force_neon
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(HEAP, 0x18000000)
        self.uc.mem_map(SHIM, 0x100000)
        self.uc.mem_map(0x70000000, 0x100000)
        self.uc.reg_write(R.UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.uc.reg_write(R.UC_ARM_REG_FPEXC, 0x40000000)
        filename = "libx1d-jpeg-adapter.so" if module == "jpeg" else "libx1d-replay-provider.so"
        self.native = ArmElf((HERE / "artifacts/adapter" / filename).read_bytes())
        self.modules = [(self.native, NATIVE, "candidate")]
        for part in (["Core", "Gui", "Quick"] if qt_gui else ["Core"]):
            self.modules.append((ArmElf.load("usr/lib/libQt5" + part + ".so.5.5.1"), 0, "Qt" + part))
        self.modules.append((ArmElf.load("usr/lib/libturbojpeg.so.0.1.0"), TURBO, "TurboJPEG"))
        self.symbols = {}
        self.native_symbols = {}
        self.module_hashes = {}
        for elf, bias, name in self.modules:
            self.module_hashes[name] = hashlib.sha256(elf.data).hexdigest()
            for s in elf.symbols:
                if s.name and s["st_shndx"] != "SHN_UNDEF" and s["st_value"]:
                    self.symbols.setdefault(s.name, bias + s["st_value"])
                    if elf is self.native: self.native_symbols[s.name] = bias + s["st_value"]
            loads = [p for p in elf.elf.iter_segments() if p["p_type"] == "PT_LOAD"]
            lo = min(p["p_vaddr"] for p in loads) & ~0xFFF
            hi = (max(p["p_vaddr"] + p["p_memsz"] for p in loads) + 4095) & ~0xFFF
            self.uc.mem_map(bias + lo, hi - lo)
            for p in loads: self.uc.mem_write(bias + p["p_vaddr"], p.data())
        self.imports = {}
        self.callbacks = {}
        self.entries = {}
        self.calls = {}
        self.heap_next = HEAP
        self.live = {}
        self.free_blocks = []
        self.peak = self.current = 0
        self.fail_alloc_size = 0
        self.jumps = {}
        self.writes = []
        self.failed_watchers = []
        self.deferred = []
        self.permits = 1
        self.permit_releases = 0
        self.permit_acquires = 0
        self.last_calls = []
        self.environment_one = self.allocate(16)
        self.uc.mem_write(self.environment_one, b"1\0")
        self.stderr = self.allocate(16)
        self.put(self.stderr, self.allocate(16))
        for elf, bias, _ in self.modules: self.relocate(elf, bias)
        self.uc.hook_add(UC_HOOK_CODE, self.shim, begin=SHIM, end=SHIM + 0xFFFFF)
        self.bind("_ZN3X1D14runtimeMatchesEPKc", lambda: self.ret(1))
        self.bind("_ZN3X1D16invalidateRecordERK7QString", lambda: self.ret())
        names = ["tjInitDecompress", "tjInitCompress", "tjDestroy", "tjAlloc", "tjFree", "tjDecompressHeader3",
                 "tjGetScalingFactors", "tjDecompress2", "tjBufSize", "tjCompress2"]
        self.codec_table = self.allocate(48)
        self.uc.mem_write(self.codec_table, struct.pack("<12I", 48, 1, *[self.symbols[n] for n in names]))
        self.bind("_ZN3X1D5codecEv", lambda: self.ret(self.codec_table))
        self.bind("_ZN3X1D8readFileERK7QStringyiPb", self.no_file)
        for name in ("_ZN10QSemaphoreC1Ei", "_ZN10QSemaphoreC2Ei", "_ZN10QSemaphoreD1Ev", "_ZN10QSemaphoreD2Ev",
                     "_ZN20QQuickTextureFactoryC1Ev", "_ZN20QQuickTextureFactoryC2Ev",
                     "_ZN20QQuickTextureFactoryD1Ev", "_ZN20QQuickTextureFactoryD2Ev"):
            self.bind(name, lambda: self.ret(self.arg(0)))
        self.bind("_ZN10QSemaphore10tryAcquireEi", self.acquire)
        self.bind("_ZN10QSemaphore7releaseEi", self.release_permit)
        self.original_write = self.callback("original-write", self.write)
        self.original_image = self.callback("original-image", lambda: self.ret(0))
        self.init_native()

    def allocate(self, size, zero=False):
        size = max(size, 1)
        assert size <= 204 * 1024 * 1024, "超出本离线用例分配上限"
        if self.fail_alloc_size and size == self.fail_alloc_size: return 0
        found = next(((i, p, n) for i, (p, n) in enumerate(self.free_blocks) if n >= size), None)
        if found:
            i, at, reserved = found
            del self.free_blocks[i]
        else:
            reserved = (size + 15) & ~15
            at = self.heap_next
            self.heap_next += reserved
            assert self.heap_next < HEAP + 0x18000000
        self.live[at] = (size, reserved)
        self.current += size
        self.peak = max(self.peak, self.current)
        self.uc.mem_write(at, (b"\0" if zero else b"\xcd") * size)
        return at

    def acquire(self):
        assert self.arg(1) == 1
        acquired = self.permits > 0
        if acquired:
            self.permits -= 1
            self.permit_acquires += 1
        self.ret(acquired)

    def release_permit(self):
        assert self.arg(1) == 1 and self.permits == 0
        self.permits += 1
        self.permit_releases += 1
        self.ret()

    def free(self, at):
        if not at: return
        used, reserved = self.live.pop(at)
        self.current -= used
        self.free_blocks.append((at, reserved))

    def put(self, at, value): self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))
    def word(self, at): return struct.unpack("<I", self.uc.mem_read(at, 4))[0]
    def arg(self, n):
        return self.uc.reg_read(REGS[n]) if n < 4 else self.word(self.uc.reg_read(R.UC_ARM_REG_SP) + 4 * (n - 4))
    def ret(self, value=0):
        self.uc.reg_write(R.UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(R.UC_ARM_REG_PC, self.uc.reg_read(R.UC_ARM_REG_LR))

    def cstring(self, at, limit=256):
        out = bytearray()
        for _ in range(limit):
            byte = self.uc.mem_read(at + len(out), 1)[0]
            if byte == 0: return out.decode("ascii")
            out.append(byte)
        raise AssertionError("未声明的长字符串")

    def stub(self, name):
        if name in self.imports: return self.imports[name]
        at = SHIM + 16 * len(self.imports)
        assert at < SHIM + 0xF0000
        self.imports[name] = at
        self.entries[at] = name
        return at

    def callback(self, name, callback):
        self.callbacks[name] = callback
        return self.stub(name)

    def bind(self, name, callback):
        if name not in self.symbols: return
        self.callbacks[name] = callback
        address = self.symbols[name]
        def handler(uc, at, size, user):
            self.calls[name] = self.calls.get(name, 0) + 1
            callback()
        self.uc.hook_add(UC_HOOK_CODE, handler, begin=address, end=address)

    def relocate(self, elf, bias):
        for section in elf.sections:
            if section["sh_type"] != "SHT_REL": continue
            table = elf.elf.get_section(section["sh_link"])
            for r in section.iter_relocations():
                at = bias + r["r_offset"]
                kind = r["r_info_type"]
                if kind == 23:
                    self.put(at, bias + self.word(at)); continue
                s = table.get_symbol(r["r_info_sym"])
                if s["st_shndx"] != "SHN_UNDEF": value = bias + s["st_value"]
                elif s.name in self.symbols: value = self.symbols[s.name]
                elif s.name == "stderr": value = self.stderr
                elif s["st_info"]["bind"] == "STB_WEAK": value = 0
                else: value = self.stub(s.name)
                if kind == 2: value += self.word(at)
                elif kind not in (21, 22): raise AssertionError((kind, s.name))
                self.put(at, value)

    def init_native(self):
        section = self.native.elf.get_section_by_name(".init_array")
        if section:
            for at in range(NATIVE + section["sh_addr"], NATIVE + section["sh_addr"] + section["sh_size"], 4):
                self.call(self.word(at), [])

    def call(self, address, args, stop=STOP, budget=2_000_000_000):
        if isinstance(address, str): address = self.symbols[address]
        for i, reg in enumerate(SAVED): self.uc.reg_write(reg, 0x1000 + i)
        for reg, value in zip(REGS, args): self.uc.reg_write(reg, value & 0xFFFFFFFF)
        for i, value in enumerate(args[4:]): self.put(STACK + 4 * i, value)
        self.uc.reg_write(R.UC_ARM_REG_SP, STACK)
        self.uc.reg_write(R.UC_ARM_REG_LR, stop)
        try: self.uc.emu_start(address, stop, count=budget)
        except Exception as error:
            raise AssertionError(f"ARM PC={self.uc.reg_read(R.UC_ARM_REG_PC):#x}; 最后边界={self.last_calls}") from error
        assert self.uc.reg_read(R.UC_ARM_REG_PC) == stop, f"ARM 指令预算耗尽，PC={self.uc.reg_read(R.UC_ARM_REG_PC):#x}"
        assert self.uc.reg_read(R.UC_ARM_REG_SP) == STACK, "栈未恢复"
        assert [self.uc.reg_read(reg) for reg in SAVED] == list(range(0x1000, 0x1008)), "callee-saved 未恢复"
        return self.uc.reg_read(R.UC_ARM_REG_R0)

    def array(self, obj):
        d = self.word(obj)
        return bytes(self.uc.mem_read(d + self.word(d + 12), self.word(d + 4)))

    def string(self, obj):
        d = self.word(obj)
        return bytes(self.uc.mem_read(d + self.word(d + 12), 2 * self.word(d + 4))).decode("utf-16le")

    def byte_array(self, data):
        source = self.allocate(len(data) + 1)
        self.uc.mem_write(source, data + b"\0")
        obj = self.allocate(4)
        self.call("_ZN10QByteArrayC1EPKci", [obj, source, len(data)])
        self.free(source)
        return obj

    def qstring(self, text):
        data = text.encode("utf-8")
        src = self.allocate(len(data) + 1)
        self.uc.mem_write(src, data + b"\0")
        obj = self.allocate(4)
        self.call("_ZN7QString15fromUtf8_helperEPKci", [obj, src, len(data)])
        self.free(src)
        return obj

    def no_file(self):
        # QByteArray 隐藏返回指针、QString、quint64、int、bool*。
        self.uc.mem_write(self.arg(5), b"\0")
        self.put(self.arg(0), self.symbols["_ZN10QArrayData11shared_nullE"])
        self.ret(self.arg(0))

    def write(self):
        assert self.arg(2) == 0 and self.arg(3) == 0
        self.writes.append((self.string(self.arg(4)), self.array(self.arg(1))))
        self.ret(0)

    def shim(self, uc, at, size, context):
        name = self.entries[at]
        self.last_calls = (self.last_calls + [name])[-12:]
        self.calls[name] = self.calls.get(name, 0) + 1
        if name in self.callbacks:
            self.callbacks[name](); return
        a, b, c = self.arg(0), self.arg(1), self.arg(2)
        if name in ("malloc", "_Znwj", "_Znaj"): self.ret(self.allocate(a))
        elif name == "calloc": self.ret(self.allocate(a * b, True))
        elif name in ("free", "_ZdlPv", "_ZdaPv"): self.free(a); self.ret()
        elif name in ("memcpy", "memmove"):
            self.uc.mem_write(a, bytes(self.uc.mem_read(b, c))); self.ret(a)
        elif name == "memset": self.uc.mem_write(a, bytes([b & 255]) * c); self.ret(a)
        elif name in ("memcmp", "bcmp"):
            x, y = bytes(self.uc.mem_read(a, c)), bytes(self.uc.mem_read(b, c))
            self.ret((x > y) - (x < y))
        elif name == "strlen": self.ret(len(self.cstring(a)))
        elif name == "__cxa_guard_acquire": self.ret(int(self.word(a) == 0))
        elif name == "__cxa_guard_release": self.put(a, 1); self.ret()
        elif name in ("__cxa_atexit", "__aeabi_atexit", "__cxa_finalize"): self.ret()
        elif name == "__aeabi_uidiv": self.ret(a // b)
        elif name == "__aeabi_uidivmod":
            self.ret(a // b); uc.reg_write(R.UC_ARM_REG_R1, a % b)
        elif name == "getenv":
            key = self.cstring(a)
            assert key in {"X1D_REPLAY_SESSION", "JSIMD_FORCENONE", "JSIMD_FORCENEON", "JPEGMEM", "TJ_OPTIMIZE", "TJ_ARITHMETIC", "TJ_PROGRESSIVE", "TJ_RESTART"}
            wanted = "JSIMD_FORCENEON" if self.force_neon else "JSIMD_FORCENONE"
            self.ret(self.environment_one if key == wanted else 0)
        elif name == "_setjmp":
            regs = SAVED + [R.UC_ARM_REG_SP, R.UC_ARM_REG_LR] + [getattr(R, "UC_ARM_REG_D" + str(i)) for i in range(8, 16)]
            self.jumps[a] = {reg: uc.reg_read(reg) for reg in regs}; self.ret()
        elif name == "longjmp":
            for reg, value in self.jumps[a].items(): uc.reg_write(reg, value)
            self.ret(b or 1)
        elif name in ("sprintf", "snprintf"):
            self.uc.mem_write(a, b"codec-error\0"); self.ret(11)
        elif name in ("fprintf", "fwrite"): self.ret()
        elif name == "dlsym":
            symbol = self.cstring(b)
            if symbol == "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString": self.ret(self.original_write)
            elif symbol == "_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile": self.ret(self.original_image)
            else: raise AssertionError("未声明 dlsym：" + symbol)
        elif name == "_ZN10QDBusErrorC1ENS_9ErrorTypeERK7QString": self.ret(a)
        elif name == "_ZN10QDBusErrorD1Ev": self.ret()
        elif name == "_ZN16QDBusPendingCall9fromErrorERK10QDBusError": self.put(a, 0); self.ret(a)
        elif name == "_ZN16QDBusPendingCallD1Ev": self.ret()
        elif name == "_ZN23QDBusPendingCallWatcherC1ERK16QDBusPendingCallP7QObject":
            self.failed_watchers.append(a); self.ret(a)
        elif name == "_ZN7QObject11deleteLaterEv": self.deferred.append(a); self.ret()
        else: raise AssertionError("离线边界拒绝未声明调用：" + name)
