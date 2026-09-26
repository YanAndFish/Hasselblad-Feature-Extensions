"""执行修正版 ARM connect interposer；Qt/文件系统为替身，禁止设备与消息发送。"""
import hashlib, io, json, os, struct, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / '.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

CONNECT = '_ZN7QObject11connectImplEPKS_PPvS1_S3_PN9QtPrivate15QSlotObjectBaseEN2Qt14ConnectionTypeEPKiPK11QMetaObject'
LIB = HERE / 'bus-startup-r2/linux-build/libhbl-af-bus.so'
ORIGINAL = ROOT / '.research-cache/x1d-1.25.0/usb-diagnostic-inputs/usr/bin/msg2dbus'

class ArmConnect:
    def __init__(self, enabled=True, connected=True, destroyed=False):
        self.enabled, self.connected, self.destroyed = enabled, connected, destroyed
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
        self.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.bias = 0x1000000
        self.u.mem_map(self.bias, 0x50000)
        self.u.mem_map(0x2000000, 0x10000)
        self.u.mem_map(0x3000000, 0x100000)
        self.u.mem_map(0x4000000, 0x10000)
        self.elf = ELFFile(io.BytesIO(LIB.read_bytes()))
        for seg in self.elf.iter_segments():
            if seg['p_type'] == 'PT_LOAD':
                self.u.mem_write(self.bias + seg['p_vaddr'], seg.data())
        self.names, self.stubs, self.symbols = {}, {}, {}
        syms = self.elf.get_section_by_name('.dynsym')
        for s in syms.iter_symbols():
            if not s.name:
                continue
            self.symbols[s.name] = self.stub(s.name) if s['st_shndx'] == 'SHN_UNDEF' else self.bias + s['st_value']
        for name in ('.rel.dyn', '.rel.plt'):
            for rel in self.elf.get_section_by_name(name).iter_relocations():
                a, kind = self.bias + rel['r_offset'], rel['r_info_type']
                symbol = syms.get_symbol(rel['r_info_sym']).name
                if kind == 23:
                    value = self.word(a) + self.bias
                elif kind in (21, 22):
                    value = self.symbols[symbol]
                elif kind == 2:
                    value = self.symbols[symbol] + self.word(a)
                else:
                    raise AssertionError('unhandled relocation ' + str(kind))
                self.put(a, value)
        self.original = self.stub('original-connect')
        self.meta_function = self.stub('fake-meta')
        self.errno, self.text, self.owner, self.other = 0x3000000, 0x3000010, 0x3000100, 0x3000200
        self.message_meta, self.uart_meta = 0x3000300, 0x3000340
        self.weak = 0x3000400
        self.u.mem_write(self.text, b'1\0')
        self.put(0x3000500, self.meta_function)
        self.put(self.owner, 0x3000500)
        self.put(self.other, 0x3000500)
        self.put(self.weak, 100)
        self.put(self.weak + 4, 0xffffffff)
        self.heap = 0x3010000
        self.calls, self.queues, self.refs = [], [], []
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def stub(self, name):
        if name not in self.names:
            address = 0x2000000 + 4 * len(self.names)
            self.names[name] = address
            self.stubs[address] = name
            self.u.mem_write(address, bytes.fromhex('1eff2fe1'))
        return self.names[name]

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def put(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def string(self, address):
        out = bytearray()
        while address and self.u.mem_read(address, 1) != b'\0':
            out += self.u.mem_read(address, 1)
            address += 1
        return out.decode('ascii')

    def hook(self, u, address, size, _):
        if address not in self.stubs:
            return
        name = self.stubs[address]
        r = [u.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        sp = u.reg_read(UC_ARM_REG_SP)
        value = 0
        if name == '__errno_location':
            value = self.errno
        elif name == 'getenv':
            self.assert_env = self.string(r[0])
            assert self.assert_env == 'HBL_AF_SETTINGS_ENABLE'
            value = self.text if self.enabled else 0
        elif name == 'strcmp':
            value = int(self.string(r[0]) != self.string(r[1]))
        elif name == 'dlsym':
            symbol = self.string(r[1])
            choices = {CONNECT: self.original,
                '_ZN19MessageIO_Interface16staticMetaObjectE': self.message_meta,
                '_ZN14MessageIO_UART16staticMetaObjectE': self.uart_meta}
            assert symbol in choices, symbol
            value = choices[symbol]
        elif name == 'fake-meta':
            value = self.uart_meta if r[0] == self.owner else self.message_meta
        elif name.endswith('ExternalRefCountData9getAndRefEPK7QObject'):
            self.refs.append(r[0])
            value = self.weak
        elif name == 'original-connect':
            args = r + [self.word(sp + 4 * i) for i in range(5)]
            self.calls.append(args)
            self.put(r[0], 0xbeef if self.connected else 0)
            if self.destroyed:
                self.put(self.weak + 4, 0)
            self.put(self.errno, 77)
            value = r[0]
        elif name.endswith('Connection18isConnected_helperEv'):
            value = int(self.word(r[0]) != 0)
        elif name in ('_ZN11QMetaObject10ConnectionD1Ev', '_ZdlPv'):
            pass
        elif name == '__lxstat64':
            assert r[0] == 3
            self.put(self.errno, 2)
            value = 0xffffffff  # 没有真实目录，诊断文件写入不会运行。
        elif name == '_Znwj':
            value = self.heap
            self.heap += (r[0] + 15) & ~15
        elif name == '_ZN6QTimer14singleShotImplEiN2Qt9TimerTypeEPK7QObjectPN9QtPrivate15QSlotObjectBaseE':
            self.queues.append(r)
        else:
            raise AssertionError('unexpected external action: ' + name)
        u.reg_write(UC_ARM_REG_R0, value)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def call(self, match=True):
        self.put(self.errno, 33)
        output = 0x3000600
        args = [output, self.other, 0x111111, self.owner if match else self.other,
                0x222222, 0x333333, 2, 0x444444, 0x555555]
        sp = 0x400f000
        for i, value in enumerate(args[4:]):
            self.put(sp + i * 4, value)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args[:4]):
            self.u.reg_write(reg, value)
        self.u.reg_write(UC_ARM_REG_SP, sp)
        self.u.reg_write(UC_ARM_REG_LR, 0x200f000)
        self.u.emu_start(self.symbols[CONNECT], 0x200f000, count=200000)
        assert self.u.reg_read(UC_ARM_REG_PC) == 0x200f000
        assert self.u.reg_read(UC_ARM_REG_SP) == sp
        assert self.calls[0] == args  # 包括非平凡 Connection 隐藏返回参数和五个栈参数。
        assert self.word(output) == (0xbeef if self.connected else 0)
        assert self.word(self.errno) == 77

class StartupTests(unittest.TestCase):
    def test_fixed_factory_meta_slots_and_startup_connection_calls(self):
        raw = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1')
        elf = ELFFile(io.BytesIO(raw))
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.dynsym').iter_symbols()}
        self.assertEqual(symbols['_ZN19MessageIO_Interface16staticMetaObjectE'], 0x7e32c)
        self.assertEqual(symbols['_ZN14MessageIO_UART16staticMetaObjectE'], 0x7e418)
        def read(a, n):
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD' and seg['p_vaddr'] <= a and a+n <= seg['p_vaddr']+seg['p_filesz']:
                    return seg.data()[a-seg['p_vaddr']:a-seg['p_vaddr']+n]
            raise ValueError(hex(a))
        self.assertEqual(struct.unpack('<I', read(0x7e418, 4))[0], 0x7e32c)
        for meta in (0x7e32c, 0x7e418):
            _, strings, table = struct.unpack('<3I', read(meta, 12))
            values = struct.unpack('<38I', read(table, 152))
            found = False
            for i in range(values[4]):
                name, argc, params, tag, flags = values[values[5]+5*i:values[5]+5*i+5]
                header = strings + name*16
                _, length, _, offset = struct.unpack('<4I', read(header, 16))
                if read(header + offset, length) == b'SendMessage':
                    self.assertEqual((argc, flags & 0xc, values[params], values[params+1]), (1, 8, 1, 12))
                    found = True  # slot, bool 返回、QByteArray 入参。
            self.assertTrue(found)
        for call in (0x1cd58, 0x1cde8):
            word = struct.unpack('<I', read(call, 4))[0]
            self.assertEqual(word >> 24, 0xeb)
            delta = word & 0xffffff
            if delta & 0x800000:
                delta -= 0x1000000
            self.assertEqual(call + 8 + delta*4, 0x18720)

    def test_disabled_forwards_original_abi_and_errno(self):
        m = ArmConnect(enabled=False)
        m.call()
        self.assertEqual(len(m.calls), 1)
        self.assertFalse(m.queues)
        self.assertFalse(m.refs)

    def test_unrelated_object_does_not_schedule(self):
        m = ArmConnect()
        m.call(match=False)
        self.assertEqual(len(m.calls), 1)
        self.assertFalse(m.queues)

    def test_existing_uart_connection_schedules_without_any_signal(self):
        m = ArmConnect()
        m.call()
        self.assertEqual(len(m.calls), 2)  # 原连接 + 自己的 destroyed 生命周期连接。
        self.assertEqual(len(m.queues), 1)
        self.assertEqual(m.queues[0][0], 0)
        self.assertEqual(m.queues[0][2], m.owner)

    def test_failed_connection_or_destroyed_owner_does_not_schedule(self):
        for kwargs in ({'connected': False}, {'destroyed': True}):
            m = ArmConnect(**kwargs)
            m.call()
            self.assertEqual(len(m.calls), 1)
            self.assertFalse(m.queues)

    def test_repeated_connections_do_not_duplicate_owner_initialization(self):
        m = ArmConnect()
        m.call()
        m.call()
        self.assertEqual(len(m.calls), 3)
        self.assertEqual(len(m.queues), 1)

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StartupTests))
    paths = [Path(__file__), HERE / 'bus-startup-r2/settings_bus.cpp', HERE / 'bus-startup-r2/build_bus.py', LIB, ORIGINAL]
    report = {'passed': result.wasSuccessful(), 'tests': result.testsRun, 'hardwareRequests': 0,
        'scope': '真实 ARM interposer 转发 ABI/errno、无信号发现、无关对象和失败/销毁保护；Qt/文件系统替身',
        'targetQtEventLoopVerified': False, 'backendBindVerified': False,
        'files': {os.path.relpath(p, HERE): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (HERE / 'bus-startup-r2/startup-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
