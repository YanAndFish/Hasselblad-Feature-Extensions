"""只在 Unicorn 合成内存执行已编译 ARM 观察组件；没有设备或网络代码。"""
import io
import struct
import unittest
from pathlib import Path

import unicorn
from unicorn import arm_const as arm
from elftools.elf.elffile import ELFFile

ELF_PATH = Path(__file__).resolve().parents[1] / "build" / "farm-sensor-probe.elf"
OUT, STACK, RETURN = 0x02000000, 0x03000000, 0x04000000
TIMER, STATUS, SHADOW = 0xF8F00200, 0x42000014, 0x002B1990
CONFIG, REGISTERS = 0x6C1690, 0x6DB2E8
MAGIC, RECORD_SIZE = 0x32504647, 88


def execute(*, magic=MAGIC, armed=1, sequence=0, pointer=OUT,
            controls=(1,), highs=(7,), lows=(100,), repeat=False):
    elf = ELFFile(io.BytesIO(ELF_PATH.read_bytes()))
    code_parts = [(s["sh_addr"], s.data()) for s in elf.iter_sections() if s["sh_flags"] & 4 and s["sh_size"]]
    code_ranges = [(a, a + len(b)) for a, b in code_parts]
    symbols = elf.get_section_by_name(".symtab")
    entry = next((s["st_value"] for s in symbols.iter_symbols() if s.name == "farm_sensor_probe_after_start"),
                 elf.header["e_entry"]) if symbols else elf.header["e_entry"]
    assert any(a <= entry < b for a, b in code_ranges)
    machine = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
    code_pages = set()
    for a, b in code_ranges:
        code_pages.update(range(a & ~4095, (b + 4095) & ~4095, 4096))
    for page in sorted(code_pages):
        machine.mem_map(page, 4096)
    for address, code in code_parts:
        machine.mem_write(address, code)
    for page in code_pages:
        machine.mem_protect(page, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
    for address in (OUT, STACK, RETURN, TIMER & ~4095,
                    STATUS & ~4095, SHADOW & ~4095, CONFIG & ~4095, REGISTERS & ~4095):
        machine.mem_map(address, 4096)
    words = [magic, armed, sequence, 0] + [0xCCCCCCCC] * 18
    machine.mem_write(OUT, struct.pack("<22I", *words))
    machine.mem_write(SHADOW, struct.pack("<5I", 0x100, 40, 6320, 2582, 0))
    machine.mem_write(STATUS, struct.pack("<I", 4))
    machine.mem_write(CONFIG + 0x98, struct.pack("<I", 3))
    machine.mem_write(CONFIG + 0x7C, struct.pack("<I", 0xA5000006))
    machine.mem_write(REGISTERS, struct.pack("<2I", 0x50032404, 0x00510E00))
    for address in (STATUS & ~4095, SHADOW & ~4095, TIMER & ~4095,
                    CONFIG & ~4095, REGISTERS & ~4095):
        machine.mem_protect(address, 4096, unicorn.UC_PROT_READ)
    reads, writes = [], []
    positions = {TIMER: 0, TIMER + 4: 0, TIMER + 8: 0}
    values = {TIMER: lows, TIMER + 4: highs, TIMER + 8: controls}

    def read_memory(uc, access, address, size, value, context):
        if address in values:
            assert size == 4
            sequence_values = values[address]
            index = positions[address]
            positions[address] += 1
            supplied = sequence_values[min(index, len(sequence_values) - 1)]
            uc.mem_write(address, struct.pack("<I", supplied))
            reads.append(address)
        elif address in (STATUS, CONFIG + 0x98, CONFIG + 0x7C, REGISTERS, REGISTERS + 4) or SHADOW <= address < SHADOW + 20:
            assert size == 4
            reads.append(address)
        else:
            assert (OUT <= address and address + size <= OUT + RECORD_SIZE) or (
                STACK <= address and address + size <= STACK + 4096), hex(address)

    def write_memory(uc, access, address, size, value, context):
        assert (OUT <= address and address + size <= OUT + RECORD_SIZE) or (
            STACK <= address and address + size <= STACK + 4096), hex(address)
        # 编译器可在拒绝分支前保存寄存器；私有栈写仍受上面的界限约束。
        # 一次性/拒绝检查计数只针对共享记录，不能把正常函数栈保存当成二次采样。
        if OUT <= address and address + size <= OUT + RECORD_SIZE:
            writes.append((address, size))

    def guard_code(uc, address, size, context):
        assert any(a <= address < b for a, b in code_ranges), hex(address)

    machine.hook_add(unicorn.UC_HOOK_MEM_READ, read_memory)
    machine.hook_add(unicorn.UC_HOOK_MEM_WRITE, write_memory)
    machine.hook_add(unicorn.UC_HOOK_CODE, guard_code)
    preserved = [getattr(arm, "UC_ARM_REG_R" + str(i)) for i in range(4, 12)]
    for index, register in enumerate(preserved):
        machine.reg_write(register, 0xA0000000 + index)
    stack_pointer = STACK + 0xF00
    machine.reg_write(arm.UC_ARM_REG_SP, stack_pointer)

    def invoke():
        machine.reg_write(arm.UC_ARM_REG_R0, pointer)
        machine.reg_write(arm.UC_ARM_REG_LR, RETURN)
        machine.emu_start(entry, RETURN, timeout=1_000_000, count=5000)
        assert machine.reg_read(arm.UC_ARM_REG_PC) == RETURN
        assert machine.reg_read(arm.UC_ARM_REG_SP) == stack_pointer
        assert [machine.reg_read(r) for r in preserved] == [
            0xA0000000 + i for i in range(8)]
        return machine.reg_read(arm.UC_ARM_REG_R0)

    result = invoke()
    record = struct.unpack("<22I", machine.mem_read(OUT, RECORD_SIZE))
    if repeat:
        checkpoint = (len(reads), len(writes), record)
        assert invoke() == 0
        assert checkpoint == (len(reads), len(writes), struct.unpack(
            "<22I", machine.mem_read(OUT, RECORD_SIZE)))
    return result, record, reads, writes


class FarmSensorProbeTests(unittest.TestCase):
    def test_normal_and_one_shot(self):
        result, record, reads, _ = execute(repeat=True)
        self.assertEqual(result, 1)
        self.assertEqual(record[:4], (MAGIC, 0, 2, 1))
        self.assertEqual(record[4:8], (100, 7, 1, 1))
        self.assertEqual(record[8:14], (4, 0x100, 40, 6320, 2582, 0))
        self.assertEqual(record[14:18], (3, 0xA5000006, 0x50032404, 0x00510E00))
        self.assertEqual((record[16] >> 16) & 0xFFF, 3)
        self.assertEqual((record[17] >> 8) & 0x3FFF, 4366)
        self.assertEqual(record[18:], (100, 7, 1, 1))
        self.assertEqual(reads.count(STATUS), 1)
        for address in (CONFIG + 0x98, CONFIG + 0x7C, REGISTERS, REGISTERS + 4):
            self.assertEqual(reads.count(address), 1)

    def test_disabled_timer_is_not_started(self):
        _, record, reads, _ = execute(controls=(0,))
        self.assertEqual(record[4:8], (0, 0, 0, 0))
        self.assertEqual(record[18:], (0, 0, 0, 0))
        self.assertNotIn(TIMER, reads)
        self.assertNotIn(TIMER + 4, reads)

    def test_rollover_retries(self):
        _, record, _, _ = execute(highs=(0, 1, 1, 1, 1, 1),
                                  lows=(0xFFFFFFFF, 12, 25))
        self.assertEqual(record[4:8], (12, 1, 1, 1))
        self.assertEqual(record[18:], (25, 1, 1, 1))

    def test_unstable_timer_is_bounded(self):
        _, record, reads, _ = execute(highs=tuple(range(16)))
        self.assertEqual(record[7], 0)
        self.assertEqual(record[21], 0)
        self.assertEqual(reads.count(TIMER + 4), 16)
        self.assertEqual(reads.count(TIMER), 8)

    def test_changed_control_invalidates_timestamp(self):
        _, record, _, _ = execute(controls=(1, 0, 1, 0))
        self.assertEqual(record[7], 0)
        self.assertEqual(record[21], 0)

    def test_sequence_wrap(self):
        _, record, _, _ = execute(sequence=0xFFFFFFFE)
        self.assertEqual(record[2], 0)

    def test_rejected_inputs_do_not_touch_hardware(self):
        for options in ({"magic": 0}, {"magic": 0x53504647}, {"armed": 0}, {"armed": 2},
                        {"sequence": 1}, {"pointer": 0}, {"pointer": OUT + 1}):
            with self.subTest(options=options):
                result, _, reads, writes = execute(**options)
                self.assertEqual(result, 0)
                self.assertEqual(reads, [])
                self.assertEqual(writes, [])


if __name__ == "__main__":
    unittest.main()
