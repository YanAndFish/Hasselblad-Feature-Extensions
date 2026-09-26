"""固定已安装候选的原厂分发/封包/发送入口验证；不访问设备。"""
import hashlib, json, struct, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
COMMON = HERE.parent
ROOT = COMMON.parents[2]
assert Path.cwd().resolve() == ROOT
sys.path[:0] = [str(ROOT/'x1d/tools'), str(ROOT/'.research-cache/x1d-1.25.0/python')]
from binary import ArmElf
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
FARM = FarmApplication()
BUILD = COMMON/'delivery-r3/build/003577c0'
MANIFEST = json.loads((BUILD/'capture-manifest.json').read_text(encoding='utf-8'))
PAYLOAD = (BUILD/'candidate.bin').read_bytes()
BUS_PATH = ROOT/'.research-cache/x1d-1.25.0/usb-diagnostic-inputs/usr/bin/msg2dbus'
MSG_PATH = ROOT/'.research-cache/x1d-1.25.0/usb-diagnostic-inputs/usr/lib/libAppsMessaging.so'
BUS, MSG = ArmElf(BUS_PATH.read_bytes()), ArmElf(MSG_PATH.read_bytes())
assert FARM.sha256 == '317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
assert hashlib.sha256(PAYLOAD).hexdigest() == '23d3bc18b47d873e70de13242b4c69e81aa3f65d9aa66c25b97fcda3b2ca7556'
assert hashlib.sha256(BUS.data).hexdigest() == '988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1'

def word(n): return struct.pack('<I', n & 0xffffffff)
def hash32(b):
    h = 2166136261
    for x in b: h = ((h ^ x) * 16777619) & 0xffffffff
    return h
def query():
    p = bytearray(255)
    p[:24] = struct.pack('<6I', 0x414c4248, 0x21335346, 3, 1, 123, 456)
    p[251:] = word(hash32(p[:251]))
    return b'\x0f\x03\x05\x01\0\xff' + p

class FarmMachine:
    def __init__(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x100000, 0x600000)
        self.u.mem_write(0x100000, FARM.data)
        self.u.mem_write(MANIFEST['base'], PAYLOAD)
        self.u.mem_map(0x900000, 0x10000)
        for a, old, new in MANIFEST['emulatorOnlyHooks']:
            assert FARM.word(a) == old
            self.u.mem_write(a, word(new))
        self.u.mem_write(0x2adc79, b'\x12')
        self.u.mem_write(0x6bb46c, b'\x02')
        self.u.mem_write(0x6c4df4, word(0x906000))
        self.u.mem_write(0x2ae064, b'\0')
        self.replies, self.visited = [], set()
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        self.call(MANIFEST['symbols']['na_begin'], 1)

    def hook(self, u, a, size, _):
        if a in (0x1e20b8, 0x1e22b4, MANIFEST['symbols']['as_receive'] & ~1, 0x1e0a50, 0x1e80d0):
            self.visited.add(a)
        if a == 0x1e2368:
            u.emu_stop()
        elif a == 0x186500:
            # 原厂发送函数正常入队边界。只替代 RTOS 队列，不替代封包/发送函数。
            assert u.reg_read(UC_ARM_REG_R0) == 0x906000
            p = u.reg_read(UC_ARM_REG_R1)
            self.replies.append(bytes(u.mem_read(p, 259)))
            u.reg_write(UC_ARM_REG_R0, 1)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        elif a == 0x236a14:
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        elif a == 0x2209f4:
            raise AssertionError('factory assertion')

    def call(self, address, *args):
        u = self.u
        u.reg_write(UC_ARM_REG_CPSR, 0x1f)
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xf << 20)
        u.reg_write(UC_ARM_REG_FPEXC, 1 << 30)
        u.reg_write(UC_ARM_REG_SP, 0x90fc00)
        u.reg_write(UC_ARM_REG_R11, 0x90fde0)
        u.reg_write(UC_ARM_REG_LR, 0x900000)
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(r, v)
        u.emu_start(address, 0x900000, count=300000)
        assert u.reg_read(UC_ARM_REG_PC) in (0x900000, 0x1e2368)

class OriginalChainTests(unittest.TestCase):
    def test_installed_query_traverses_original_dispatch_builder_and_send(self):
        m = FarmMachine()
        bank = MANIFEST['symbols']['na_config_bank']
        before = bytes(m.u.mem_read(bank, 100))
        m.u.mem_write(0x6c37f4, query())
        m.call(0x1e20b8)
        self.assertEqual(len(m.replies), 1)
        self.assertEqual(m.visited, {0x1e20b8, 0x1e22b4, MANIFEST['symbols']['as_receive'] & ~1, 0x1e0a50, 0x1e80d0})
        r = m.replies[0]
        self.assertEqual(r[:12], b'\x10\x03\x01\x05HBLAFR3!')
        self.assertEqual(struct.unpack_from('<6I', r, 12), (3, 0x80000001, 123, 456, 0, 1))
        self.assertEqual(r[255:], word(hash32(r[4:255])))
        self.assertEqual(bytes(m.u.mem_read(bank, 100)), before)

    def test_original_message_lengths_and_node_identity(self):
        self.assertEqual(MSG.word(0x4adf8234+783*4), 257)
        self.assertEqual(MSG.word(0x4adf8234+784*4), 255)
        self.assertEqual(len(query()), 257+4)
        self.assertEqual(MSG.read(MSG.word(0x4ae1600c+1*4), 5), b'farm\0')
        self.assertEqual(MSG.read(MSG.word(0x4ae1600c+5*4), 4), b'iMX\0')

    def test_original_uart_send_can_reject_even_when_slot_exists(self):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.mem_map(0x10000, 0x80000)
        for seg in BUS.elf.iter_segments():
            if seg['p_type']=='PT_LOAD': u.mem_write(seg['p_vaddr'], seg.data())
        u.mem_map(0x900000, 0x10000)
        # 执行原厂 SendMessage；仅替代 mutex 和 writer queue。状态不就绪时不访问 queue。
        queued = []
        def stub(uc, a, size, _):
            if a in (0x19134, 0x19278, 0x1dd50):
                if a == 0x1dd50: queued.append(1); uc.reg_write(UC_ARM_REG_R0, 1)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE, stub)
        for state, result, n in ((0,0,0), (1,1,1), (2,0,1)):
            u.mem_write(0x90102c, word(state))
            u.reg_write(UC_ARM_REG_R0, 0x901000)
            u.reg_write(UC_ARM_REG_R1, 0x902000)
            u.reg_write(UC_ARM_REG_SP, 0x90ff00)
            u.reg_write(UC_ARM_REG_LR, 0x900000)
            u.emu_start(0x1de1c, 0x900000, count=1000)
            self.assertEqual(u.reg_read(UC_ARM_REG_R0), result)
            self.assertEqual(len(queued), n)

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OriginalChainTests))
    report = {'passed': result.wasSuccessful(), 'tests': result.testsRun, 'hardwareRequests': 0,
        'farmSha256': FARM.sha256, 'payloadSha256': hashlib.sha256(PAYLOAD).hexdigest(),
        'msg2dbusSha256': hashlib.sha256(BUS.data).hexdigest(), 'messagingSha256': hashlib.sha256(MSG.data).hexdigest(),
        'testSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': '实际已安装 ARM 候选与原厂 FARM dispatcher/header/send；原厂 UART SendMessage 返回值；固定消息长度/节点',
        'stubs': ['FARM日志开关', 'FARM RTOS发送队列', 'Qt mutex', 'UART writer queue'],
        'liveSocketOrUartVerified': False, 'timeoutRootCauseConfirmed': False}
    (HERE/'original-chain-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
