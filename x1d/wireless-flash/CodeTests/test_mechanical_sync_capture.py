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
ELF_PATH = HERE / "build/mechanical-sync-capture/simulation.elf"
FARM = None
FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
CLEAR, OBSERVE, WRITE, QUEUE = 0x21409C, 0x1C4380, 0x238820, 0x186500
CONTROL, STATUS, TIMER, STACK = 0x42000010, 0x42000014, 0xF8F00200, 0x3000000
MAGIC, SIZE = 0x31534d47, 364
PROGRESS, STOP = 0x1C4458, 0x1C44F4


class Machine:
    def __init__(self, *, patched=True, enabled=1, magic=MAGIC, sequence=0,
                 clear_status=0x3001, observed_status=0x3c04, timer_control=1,
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
        self.out = symbols["mechanical_sync_record"]
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
        mapping=((CLEAR,0xEB0091DF,"mechanical_sync_clear_hook"),(0x21410c,0xEB0091C3,"mechanical_sync_start_hook"),
                 (0x213e60,0xEB0092CD,"mechanical_sync_status_hook"),(0x213ef8,0xEB0092A7,"mechanical_sync_status_hook"),
                 (0x2143e4,0xEB00916C,"mechanical_sync_finish_hook"))
        for address,word,symbol in mapping:
            self.assert_word(address,word)
            if patched:
                offset=(symbols[symbol]-address-8)//4
                assert -(1<<23)<=offset<(1<<23)
                u.mem_write(address,struct.pack("<I",0xEB000000|(offset&0xffffff)))
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
            if address == 0x23899c:
                assert uc.reg_read(arm.UC_ARM_REG_R0)==STATUS
                assert uc.reg_read(arm.UC_ARM_REG_SP)%8==0
                uc.reg_write(arm.UC_ARM_REG_R0,self.status_value)
                uc.reg_write(arm.UC_ARM_REG_R12,0x778899)
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
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
                                   (PROGRESS, PROGRESS + 4), (STOP, STOP + 4), (0x213e4c,0x213e64),(0x213ee4,0x213efc),(0x2143d0,0x2143e8)]
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

    def start(self, *, caller=0x1C5244, arg0=0, mode=0, parent_mode=None, source=3, parent_return=None, parent_delta=0x160):
        u = self.uc
        self.phase = "start"
        self.init_registers()
        fp, sp = STACK + 0xB04, STACK + 0x9D0
        u.mem_write(fp, struct.pack("<I", caller))
        parent=fp+parent_delta
        u.mem_write(fp-4,struct.pack("<I",parent))
        u.mem_write(parent,struct.pack("<I",parent_return if parent_return is not None else (0x1ce09c if mode==1 else 0x1ce080)))
        u.mem_write(parent-0x14d,bytes([source]))
        u.mem_write(parent-0x14e,bytes([mode if parent_mode is None else parent_mode]))
        u.mem_write(fp - 0x12D, bytes([arg0]))
        u.mem_write(fp - 0x12E, bytes([mode]))
        u.mem_write(fp - 0xC, struct.pack("<I", 0))
        u.reg_write(arm.UC_ARM_REG_R11, fp)
        u.reg_write(arm.UC_ARM_REG_SP, sp)
        u.reg_write(arm.UC_ARM_REG_LR, 0x21407C)
        u.emu_start(0x214084, 0x214110, timeout=1_000_000, count=6000)
        assert u.reg_read(arm.UC_ARM_REG_PC) == 0x214110 and u.reg_read(arm.UC_ARM_REG_SP) == sp
        return self.registers()

    def record(self):
        return struct.unpack("<91I", self.uc.mem_read(self.out, SIZE))

    def status(self, value, site=0x213e60):
        self.status_value=value
        self.init_registers()
        self.uc.reg_write(arm.UC_ARM_REG_R11, STACK+0xb04)
        self.uc.reg_write(arm.UC_ARM_REG_SP, STACK+0x9d0)
        self.uc.emu_start(site-20,site+4,timeout=1_000_000,count=6000)
        assert self.uc.reg_read(arm.UC_ARM_REG_PC)==site+4
        return self.registers()


class MechanicalSyncTests(unittest.TestCase):
    def test_modes_preserve_original_control_and_abi(self):
        for mode,control in ((0,3),(1,7)):
            c,b=Machine(),Machine(patched=False)
            self.assertEqual(c.start(mode=mode),b.start(mode=mode))
            self.assertEqual([w[1] for w in c.writes],[0x40,control])
            self.assertEqual([w[1] for w in b.writes],[0,control])
            self.assertEqual(c.record()[:4],(MAGIC,1,3,1))
            self.assertEqual(c.record()[7],0x0f07)
            self.assertEqual(c.record()[13:15],(mode,3))
            self.assertEqual(len(c.packets),1)

    def test_all_guards_reject_without_mmio_or_capture(self):
        for options,call in (({},dict(caller=0x1c437c)),({},dict(arg0=1)),({},dict(mode=2)),
                            ({},dict(source=1)),({},dict(parent_mode=1)),({},dict(parent_return=0)),
                            ({},dict(parent_delta=0x164)),(dict(enabled=0),{}),(dict(magic=MAGIC^1),{})):
            with self.subTest(options=options,call=call):
                c,b=Machine(**options),Machine(patched=False,**options)
                initial=c.record()
                self.assertEqual(c.start(**call),b.start(**call))
                self.assertEqual(c.writes,b.writes)
                self.assertEqual(c.record(),initial)
                self.assertEqual((c.reads,c.packets),([],[]))

    def test_old_flags_and_missing_edges(self):
        c=Machine(clear_status=0x3c04,observed_status=0x3c04)
        c.start()
        self.assertEqual(c.record()[7],4)
        c=Machine(clear_status=0x3001,observed_status=0x3001)
        c.start()
        self.assertEqual(c.record()[7],7)

    def test_once_per_source_and_idle_closes_window(self):
        c,b=Machine(),Machine(patched=False)
        c.start()
        for value,site in ((0x3c06,0x213e60),(0x3c06,0x213e60),(0x3c0e,0x213e60),
                           (0x3c05,0x213ef8),(0x3c0e,0x213e60)):
            self.assertEqual(c.status(value,site),b.status(value,site))
        samples=[struct.unpack('<11I',p[4:48]) for p in c.packets]
        self.assertEqual([(s[3]>>8)&127 for s in samples],[15,16,32,64])
        self.assertTrue(samples[-1][3]&0x8000)
        self.assertEqual(c.record()[2],0)
        self.assertEqual(c.record()[17],127)

    def test_finish_and_other_new_start_cancel_old_window(self):
        for action in ('finish','start'):
            c=Machine(); c.start()
            if action=='finish': c.status(0x3c04,0x2143e4)
            else: c.start(caller=0x1c437c)
            n=len(c.packets)
            c.status(0x3c0e)
            self.assertEqual(len(c.packets),n)
            self.assertEqual(c.record()[2],0)

    def test_unstable_or_disabled_clock_cannot_confirm(self):
        c=Machine(timer_control=0); c.start()
        self.assertEqual(c.record()[7],0x0f03)
        self.assertEqual(c.record()[10:13],(0,0,0))

    def test_queue_failure_has_no_retry(self):
        for options,n in ((dict(queue_result=0),1),(dict(queue_handle=0),0),(dict(queue_handle=3),0)):
            c=Machine(**options); c.start()
            c.status(0x3c04); c.status(0x3c04)
            self.assertEqual(c.record()[15:17],(0,1))
            self.assertEqual(len(c.packets),n)

    def test_new_request_numbered_and_sequence_exhaustion(self):
        c=Machine(); c.start(); c.start()
        self.assertEqual(c.record()[3],2)
        self.assertEqual(len(c.packets),2)
        c.uc.mem_write(c.out+4,struct.pack('<I',0))
        c.start(); self.assertEqual(c.record()[3],2)
        c=Machine(sequence=0xffffffff); c.start()
        self.assertEqual(c.record()[1:4],(0,0,0xffffffff))
        self.assertEqual([w[1] for w in c.writes],[0,3])

