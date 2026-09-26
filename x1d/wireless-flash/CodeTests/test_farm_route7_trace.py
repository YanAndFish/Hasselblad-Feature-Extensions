"""原 FARM BL 与候选入口的上下文逐项对照；仅内存 Unicorn。"""
import hashlib
import io
import json
from pathlib import Path
import struct
import unittest

from elftools.elf.elffile import ELFFile
import unicorn
from unicorn import arm_const as arm
from build_farm_route7_trace import SITES, OUT
from farm_route7_record import MAGIC, SIZE, parse_snapshot

FARM = None
LAYOUT = "simulation"
STACK, MESSAGE = 0x3000000, 0x3100000
GPRS = [getattr(arm, "UC_ARM_REG_R" + str(i)) for i in range(13)] + [arm.UC_ARM_REG_SP, arm.UC_ARM_REG_LR]
VFP = [getattr(arm, "UC_ARM_REG_D" + str(i)) for i in range(32)]


class Machine:
    def __init__(self, patched=True, armed=1, sequence=0, magic=MAGIC, lock=0):
        assert hashlib.sha256(FARM).hexdigest() == "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
        self.uc = u = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
        u.mem_map(0x100000, 0x1c0000)
        u.mem_write(0x100000, FARM)
        elf = ELFFile(io.BytesIO((OUT / (LAYOUT + ".elf")).read_bytes()))
        symbols = {s.name: s["st_value"] for sec in elf.iter_sections() if sec["sh_type"] == "SHT_SYMTAB" for s in sec.iter_symbols()}
        self.record = symbols["route7_record"]
        if LAYOUT == "simulation":
            u.mem_map(0x1000000, 0x1000)
        for s in elf.iter_sections():
            if s["sh_flags"] & 2 and s["sh_size"]:
                u.mem_write(s["sh_addr"], s.data())
        for a, (s, target, original) in SITES.items():
            assert struct.unpack("<I", u.mem_read(a, 4))[0] == original
            displacement = original & 0xffffff
            if displacement & 0x800000:
                displacement -= 0x1000000
            assert a + 8 + 4 * displacement == target
            if patched:
                u.mem_write(a, struct.pack("<I", 0xeb000000 | (((symbols[s] - a - 8) // 4) & 0xffffff)))
        u.mem_map(STACK, 0x1000)
        u.mem_map(MESSAGE, 0x1000)
        u.mem_write(self.record, struct.pack("<8I", magic, armed, sequence, 0, 0, 0, lock, 0))
        self.writes = []
        self.external_reads = []
        self.limit = None
        u.hook_add(unicorn.UC_HOOK_MEM_WRITE, self.on_write)
        u.hook_add(unicorn.UC_HOOK_MEM_READ, self.on_read)
        u.hook_add(unicorn.UC_HOOK_CODE, self.on_code)

    def on_code(self, u, address, size, _):
        if address == self.limit:
            u.emu_stop()

    def on_write(self, u, access, address, size, value, _):
        assert self.record <= address and address + size <= self.record + SIZE or STACK <= address and address + size <= STACK + 0x1000, hex(address)
        self.writes.append((address, size, value))

    def on_read(self, u, access, address, size, value, _):
        assert (0x100000 <= address and address + size <= 0x2c0000 or
                0x1000000 <= address and address + size <= 0x1001000 or
                STACK <= address and address + size <= STACK + 0x1000 or address == MESSAGE + 4 and size == 1), hex(address)
        if address == MESSAGE + 4:
            self.external_reads.append(address)

    def snapshot(self):
        return [self.uc.reg_read(r) for r in GPRS + [arm.UC_ARM_REG_CPSR, arm.UC_ARM_REG_FPSCR] + VFP]

    def call(self, site, mode=0, flags=0xa80f0013):
        u = self.uc
        u.reg_write(arm.UC_ARM_REG_CPSR, flags)
        for i, reg in enumerate(GPRS):
            u.reg_write(reg, 0x11223300 + i * 13)
        u.reg_write(arm.UC_ARM_REG_R0, MESSAGE)
        u.reg_write(arm.UC_ARM_REG_SP, STACK + 0xf00)
        for i, reg in enumerate(VFP):
            u.reg_write(reg, 0x1029384700000000 + i)
        u.reg_write(arm.UC_ARM_REG_FPSCR, 0x01000000)
        u.mem_write(MESSAGE + 4, bytes([mode]))
        self.limit = SITES[site][1]
        u.emu_start(site, 0, count=250)
        assert u.reg_read(arm.UC_ARM_REG_PC) == self.limit
        assert u.reg_read(arm.UC_ARM_REG_LR) == site + 4
        return self.snapshot()

    def raw(self):
        return bytes(self.uc.mem_read(self.record, SIZE))

    def decoded(self):
        seq = struct.unpack_from("<I", self.raw(), 8)[0]
        return parse_snapshot(self.raw(), sequence_before=seq, sequence_after=seq)


class Route7Tests(unittest.TestCase):
    def test_original_bl_targets_and_complete_context(self):
        for site in SITES:
            for flags in (0x13, 0xf80f0013, 0xa8050013):
                with self.subTest(site=hex(site), flags=flags):
                    a, b = Machine(False), Machine(True)
                    self.assertEqual(a.call(site, 1, flags), b.call(site, 1, flags))
                    self.assertEqual(b.decoded()["count"], 1)

    def test_modes_and_event_sequence(self):
        for mode in (0, 1, 2, 3, 4, 255):
            a = Machine()
            for site in (0x1c4318, 0x1ce150, 0x1c8874, 0x1c8950):
                a.call(site, mode)
            d = a.decoded()
            self.assertEqual([e["stage"] for e in d["events"]], ["normal_capture_marker", "route7_request_entry", "route7_before_pulse", "route7_after_sensor_call_and_wait"])
            self.assertEqual(d["events"][1]["mode"], mode)
            self.assertFalse(d["physical_flash_or_integration_verified"])
            self.assertEqual(a.external_reads, [MESSAGE + 4])

    def test_disarmed_or_wrong_magic_has_no_record_or_message_access(self):
        for kwargs in ({"armed": 0}, {"magic": 0}, {"armed": 2}):
            a = Machine(**kwargs)
            before = a.raw()
            for site in SITES:
                a.call(site)
            self.assertEqual(a.raw(), before)
            self.assertEqual(a.external_reads, [])

    def test_overflow_retains_first_sixteen(self):
        a = Machine()
        for i in range(16):
            a.call(0x1ce150, i)
        retained = a.raw()[32:]
        for i in range(4):
            a.call(0x1c8874)
        self.assertEqual(a.raw()[32:], retained)
        self.assertTrue(a.decoded()["overflow"])
        self.assertFalse(a.decoded()["complete_buffer"])

    def test_busy_lock_drops_without_waiting(self):
        a = Machine(lock=1)
        a.call(0x1ce150)
        words = struct.unpack("<24I", a.raw())
        self.assertEqual(words[2:7], (0, 0, 0, 1, 1))
        self.assertEqual(a.external_reads, [])

    def test_sequence_wrap_and_corrupt_sequence(self):
        a = Machine(sequence=0xfffffffe)
        a.call(0x1c8874)
        self.assertEqual(a.decoded()["sequence"], 0)
        b = Machine(sequence=3)
        b.call(0x1ce150)
        words = struct.unpack("<24I", b.raw())
        self.assertEqual(words[2:7], (3, 0, 0, 1, 0))

    def test_snapshot_rejects_busy_or_torn_and_empty_is_not_flash_proof(self):
        a = Machine()
        self.assertEqual(a.decoded()["events"], [])
        for before, after in ((0, 2), (True, 0), (1, 1)):
            with self.assertRaises(ValueError):
                parse_snapshot(a.raw(), sequence_before=before, sequence_after=after)
        with self.assertRaises(ValueError):
            Machine(lock=1).decoded()


def run(farm):
    global FARM, LAYOUT
    FARM = farm
    report = {"hardware_requests": 0}
    for LAYOUT in ("simulation", "target"):
        result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Route7Tests))
        report[LAYOUT] = {"tests": result.testsRun, "passed": result.wasSuccessful()}
    report["passed"] = all(report[n]["passed"] for n in ("simulation", "target"))
    example = Machine()
    for site in (0x1c4318, 0x1ce150, 0x1c8874, 0x1c8950):
        example.call(site, 1)
    report["arm_record"] = list(struct.unpack("<24I", example.raw()))
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
