"""执行原厂曝光编码、两个 ARM 包装及启动原指令；不连接任何设备。"""
import hashlib
import io
from pathlib import Path
import struct
import unittest

from elftools.elf.elffile import ELFFile
import unicorn
from unicorn import arm_const as arm

HERE = Path(__file__).resolve().parents[1]
ELF_PATH = HERE / "build/farm-sensor-capture-v3/simulation.elf"
FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
# 执行者须显式提供完整固定来源；不自动搜索固件或连接设备。
FARM = None
ENCODE_HOOK, START_HOOK = 0x233C7C, 0x214110
CONFIG, REGISTERS, STACK = 0x6C1690, 0x6DB2E8, 0x3000000
TIMER, STATUS, SHADOW = 0xF8F00200, 0x42000014, 0x2B1990
MAGIC, SIZE = 0x33504647, 116
ENCODE_CODE = ((0x233A4C, 0x233C84), (0x15AE34, 0x15AE70),
               (0x15AF54, 0x15AF90), (0x15C880, 0x15C994))


class Machine:
    def __init__(self, *, patched=True, armed=1, magic=MAGIC, sequence=0, timer_control=1):
        if type(FARM) is not bytes or len(FARM) != 1808280 or hashlib.sha256(FARM).hexdigest() != FARM_SHA:
            raise ValueError("explicit fixed FARM required")
        self.uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
        u = self.uc
        u.mem_map(0x100000, (len(FARM) + 4095) & ~4095)
        u.mem_write(0x100000, FARM)
        elf = ELFFile(io.BytesIO(ELF_PATH.read_bytes()))
        symbols = {symbol.name: symbol["st_value"] for section in elf.iter_sections()
                   if section["sh_type"] == "SHT_SYMTAB" for symbol in section.iter_symbols()}
        self.code = [(s["sh_addr"], s["sh_addr"] + s["sh_size"]) for s in elf.iter_sections()
                     if s["sh_flags"] & 4 and s["sh_size"]]
        self.out = symbols["farm_capture_record"]
        pages = set()
        for start, end in self.code + [(self.out, self.out + SIZE)]:
            pages.update(range(start & ~4095, (end + 4095) & ~4095, 4096))
        for page in pages:
            if not 0x100000 <= page < 0x100000 + ((len(FARM) + 4095) & ~4095):
                u.mem_map(page, 4096)
        for section in elf.iter_sections():
            if section["sh_flags"] & 2 and section["sh_size"]:
                u.mem_write(section["sh_addr"], section.data())
        assert bytes(u.mem_read(ENCODE_HOOK, 8)) == bytes.fromhex("08d04be21088bde8")
        assert bytes(u.mem_read(START_HOOK, 16)) == bytes.fromhex("903901e32b3040e30120a0e30120c3e5")
        if patched:
            for address, symbol in ((ENCODE_HOOK, "farm_capture_encoding_hook"), (START_HOOK, "farm_capture_start_hook")):
                target = symbols[symbol]
                offset = (target - address - 8) // 4
                assert target % 4 == 0 and -(1 << 23) <= offset < (1 << 23)
                u.mem_write(address, struct.pack("<I", 0xEA000000 | (offset & 0xFFFFFF)))
        u.mem_protect(0x100000, (len(FARM) + 4095) & ~4095, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
        u.mem_protect(SHADOW & ~4095, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
        u.mem_protect(self.out & ~4095, 4096, unicorn.UC_PROT_ALL)
        for start, end in self.code:
            for page in range(start & ~4095, (end + 4095) & ~4095, 4096):
                if page != (self.out & ~4095):
                    u.mem_protect(page, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
        for page in (CONFIG & ~4095, REGISTERS & ~4095, STACK, TIMER & ~4095, STATUS & ~4095):
            u.mem_map(page, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
        u.mem_write(self.out, struct.pack("<4I", magic, armed, sequence, 0))
        u.mem_write(CONFIG + 0x70, struct.pack("<I", 2582))
        u.mem_write(CONFIG + 0x78, struct.pack("<I", 6320))
        u.mem_write(CONFIG + 0x7C, struct.pack("<I", 14))
        u.mem_write(REGISTERS, bytes.fromhex("0420000000010000"))
        u.mem_write(TIMER, struct.pack("<3I", 100, 7, timer_control))
        u.mem_write(STATUS, struct.pack("<I", 0x3F34))
        u.mem_write(SHADOW, struct.pack("<5I", 917507, 40, 6320, 2582, 0))
        for page in (TIMER & ~4095, STATUS & ~4095):
            u.mem_protect(page, 4096, unicorn.UC_PROT_READ)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xF << 20)
        u.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        self.mmio_reads, self.record_writes = [], []
        self.running = "none"

        def instruction(uc, address, size, context):
            allowed = self.code + (list(ENCODE_CODE) if self.running == "encoding" else [(START_HOOK, 0x214120)])
            if not any(a <= address < b for a, b in allowed):
                raise RuntimeError("unexpected PC " + hex(address))

        def write(uc, access, address, size, value, context):
            if self.out <= address and address + size <= self.out + SIZE:
                self.record_writes.append((address, size))
                return
            if STACK <= address and address + size <= STACK + 4096:
                return
            if self.running == "encoding" and any(a <= address and address + size <= b for a, b in (
                    (CONFIG, CONFIG + 0x300), (REGISTERS, REGISTERS + 0x200))):
                # 固定原厂编码的模拟输出；新代码不得修改它们。
                pc = uc.reg_read(arm.UC_ARM_REG_PC)
                assert any(a <= pc < b for a, b in ENCODE_CODE)
                return
            if self.running == "start" and address == SHADOW + 1 and size == 1:
                assert uc.reg_read(arm.UC_ARM_REG_PC) == 0x21411C and value == 1
                return
            raise RuntimeError("unexpected write " + hex(address))

        def read(uc, access, address, size, value, context):
            if address >= 0x40000000:
                assert self.running == "start" and size == 4 and address in (TIMER, TIMER + 4, TIMER + 8, STATUS)
                self.mmio_reads.append(address)

        u.hook_add(unicorn.UC_HOOK_CODE, instruction)
        u.hook_add(unicorn.UC_HOOK_MEM_WRITE, write)
        u.hook_add(unicorn.UC_HOOK_MEM_READ, read)

    def snapshot(self):
        u = self.uc
        return ([u.reg_read(getattr(arm, "UC_ARM_REG_R" + str(i))) for i in range(13)],
                [u.reg_read(r) for r in (arm.UC_ARM_REG_SP, arm.UC_ARM_REG_LR, arm.UC_ARM_REG_CPSR)],
                [u.reg_read(getattr(arm, "UC_ARM_REG_D" + str(i))) for i in range(32)])

    def init_registers(self):
        u = self.uc
        u.reg_write(arm.UC_ARM_REG_CPSR, 0xA80A01D3)
        for i in range(13):
            u.reg_write(getattr(arm, "UC_ARM_REG_R" + str(i)), 0x11000000 + i * 0x10001)
        for i in range(32):
            u.reg_write(getattr(arm, "UC_ARM_REG_D" + str(i)), 0x1122334400000000 + i)

    def encode(self, exposure=1_000_000, *, caller=0x230674, config=CONFIG, registers=REGISTERS):
        u = self.uc
        mmio_count_before = len(self.mmio_reads)
        self.running = "encoding"
        self.init_registers()
        # 不匹配指针用另一块合成数据；仍完整执行原编码函数。
        u.mem_write(config + 0x70, struct.pack("<I", 2582))
        u.mem_write(config + 0x78, struct.pack("<I", 6320))
        for register, value in ((arm.UC_ARM_REG_R0, exposure & 0xFFFFFFFF), (arm.UC_ARM_REG_R1, exposure >> 32),
                                (arm.UC_ARM_REG_R2, config), (arm.UC_ARM_REG_R3, registers),
                                (arm.UC_ARM_REG_SP, STACK + 0xF00), (arm.UC_ARM_REG_LR, caller)):
            u.reg_write(register, value)
        u.emu_start(0x233AC0, caller, timeout=1_000_000, count=100_000)
        assert u.reg_read(arm.UC_ARM_REG_PC) == caller
        assert u.reg_read(arm.UC_ARM_REG_SP) == STACK + 0xF00
        assert (u.reg_read(arm.UC_ARM_REG_R0) | (u.reg_read(arm.UC_ARM_REG_R1) << 32)) == exposure
        assert len(self.mmio_reads) == mmio_count_before
        return self.snapshot()

    def overwrite_template(self):
        self.uc.mem_write(REGISTERS, bytes.fromhex("0420000000010000"))

    def start(self, *, caller=0x1C437C, arg0=0, arg1=0, control=3):
        u = self.uc
        self.running = "start"
        self.init_registers()
        fp, sp = STACK + 0x704, STACK + 0x5D0
        u.mem_write(fp, struct.pack("<I", caller))
        u.mem_write(fp - 0x12D, bytes([arg0]))
        u.mem_write(fp - 0x12E, bytes([arg1]))
        u.mem_write(fp - 0xC, struct.pack("<I", control))
        u.reg_write(arm.UC_ARM_REG_R11, fp)
        u.reg_write(arm.UC_ARM_REG_SP, sp)
        u.reg_write(arm.UC_ARM_REG_LR, 0x214114)
        u.emu_start(START_HOOK, 0x214120, timeout=1_000_000, count=5000)
        assert u.reg_read(arm.UC_ARM_REG_PC) == 0x214120
        assert u.reg_read(arm.UC_ARM_REG_SP) == sp
        return self.snapshot()

    def record(self):
        return struct.unpack("<29I", self.uc.mem_read(self.out, SIZE))

    def decoded(self):
        import farm_capture_v3_record
        raw = bytes(self.uc.mem_read(self.out, SIZE))
        sequence = self.record()[2]
        return farm_capture_v3_record.parse_snapshot(raw, sequence_before=sequence, sequence_after=sequence)


class FarmSensorCaptureV3Tests(unittest.TestCase):
    def test_real_encoder_and_start_preserve_original_execution(self):
        observed, original = Machine(), Machine(patched=False)
        self.assertEqual(observed.encode(), original.encode())
        observed.overwrite_template()
        original.overwrite_template()
        self.assertEqual(observed.start(), original.start())
        record = observed.record()
        self.assertEqual(record[:4], (MAGIC, 0, 2, 1))
        self.assertEqual(record[16:18], (0x2004, 0x100))
        self.assertEqual(record[22:], (1, 3, 0x32004, 0x110E00, 1_000_000, 0, 1))
        decoded = observed.decoded()
        self.assertEqual(decoded["encoding_snapshot"]["encoded_r"], 4366)
        self.assertTrue(decoded["encoding_snapshot"]["single_matching_call_before_start"])
        self.assertFalse(decoded["physical_integration_event_verified"])

    def test_wrong_encoding_caller_and_pointers_are_ignored(self):
        for options in ({"caller": 0x230678}, {"config": CONFIG + 0x100}, {"registers": REGISTERS + 0x100}):
            with self.subTest(options=options):
                observed, original = Machine(), Machine(patched=False)
                self.assertEqual(observed.encode(**options), original.encode(**options))
                self.assertEqual(observed.record()[22:], (0,) * 7)
                self.assertEqual(observed.record_writes, [])

    def test_missing_encoding_is_not_accepted_as_a_pair(self):
        machine = Machine()
        machine.start()
        decoded = machine.decoded()
        self.assertFalse(decoded["encoding_snapshot"]["valid"])
        self.assertIsNone(decoded["encoding_snapshot"]["input_exposure_us"])

    def test_multiple_encodings_expose_ambiguity(self):
        machine = Machine()
        machine.encode()
        machine.encode(2_000_000)
        machine.overwrite_template()
        machine.start()
        decoded = machine.decoded()["encoding_snapshot"]
        self.assertEqual(decoded["matching_call_count"], 2)
        self.assertEqual(decoded["input_exposure_us"], 2_000_000)
        self.assertFalse(decoded["single_matching_call_before_start"])

    def test_rejected_record_and_start_paths_do_not_read_hardware(self):
        for options in ({"armed": 0}, {"magic": 0x32504647}, {"sequence": 1}):
            with self.subTest(options=options):
                machine = Machine(**options)
                before = machine.record()
                machine.encode()
                machine.start()
                self.assertEqual(machine.record(), before)
                self.assertEqual(machine.mmio_reads, [])
                self.assertEqual(machine.record_writes, [])
        for options in ({"caller": 0x1C4380}, {"arg0": 1}, {"arg1": 1}, {"control": 7}):
            with self.subTest(options=options):
                machine = Machine()
                machine.encode()
                before = machine.record()
                machine.start(**options)
                self.assertEqual(machine.record(), before)
                self.assertEqual(machine.mmio_reads, [])

    def test_consumed_record_is_not_changed_by_later_calls(self):
        machine = Machine()
        machine.encode()
        machine.start()
        before = machine.record(), len(machine.mmio_reads), len(machine.record_writes)
        machine.encode(2_000_000)
        machine.start()
        self.assertEqual((machine.record(), len(machine.mmio_reads), len(machine.record_writes)), before)

    def test_timer_disabled_and_sequence_wrap(self):
        machine = Machine(timer_control=0, sequence=0xFFFFFFFE)
        machine.encode()
        machine.start()
        decoded = machine.decoded()
        self.assertEqual(decoded["sequence"], 0)
        self.assertFalse(decoded["timer_before"]["valid"])
        self.assertIsNone(decoded["read_interval_raw_ticks"])

    def test_parser_rejects_inconsistent_snapshots(self):
        import farm_capture_v3_record as parser
        machine = Machine()
        machine.encode()
        machine.start()
        raw = bytes(machine.uc.mem_read(machine.out, SIZE))
        for data, before, after in ((raw[:-4], 2, 2), (raw, 0, 2), (raw, 2, 4), (raw, True, 2)):
            with self.subTest(length=len(data), before=before, after=after):
                with self.assertRaises(ValueError):
                    parser.parse_snapshot(data, sequence_before=before, sequence_after=after)


if __name__ == "__main__":
    raise SystemExit("Provide fixed FARM bytes explicitly from the reviewed offline source.")
