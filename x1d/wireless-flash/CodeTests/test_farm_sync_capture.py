"""运行候选 ARM 指令，使用显式 MMIO/队列替身，不访问相机。"""
import hashlib
import io
from pathlib import Path
import struct
import unittest

from elftools.elf.elffile import ELFFile
import unicorn
from unicorn import arm_const as arm

HERE = Path(__file__).resolve().parents[1]
ELF_PATH = HERE / "build/farm-sync-capture/simulation.elf"
FARM = None
FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
CLEAR, OBSERVE, WRITE, QUEUE = 0x21409C, 0x1C4380, 0x238820, 0x186500
CONTROL, STATUS, TIMER, STACK = 0x42000010, 0x42000014, 0xF8F00200, 0x3000000
MAGIC, SIZE = 0x33534647, 356
PROGRESS, STOP = 0x1C4458, 0x1C44F4


class Machine:
    def __init__(self, *, patched=True, enabled=1, magic=MAGIC, sequence=0,
                 clear_status=0x3334, observed_status=0x3734, timer_control=1,
                 queue_result=1, queue_handle=0x006D5000):
        if type(FARM) is not bytes or hashlib.sha256(FARM).hexdigest() != FARM_SHA:
            raise ValueError("Provide the fixed official FARM bytes explicitly")
        u = self.uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
        length = (len(FARM) + 4095) & ~4095
        u.mem_map(0x100000, length)
        u.mem_write(0x100000, FARM)
        elf = ELFFile(io.BytesIO(ELF_PATH.read_bytes()))
        symbols = {s.name: s["st_value"] for section in elf.iter_sections()
                   if section["sh_type"] == "SHT_SYMTAB" for s in section.iter_symbols()}
        self.out = symbols["farm_sync_record"]
        self.code = [(s["sh_addr"], s["sh_addr"] + s["sh_size"])
                     for s in elf.iter_sections() if s["sh_flags"] & 4 and s["sh_size"]]
        pages = set()
        for start, end in self.code + [(self.out, self.out + SIZE)]:
            pages.update(range(start & ~4095, (end + 4095) & ~4095, 4096))
        for page in pages:
            if not 0x100000 <= page < 0x100000 + length:
                u.mem_map(page, 4096)
        for section in elf.iter_sections():
            if section["sh_flags"] & 2 and section["sh_size"]:
                u.mem_write(section["sh_addr"], section.data())
        self.assert_word(CLEAR, 0xEB0091DF)  # 原 0x238820 BL
        self.assert_word(OBSERVE, 0xE3013690)
        self.assert_word(PROGRESS, 0xE1A03000)
        self.assert_word(STOP, 0xE3A00001)
        self.assert_word(0x1C437C, 0xEB000F16)  # 原定时处理调用不改
        if patched:
            for address, symbol, opcode in ((CLEAR, "farm_sync_clear_hook", 0xEB000000),
                                             (OBSERVE, "farm_sync_observe_hook", 0xEA000000),
                                             (PROGRESS, "farm_sync_progress_hook", 0xEA000000),
                                             (STOP, "farm_sync_stop_hook", 0xEA000000)):
                offset = (symbols[symbol] - address - 8) // 4
                assert -(1 << 23) <= offset < (1 << 23)
                u.mem_write(address, struct.pack("<I", opcode | (offset & 0xFFFFFF)))
        for page in (STACK, CONTROL & ~4095, TIMER & ~4095, 0x6C4000):
            u.mem_map(page, 4096)
        u.mem_write(self.out, struct.pack("<4I", magic, enabled, 0, sequence))
        u.mem_write(0x6C4DF4, struct.pack("<I", queue_handle))
        u.mem_write(TIMER, struct.pack("<3I", 100, 7, timer_control))
        u.mem_protect(TIMER & ~4095, 4096, unicorn.UC_PROT_READ)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xF << 20)
        u.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        self.clear_status, self.observed_status, self.queue_result = clear_status, observed_status, queue_result
        self.writes, self.reads, self.packets, self.record_writes = [], [], [], []
        self.phase = "none"

        def instruction(uc, address, size, context):
            if address == WRITE:
                args = [uc.reg_read(getattr(arm, "UC_ARM_REG_R" + str(i))) for i in range(4)]
                assert args[0] == CONTROL and args[1] in (0, 0x40, 3, 7, 0x302)
                assert args[2] == 0x2543E0 and args[3] in (0x139, 0x14E)
                assert uc.reg_read(arm.UC_ARM_REG_SP) % 8 == 0
                self.writes.append(tuple(args))
                uc.mem_write(CONTROL, struct.pack("<I", args[1]))
                uc.mem_write(STATUS, struct.pack("<I", self.clear_status if args[1] in (0, 0x40) else self.observed_status))
                # 显式替身只模拟原调用 ABI 和控制写入，不宣称执行了完整 MMIO wrapper。
                uc.reg_write(arm.UC_ARM_REG_R0, 0xAABB)
                uc.reg_write(arm.UC_ARM_REG_R12, 0x1122)
                uc.reg_write(arm.UC_ARM_REG_PC, uc.reg_read(arm.UC_ARM_REG_LR))
                return
            if address == QUEUE:
                args = [uc.reg_read(getattr(arm, "UC_ARM_REG_R" + str(i))) for i in range(4)]
                assert args[0] == queue_handle and args[2:] == [0, 0]
                assert uc.reg_read(arm.UC_ARM_REG_SP) % 8 == 0
                packet = bytes(uc.mem_read(args[1], 287))
                assert packet[:4] == bytes.fromhex("09000105") and not any(packet[48:])
                self.packets.append(packet)
                uc.reg_write(arm.UC_ARM_REG_R0, self.queue_result)
                uc.reg_write(arm.UC_ARM_REG_PC, uc.reg_read(arm.UC_ARM_REG_LR))
                return
            allowed = self.code + [(0x214084, 0x214110), (OBSERVE, OBSERVE + 8),
                                   (PROGRESS, PROGRESS + 4), (STOP, STOP + 4)]
            if not any(a <= address < b for a, b in allowed):
                raise RuntimeError("Unexpected instruction " + hex(address))

        def write(uc, access, address, size, value, context):
            if STACK <= address and address + size <= STACK + 4096:
                return
            if self.out <= address and address + size <= self.out + SIZE:
                self.record_writes.append((address, size))
                return
            raise RuntimeError("Candidate wrote outside its own record/stack: " + hex(address))

        def read(uc, access, address, size, value, context):
            if address >= 0x40000000:
                assert size == 4 and address in (STATUS, TIMER, TIMER + 4, TIMER + 8)
                self.reads.append(address)

        u.hook_add(unicorn.UC_HOOK_CODE, instruction)
        u.hook_add(unicorn.UC_HOOK_MEM_WRITE, write)
        u.hook_add(unicorn.UC_HOOK_MEM_READ, read)

    def assert_word(self, address, expected):
        actual = struct.unpack("<I", self.uc.mem_read(address, 4))[0]
        assert actual == expected, (hex(address), hex(actual), hex(expected))

    def registers(self):
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

    def start(self, *, caller=0x1C437C, arg0=0, mode=0):
        u = self.uc
        self.phase = "start"
        self.init_registers()
        fp, sp = STACK + 0xB04, STACK + 0x9D0
        u.mem_write(fp, struct.pack("<I", caller))
        u.mem_write(fp - 0x12D, bytes([arg0]))
        u.mem_write(fp - 0x12E, bytes([mode]))
        u.mem_write(fp - 0xC, struct.pack("<I", 0))
        u.reg_write(arm.UC_ARM_REG_R11, fp)
        u.reg_write(arm.UC_ARM_REG_SP, sp)
        u.reg_write(arm.UC_ARM_REG_LR, 0x21407C)
        u.emu_start(0x214084, 0x214110, timeout=1_000_000, count=6000)
        assert u.reg_read(arm.UC_ARM_REG_PC) == 0x214110 and u.reg_read(arm.UC_ARM_REG_SP) == sp
        return self.registers()

    def observe(self, exposure=250000):
        u = self.uc
        self.phase = "observe"
        self.init_registers()
        fp=STACK+0xB04
        u.reg_write(arm.UC_ARM_REG_R11,fp)
        u.mem_write(fp-0x74,struct.pack("<Q",exposure))
        u.reg_write(arm.UC_ARM_REG_SP, STACK + 0xC00)
        u.reg_write(arm.UC_ARM_REG_LR, 0x1C4380)
        u.emu_start(OBSERVE, OBSERVE + 8, timeout=1_000_000, count=6000)
        assert u.reg_read(arm.UC_ARM_REG_PC) == OBSERVE + 8
        return self.registers()

    def record(self):
        return struct.unpack("<89I", self.uc.mem_read(self.out, SIZE))

    def node(self, address, value=0):
        self.init_registers()
        self.uc.reg_write(arm.UC_ARM_REG_SP, STACK + 0xC00)
        self.uc.reg_write(arm.UC_ARM_REG_LR, 0x1C4380)
        self.uc.reg_write(arm.UC_ARM_REG_R0, value)
        self.uc.emu_start(address, address+4, timeout=1_000_000, count=6000)
        assert self.uc.reg_read(arm.UC_ARM_REG_PC)==address+4
        return self.registers()


class FarmSyncCaptureTests(unittest.TestCase):
    def test_control_start_and_registers_preserved(self):
        candidate, baseline = Machine(), Machine(patched=False)
        self.assertEqual(candidate.start(), baseline.start())
        self.assertEqual([v[1] for v in candidate.writes], [0x40, 3])
        self.assertEqual([v[1] for v in baseline.writes], [0, 3])
        self.assertEqual(candidate.observe(), baseline.observe())
        record = candidate.record()
        self.assertEqual(record[:4], (MAGIC, 1, 3, 1))
        self.assertEqual(record[4:13], (MAGIC, 3, 1, 7, 0x3334, 0x3734, 100, 7, 1))
        self.assertEqual(record[15:17], (1, 0))
        self.assertEqual(len(candidate.packets), 1)

    def test_same_shot_exposure_words_and_new_shot_replace(self):
        candidate=Machine()
        for exposure in (250000,500000,500001,0,0x100000001):
            candidate.start(); candidate.observe(exposure)
            self.assertEqual(candidate.record()[13:15],(exposure&0xffffffff,exposure>>32))
            self.assertEqual(struct.unpack("<2I",candidate.packets[-1][40:48]),
                             (exposure&0xffffffff,exposure>>32))

    def test_other_caller_modes_and_disabled_remain_original(self):
        for options, call in (({}, {"caller": 0x1C5244}), ({}, {"arg0": 1}), ({}, {"mode": 1}),
                              ({}, {"mode": 2}), ({"enabled": 0}, {}), ({"magic": MAGIC ^ 1}, {})):
            with self.subTest(options=options, call=call):
                candidate, baseline = Machine(**options), Machine(patched=False, **options)
                before = candidate.record()
                self.assertEqual(candidate.start(**call), baseline.start(**call))
                self.assertEqual(candidate.observe(), baseline.observe())
                self.assertEqual(candidate.writes, baseline.writes)
                self.assertEqual(candidate.record(), before)
                self.assertEqual((candidate.reads, candidate.packets, candidate.record_writes), ([], [], []))

    def test_uncleared_old_flag_does_not_become_sync(self):
        machine = Machine(clear_status=0x3734)
        machine.start(); machine.observe()
        self.assertEqual(machine.record()[7], 4)

    def test_missing_sync_does_not_become_sync(self):
        machine = Machine(observed_status=0x3334)
        machine.start(); machine.observe()
        self.assertEqual(machine.record()[7], 5)

    def test_disabled_clock_cannot_validate_timing(self):
        machine = Machine(timer_control=0)
        machine.start(); machine.observe()
        self.assertEqual(machine.record()[7], 3)
        self.assertEqual(machine.record()[10:13], (0, 0, 0))

    def test_one_attempt_per_capture_and_new_capture_advances(self):
        machine = Machine()
        machine.start(); machine.observe()
        before = machine.record(), len(machine.reads), len(machine.packets)
        machine.observe()
        self.assertEqual((machine.record(), len(machine.reads), len(machine.packets)), before)
        machine.start(); machine.observe()
        self.assertEqual(machine.record()[3], 2)
        self.assertEqual(len(machine.packets), 2)

    def test_full_or_missing_queue_never_retries(self):
        for options, packets in (({"queue_result": 0}, 1), ({"queue_handle": 0}, 0), ({"queue_handle": 3}, 0)):
            with self.subTest(options=options):
                machine = Machine(**options)
                machine.start(); machine.observe(); machine.observe()
                self.assertEqual(machine.record()[15:17], (0, 1))
                self.assertEqual(len(machine.packets), packets)

    def test_sequence_exhaustion_disables_without_clear(self):
        machine = Machine(sequence=0xFFFFFFFF)
        machine.start(); machine.observe()
        self.assertEqual(machine.record()[1:4], (0, 0, 0xFFFFFFFF))
        self.assertEqual([v[1] for v in machine.writes], [0, 3])
        self.assertEqual((machine.reads, machine.packets), ([], []))

    def test_later_nodes_preserve_abi_and_publish_once(self):
        candidate, baseline = Machine(), Machine(patched=False)
        candidate.start(); candidate.observe()
        for address, value in ((PROGRESS, 20), (PROGRESS, 100), (STOP, 0), (STOP, 0)):
            self.assertEqual(candidate.node(address,value), baseline.node(address,value))
        samples=[struct.unpack("<11I",p[4:48]) for p in candidate.packets]
        self.assertEqual([s[3] for s in samples],[7,0x107,0x107,0x207])
        self.assertEqual([s[4] for s in samples[1:]],[20,100,100])
        self.assertEqual(candidate.record()[15:17],(4,0))

    def test_progress_only_increases_and_is_bounded(self):
        machine=Machine(); machine.start(); machine.observe()
        for value in range(0,102,2):
            machine.node(PROGRESS,value); machine.node(PROGRESS,value)
            if value: machine.node(PROGRESS,value-2)
        machine.node(PROGRESS,102); machine.node(PROGRESS,0xffffffff)
        samples=[struct.unpack("<11I",p[4:48]) for p in machine.packets]
        self.assertEqual([s[4] for s in samples[1:]],list(range(0,102,2)))
        self.assertEqual(len(samples),52)

    def test_first_progress_can_skip_threshold_values(self):
        machine=Machine(); machine.start(); machine.observe()
        machine.node(PROGRESS,62); machine.node(PROGRESS,106); machine.node(STOP)
        samples=[struct.unpack("<11I",p[4:48]) for p in machine.packets]
        self.assertEqual([s[4] for s in samples[1:]],[62,106,106])

    def test_later_nodes_require_confirmed_b_and_progress(self):
        for options in ({"observed_status":0x3334},{"clear_status":0x3734},{"timer_control":0}):
            machine=Machine(**options); machine.start(); machine.observe()
            before=machine.record(),len(machine.reads),len(machine.packets)
            machine.node(PROGRESS,100); machine.node(STOP)
            self.assertEqual((machine.record(),len(machine.reads),len(machine.packets)),before)
        machine=Machine(); machine.start(); machine.observe()
        machine.node(STOP)
        self.assertEqual(len(machine.packets),1)

    def test_new_shot_resets_later_nodes_and_queue_failure_never_retries(self):
        machine=Machine(queue_result=0)
        for shot in (1,2):
            machine.start(); machine.observe(); machine.node(PROGRESS,100); machine.node(STOP)
            machine.node(PROGRESS,100); machine.node(STOP)
            self.assertEqual(machine.record()[15:17],(0,3*shot))
            self.assertEqual(len(machine.packets),3*shot)


if __name__ == "__main__":
    raise SystemExit("Provide the fixed reviewed FARM bytes explicitly; no device access.")
