"""执行真实 ARM 包装及固定来源原指令；全部地址、硬件值均为合成内存。"""
import io
import struct
import unittest
from pathlib import Path

import unicorn
from unicorn import arm_const as arm
from elftools.elf.elffile import ELFFile

ELF_PATH = Path(__file__).resolve().parents[1] / "build" / "farm-sensor-hook-simulation.elf"
HOOK, CONTINUE, STOP = 0x214110, 0x214114, 0x214120
STACK, TIMER, STATUS, SHADOW = 0x03000000, 0xF8F00200, 0x42000014, 0x2B1990
CONFIG, REGISTERS = 0x6C1690, 0x6DB2E8
MAGIC, SIZE, CALLER = 0x32504647, 88, 0x1C437C
# 官方 X1D 1.25.0，FARM SHA256 317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca。
# 0x214110..0x21411f：movw / movt / mov / strb。
ORIGINAL = bytes.fromhex("903901e32b3040e30120a0e30120c3e5")


def execute(*, caller=CALLER, arg0=0, arg1=0, control=3, armed=1,
            flags=0xA80501D3, patched=True, repeat=False):
    elf = ELFFile(io.BytesIO(ELF_PATH.read_bytes()))
    data = elf.get_section_by_name(".data")
    code_parts = [(section["sh_addr"], section.data()) for section in elf.iter_sections()
                  if section["sh_flags"] & 4 and section["sh_size"]]
    code_ranges = [(a, a + len(b)) for a, b in code_parts]
    out, initial_data = data["sh_addr"], data.data()
    entry = elf.header["e_entry"]
    assert len(initial_data) == SIZE and struct.unpack_from("<2I", initial_data) == (MAGIC, 0)
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
    pages = {a & ~4095 for a in (out, HOOK, STACK, TIMER, STATUS, SHADOW, CONFIG, REGISTERS)}
    for a, b in code_ranges:
        pages.update(range(a & ~4095, (b + 4095) & ~4095, 4096))
    for address in sorted(pages):
        uc.mem_map(address, 4096)
    for address, code in code_parts:
        uc.mem_write(address, code)
    for a, b in code_ranges:
        for page in range(a & ~4095, (b + 4095) & ~4095, 4096):
            if page != (out & ~4095):
                uc.mem_protect(page, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
    uc.mem_write(out, initial_data)
    uc.mem_write(out + 4, struct.pack("<I", armed))
    original_region = bytearray(ORIGINAL)
    if patched:
        displacement = (entry - HOOK - 8) // 4
        assert entry % 4 == 0 and -(1 << 23) <= displacement < (1 << 23)
        original_region[:4] = struct.pack("<I", 0xEA000000 | (displacement & 0xFFFFFF))
    uc.mem_write(HOOK, bytes(original_region))
    uc.mem_protect(HOOK & ~4095, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
    uc.mem_write(TIMER, struct.pack("<3I", 100, 7, 1))
    uc.mem_write(STATUS, struct.pack("<I", 4))
    uc.mem_write(SHADOW, struct.pack("<5I", 0, 40, 6320, 2582, 0))
    uc.mem_write(CONFIG + 0x98, struct.pack("<I", 3))
    uc.mem_write(CONFIG + 0x7C, struct.pack("<I", 0xA5000006))
    uc.mem_write(REGISTERS, struct.pack("<2I", 0x50032404, 0x00510E00))
    for address in (TIMER & ~4095, STATUS & ~4095, CONFIG & ~4095, REGISTERS & ~4095):
        uc.mem_protect(address, 4096, unicorn.UC_PROT_READ)

    fp, sp = STACK + 0x704, STACK + 0x5D0
    assert fp - sp == 0x134 and sp % 8 == 0
    uc.mem_write(fp, struct.pack("<I", caller))
    uc.mem_write(fp - 0x12D, bytes([arg0]))
    uc.mem_write(fp - 0x12E, bytes([arg1]))
    uc.mem_write(fp - 0xC, struct.pack("<I", control))
    registers = [getattr(arm, "UC_ARM_REG_R" + str(i)) for i in range(13)]
    before = [0xA0000000 + i * 0x10001 for i in range(13)]
    before[11] = fp
    expected = before.copy()
    expected[2], expected[3] = 1, SHADOW
    vfp = [getattr(arm, "UC_ARM_REG_D" + str(i)) for i in range(32)]
    for index, register in enumerate(vfp):
        uc.reg_write(register, 0x1122334455660000 + index)
    reads, record_writes, factory_writes = [], [], []
    visited = []

    def read_memory(machine, access, address, size, value, context):
        if address in (TIMER, TIMER + 4, TIMER + 8, STATUS,
                       CONFIG + 0x98, CONFIG + 0x7C, REGISTERS, REGISTERS + 4) or SHADOW <= address < SHADOW + 20:
            assert size == 4
            reads.append(address)
        else:
            assert (out <= address and address + size <= out + SIZE) or (
                STACK <= address and address + size <= STACK + 4096) or (
                any(a <= address and address + size <= b for a, b in code_ranges)), hex(address)

    def write_memory(machine, access, address, size, value, context):
        pc = machine.reg_read(arm.UC_ARM_REG_PC)
        if out <= address and address + size <= out + SIZE:
            record_writes.append((address, size))
        elif address == SHADOW + 1 and size == 1 and pc == 0x21411C:
            assert value == 1
            factory_writes.append(address)
        else:
            assert STACK <= address and address + size <= sp, (hex(address), hex(pc))

    def guard_code(machine, address, size, context):
        assert any(a <= address < b for a, b in code_ranges) or HOOK <= address < STOP, hex(address)
        visited.append(address)

    uc.hook_add(unicorn.UC_HOOK_MEM_READ, read_memory)
    uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, write_memory)
    uc.hook_add(unicorn.UC_HOOK_CODE, guard_code)

    def invoke():
        uc.reg_write(arm.UC_ARM_REG_CPSR, flags)
        actual_flags = uc.reg_read(arm.UC_ARM_REG_CPSR)
        for register, value in zip(registers, before):
            uc.reg_write(register, value)
        uc.reg_write(arm.UC_ARM_REG_SP, sp)
        uc.reg_write(arm.UC_ARM_REG_LR, CONTINUE)
        uc.emu_start(HOOK, STOP, timeout=1_000_000, count=5000)
        assert uc.reg_read(arm.UC_ARM_REG_PC) == STOP
        assert uc.reg_read(arm.UC_ARM_REG_SP) == sp
        assert uc.reg_read(arm.UC_ARM_REG_LR) == CONTINUE
        assert [uc.reg_read(r) for r in registers] == expected
        assert uc.reg_read(arm.UC_ARM_REG_CPSR) == actual_flags
        assert [uc.reg_read(r) for r in vfp] == [0x1122334455660000 + i for i in range(32)]
        assert uc.mem_read(fp, 4) == struct.pack("<I", caller)

    invoke()
    record = struct.unpack("<22I", uc.mem_read(out, SIZE))
    if repeat:
        previous = len(reads), len(record_writes), record
        invoke()
        assert previous == (len(reads), len(record_writes), struct.unpack("<22I", uc.mem_read(out, SIZE)))
    assert factory_writes == [SHADOW + 1] * (2 if repeat else 1)
    assert struct.unpack("<5I", uc.mem_read(SHADOW, 20)) == (0x100, 40, 6320, 2582, 0)
    return record, reads, record_writes, visited


class FarmSensorHookTests(unittest.TestCase):
    def test_exposure_call_and_one_shot(self):
        record, reads, _, _ = execute(repeat=True)
        self.assertEqual(record[:4], (MAGIC, 0, 2, 1))
        self.assertEqual(record[8:14], (4, 0, 40, 6320, 2582, 0))
        self.assertEqual(record[14:18], (3, 0xA5000006, 0x50032404, 0x00510E00))
        self.assertEqual(record[18:], (100, 7, 1, 1))
        self.assertEqual(reads.count(STATUS), 1)
        for address in (CONFIG + 0x98, CONFIG + 0x7C, REGISTERS, REGISTERS + 4):
            self.assertEqual(reads.count(address), 1)

    def test_other_callers_are_ignored(self):
        for caller in (0, CALLER + 4, 0x12345678):
            with self.subTest(caller=caller):
                record, reads, writes, _ = execute(caller=caller)
                self.assertEqual(record[:4], (MAGIC, 1, 0, 0))
                self.assertEqual((reads, writes), ([], []))

    def test_parameter_mismatch_is_ignored(self):
        for options in ({"arg0": 1}, {"arg1": 1}, {"arg1": 2}, {"control": 0}, {"control": 7}):
            with self.subTest(options=options):
                _, reads, writes, _ = execute(**options)
                self.assertEqual((reads, writes), ([], []))

    def test_default_disarmed_preserves_factory_flow(self):
        _, reads, writes, _ = execute(armed=0)
        self.assertEqual((reads, writes), ([], []))

    def test_flags_and_registers_preserved_on_both_paths(self):
        for flags in (0x13, 0xF80F01D3, 0x280A0093):
            for caller in (CALLER, 0):
                with self.subTest(flags=flags, caller=caller):
                    execute(flags=flags, caller=caller)

    def test_restored_original_instruction_removes_hook(self):
        record, reads, writes, visited = execute(patched=False)
        self.assertEqual(record[:4], (MAGIC, 1, 0, 0))
        self.assertEqual((reads, writes), ([], []))
        self.assertEqual(visited, list(range(HOOK, STOP, 4)))


if __name__ == "__main__":
    unittest.main()
