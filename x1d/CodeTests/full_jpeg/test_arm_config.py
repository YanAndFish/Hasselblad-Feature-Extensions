"""实际 ARM 构造和 setter 控制流；以有界 Qt 替身核对板型与旧配置加载。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

X1D = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(X1D / "tools"))
from binary import ArmElf
from patch_full_jpeg import build, SOURCE_SHA
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

OBJ = 0x60000100
STACK = 0x700E0000
STOP = 0x700FF000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
SAVED = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
EVIDENCE = []


class ArmConfig:
    def __init__(self, data: bytes, product: int):
        self.elf = ArmElf(data)
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0x10000, 0x50000)
        for segment in self.elf.elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                self.uc.mem_write(segment["p_vaddr"], segment.data())
        self.uc.mem_map(0x60000000, 0x100000)
        self.uc.mem_map(0x70000000, 0x100000)
        self.product = product
        self.heap = 0x60001000
        self.changed = 0
        self.rejected = 0
        self.stopped = False
        self.lookups = []
        self.hooks = {
            0x24210: lambda: self.ret(self.reg(0)),  # QObject 部分；不读取设备
            0x14D1C: lambda: self.ret(product),
            0x14DDC: self.from_ascii,
            0x14AE8: self.variant_int,
            0x14DAC: lambda: self.ret(0),
            0x15214: lambda: self.ret(self.word(self.reg(0) + 8) & 0x3FFFFFFF),
            0x14C68: self.to_int,
            0x14ECC: self.to_long_long,
            0x14BD8: self.arg_string,
            0x14CC8: self.arg_number,
            0x14B24: self.local_bytes,
            0x14F50: self.property,
            0x228BC: lambda: self.ret(0x600F0000),
            0x223C0: self.special_value,
            0x24314: self.notify_changed,
            0x23F68: lambda: self.ret(0),
            0x255AC: self.reject,
        }
        plt = self.elf.elf.get_section_by_name(".plt")
        self.plt_bounds = (plt["sh_addr"], plt["sh_addr"] + plt["sh_size"])
        self.uc.hook_add(UC_HOOK_CODE, self.step)

    def put(self, at, value):
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def word(self, at):
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def reg(self, index):
        return self.uc.reg_read(REGS[index])

    def ret(self, value=0):
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def alloc(self, size):
        at = self.heap
        self.heap += (size + 15) & ~15
        assert self.heap < 0x600E0000
        return at

    def array(self, data, length):
        at = self.alloc(18 + len(data))
        self.uc.mem_write(at, struct.pack("<iIII", -1, length, 0, 16) + data + b"\0\0")
        return at

    def string(self, obj):
        d = self.word(obj)
        return bytes(self.uc.mem_read(d + self.word(d + 12), self.word(d + 4) * 2)).decode("utf-16le")

    def set_string(self, obj, text):
        self.put(obj, self.array(text.encode("utf-16le"), len(text)))

    def c_string(self, at):
        out = bytearray()
        while len(out) < 1024:
            value = self.uc.mem_read(at + len(out), 1)[0]
            if not value:
                return out.decode("ascii")
            out.append(value)
        raise AssertionError("替身字符串超出边界")

    def from_ascii(self):
        text = bytes(self.uc.mem_read(self.reg(0), self.reg(1))).decode("ascii")
        self.ret(self.array(text.encode("utf-16le"), len(text)))

    def variant(self, obj, value):
        self.uc.mem_write(obj, struct.pack("<qII", value, 2, 0))

    def variant_int(self):
        value = self.reg(1)
        self.variant(self.reg(0), value if value < 0x80000000 else value - 0x100000000)
        self.ret(self.reg(0))

    def to_int(self):
        if self.reg(1):
            self.uc.mem_write(self.reg(1), b"\x01")
        self.ret(self.word(self.reg(0)))

    def to_long_long(self):
        obj = self.reg(0)
        if self.reg(1):
            self.uc.mem_write(self.reg(1), b"\x01")
        self.uc.reg_write(UC_ARM_REG_R1, self.word(obj + 4))
        self.ret(self.word(obj))

    def arg_string(self):
        obj = self.reg(0)
        result = self.string(self.reg(1)).replace("%1", self.string(self.reg(2)), 1)
        self.set_string(obj, result)
        self.ret(obj)

    def arg_number(self):
        obj = self.reg(0)
        # 拒绝分支的文本仅为 Qt 格式化替身，不参与范围判断。
        self.set_string(obj, self.string(self.reg(1)))
        self.ret(obj)

    def local_bytes(self):
        obj = self.reg(0)
        raw = bytes(self.uc.mem_read(self.reg(1), 2 * self.reg(2))).decode("utf-16le").encode("ascii")
        self.put(obj, self.array(raw, len(raw)))
        self.ret(obj)

    def property(self):
        obj, target, name = self.reg(0), self.reg(1), self.c_string(self.reg(2))
        assert target == OBJ
        offsets = {"jpg_size_minval": 0x430, "jpg_size_maxval": 0x434}
        assert name in offsets, name
        self.lookups.append(name)
        self.variant(obj, self.word(target + offsets[name]))
        self.ret(obj)

    def special_value(self):
        # 原特殊值表构造函数仅插入 SV=0x7ffe，静态契约在单独测试中核对。
        assert self.string(self.reg(1)) == "jpg_size"
        self.ret(0)

    def notify_changed(self):
        assert self.reg(0) == OBJ and self.string(self.reg(1)) == "jpg_size"
        self.changed += 1
        self.ret(0)

    def reject(self):
        self.rejected += 1
        self.ret(0)

    def step(self, uc, at, size, _):
        if at == STOP:
            self.stopped = True
            uc.emu_stop()
        elif at in self.hooks:
            self.hooks[at]()
        elif self.plt_bounds[0] <= at < self.plt_bounds[1]:
            raise AssertionError(f"未建模的外部调用 {at:#x} {self.elf.name(at)}")

    def run(self, start, args):
        before = [0x100 + i for i in range(8)]
        for reg, value in zip(SAVED, before):
            self.uc.reg_write(reg, value)
        for reg, value in zip(REGS, args):
            self.uc.reg_write(reg, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_SP, STACK)
        self.uc.reg_write(UC_ARM_REG_LR, STOP)
        self.stopped = False
        self.uc.emu_start(start, STOP + 4, count=30000)
        assert self.stopped
        assert self.uc.reg_read(UC_ARM_REG_SP) == STACK
        assert [self.uc.reg_read(reg) for reg in SAVED] == before
        return self.reg(0)

    def construct(self):
        assert self.run(0x23570, [OBJ, 0]) == OBJ
        return bytes(self.uc.mem_read(OBJ, 0x694))

    def set_jpg(self, value):
        name = self.alloc(4)
        self.set_string(name, "jpg_size")
        self.run(0x244E4, [OBJ, value, OBJ + 0x42C, name])


class FullJpegConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = ArmElf.load("usr/bin/configstore").data
        cls.candidate, cls.report = build(cls.original)

    def test_ctor_only_changes_three_wedge_fields(self):
        for product in (0, 1, 2, 3, 4, 255):
            with self.subTest(product=product):
                original = ArmConfig(self.original, product)
                candidate = ArmConfig(self.candidate, product)
                old, new = original.construct(), candidate.construct()
                expected = bytearray(old)
                if product == 2:
                    struct.pack_into("<3I", expected, 0x42C, 2, 2, 2)
                self.assertEqual(new, expected)
                EVIDENCE.append({"case": "constructor", "productId": product,
                                 "jpgSizeMinMax": list(struct.unpack_from("<3I", new, 0x42C)),
                                 "otherConfigBytesEqual": True, "abiPreserved": True})

    def test_old_quarter_and_invalid_values_do_not_replace_full(self):
        for value in (-1, 0, 1, 2, 3, 32):
            with self.subTest(value=value):
                machine = ArmConfig(self.candidate, 2)
                machine.construct()
                machine.set_jpg(value)
                self.assertEqual(machine.word(OBJ + 0x42C), 2)
                self.assertEqual(machine.changed, 0)
                self.assertEqual(machine.rejected, int(value != 2))
                if value != 2:
                    self.assertEqual(machine.lookups, ["jpg_size_minval", "jpg_size_maxval"])
                EVIDENCE.append({"case": "wedge_property_load", "input": value,
                                 "effective": 2, "rejected": value != 2, "abiPreserved": True})

    def test_other_board_setter_behavior_unchanged(self):
        for product in (1, 3, 4):
            for value in (1, 2, 3, 4):
                results = []
                for data in (self.original, self.candidate):
                    machine = ArmConfig(data, product)
                    machine.construct()
                    machine.set_jpg(value)
                    results.append((machine.word(OBJ + 0x42C), machine.changed, machine.rejected))
                self.assertEqual(results[0], results[1])
                EVIDENCE.append({"case": "other_product_property", "productId": product,
                                 "input": value, "sameAsBaseline": True})

    def test_original_accepts_quarter_candidate_rejects_it(self):
        for data, expected, rejected in [(self.original, 1, 0), (self.candidate, 2, 1)]:
            machine = ArmConfig(data, 2)
            machine.construct()
            machine.set_jpg(2)
            machine.set_jpg(1)
            self.assertEqual(machine.word(OBJ + 0x42C), expected)
            self.assertEqual(machine.rejected, rejected)

    def test_static_contracts_and_hash_guard(self):
        original, candidate = ArmElf(self.original), ArmElf(self.candidate)
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), SOURCE_SHA)
        # 原例外值表只有 SV 名称；jpg_size 进入原有 min/max 校验。
        self.assertEqual(original.read(0x22478 + original.word(0x228A8), 2), b"SV")
        props = {p["name"]: p for p in original.meta_object("_ZN6config16staticMetaObjectE")["properties"]}
        self.assertTrue(props["jpg_size"]["flags"] & 2)
        self.assertFalse(props["jpg_size_minval"]["flags"] & 2)
        self.assertFalse(props["jpg_size_maxval"]["flags"] & 2)
        for at in (0x18F58, 0x19C7C, 0x1A910, 0x1B014):
            self.assertEqual(list(original.direct_calls(at, 4))[0][2], "_ZN7QObject11setPropertyEPKcRK8QVariant")
        for name in (".ARM.exidx", ".ARM.extab", ".dynamic", ".dynsym", ".dynstr", ".rel.dyn", ".rel.plt"):
            self.assertEqual(original.elf.get_section_by_name(name).data(), candidate.elf.get_section_by_name(name).data())
        with self.assertRaises(ValueError):
            build(self.candidate)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FullJpegConfigTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        output = X1D / "research/validation/full-jpeg-config-arm.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "firmware": "X1D-50c 1.25.0", "sourceSha256": SOURCE_SHA,
            "candidateSha256": FullJpegConfigTests.report["candidateSha256"],
            "passed": True, "testMethods": result.testsRun, "scenarios": EVIDENCE,
            "limits": ["执行实际 ARM 构造和 setter，Qt 对象及设备板号为替身",
                       "旧配置通过同一个 setter 的效果已测；未启动 SQL 数据库或真实 configstore 服务",
                       "未编码实际 Full 图像，未连接或修改相机"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
