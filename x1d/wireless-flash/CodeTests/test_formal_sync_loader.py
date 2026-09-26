"""HFS1 原厂启动边界、八入口装入/恢复及故障停止模型；无设备访问。"""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "research/formal_sync_loader.py"
spec = importlib.util.spec_from_file_location("sync_loader_checks", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FARM = None
ARM_RECORD = None


class FakeIO:
    def __init__(self, fail=None, after=False):
        self.requests, self.writes, self.closed, self.failed = 0, 0, True, False
        self.memory = {a: 0 for a in m.READ_SET}
        for address in m.CACHE_CODE + m.HOOK_LINES + (0x214110, 0x233C7C):
            self.memory[address] = struct.unpack_from("<I", FARM, address - 0x100000)[0]
        for address, (_, expected) in m.IRQ_GUARDS.items():
            self.memory[address] = expected
        self.fail, self.after = fail, after
        self.trace, self.sync = [], []

    def exchange(self, kind, address=None, value=None):
        m.request(kind, address, value)
        if self.failed:
            raise AssertionError("operation after ambiguous failure")
        self.requests += 1
        if kind == "version":
            return m.pre.VERSION
        if kind == "read":
            return self.memory[address]
        self.writes += 1
        if self.writes == self.fail and not self.after:
            self.failed = True
            raise RuntimeError("synthetic before-write failure")
        self.trace.append((address, value))
        if address != m.SGIR:
            self.memory[address] = value
        elif self.memory[m.CB] == m.BASE:
            argument = self.memory[m.ARG]
            if self.memory[m.BASE] == struct.unpack_from("<I", m.PROBE)[0]:
                self.memory[argument] = m.PROBE_MAGIC
            else:
                assert self.memory[m.BASE] == struct.unpack_from("<I", m.THUNK)[0]
                assert self.memory[argument + 8] in (m.CLEAN_RANGE, m.INVALIDATE_RANGE)
                self.sync.append((self.memory[argument], self.memory[argument + 4], self.memory[argument + 8]))
                self.memory[argument + 12] = 1
        if self.writes == self.fail and self.after:
            self.failed = True
            raise RuntimeError("synthetic after-write failure")
        return 0

    def read(self, address):
        return self.exchange("read", address)


class MemoryLoader(m.Loader):
    def __init__(self, io):
        super().__init__(io)
        self.last_saved = None

    def save(self):
        self.record.update(requests=self.io.requests, writes=self.io.writes, all_handles_closed=self.io.closed)
        self.last_saved = copy.deepcopy(self.record)


def prepared(fail=None, after=False):
    loader = MemoryLoader(FakeIO(fail, after))
    loader.prepare(FARM, m.HERE / "build/sync-model-only-no-file-is-written.json")
    return loader


def installed(fail=None, after=False):
    loader = prepared(fail, after)
    loader.probe()
    loader.install_disarmed()
    loader.arm()
    return loader


class SyncLoaderTests(unittest.TestCase):
    def test_real_transport_cannot_start_without_matching_offline_evidence(self):
        loader = m.Loader()
        with mock.patch.object(m, "offline_ready", return_value=False):
            with self.assertRaises(RuntimeError):
                loader.prepare(FARM, m.HERE / "build/sync-model-only-no-file-is-written.json")
        self.assertEqual((loader.io.requests, loader.io.writes), (0, 0))

    def test_af_reserved_memory_and_existing_af_remain_untouched(self):
        io=FakeIO()
        unrelated={a:0x41460000+(a&0xffff) for a in range(0x2b3400,0x2b3f40,4)}
        unrelated.update({0x2adc2c:3800,0x2adc30:3800,0x6bc9b0:3800,0x19bb94:0xea012345})
        self.assertFalse(set(unrelated)&set(m.READ_SET))
        self.assertFalse(set(unrelated)&set(m.WRITE_VALUES))
        io.memory.update(unrelated)
        loader=MemoryLoader(io)
        loader.prepare(FARM,m.HERE/'build/formal-model-only-no-file-is-written.json')
        loader.probe();loader.install_disarmed();loader.arm();loader.unhook()
        self.assertEqual({a:io.memory[a] for a in unrelated},unrelated)
        self.assertFalse(any(a in unrelated for a,v in io.trace))

    def test_fixed_write_scope_and_no_before_prepare_writes(self):
        for address, value in ((0x2B4000, 0), (0x42000010, 3), (0xF8F00208, 1),
                               (0x2adc2c, 20000), (0x2B26A0, 0), (0x2b3400, 0), (0x2b3f40, 0), (m.SGIR, 15),
                               (m.PAYLOAD_START, 0xFFFFFFFF)):
            with self.subTest(address=hex(address), value=value):
                with self.assertRaises(ValueError):
                    m.request("write", address, value)
        loader = MemoryLoader(FakeIO())
        with self.assertRaises(RuntimeError):
            loader.write(m.CB, m.NOOP)
        self.assertEqual(loader.io.writes, 0)

    def test_rejects_occupied_own_arena_changed_hook_or_busy(self):
        for address,value in ((m.PAYLOAD_START,1),(m.RECORD,0x31534d47),(m.BASE,1),
                              (next(iter(m.NEW_HOOKS)),0),(m.pre.AF_IDLE,1),(0xf8f01300,0x8000)):
            io=FakeIO();io.memory[address]=value;loader=MemoryLoader(io)
            with self.assertRaises(RuntimeError):
                loader.prepare(FARM,m.HERE/'build/formal-model-only-no-file-is-written.json')
            self.assertEqual(io.writes,0)

    def test_payload_precedes_all_hooks_and_arm(self):
        loader = installed()
        io = loader.io
        for address, value in m.NEW_HOOKS.items():
            self.assertEqual(io.memory[address], value)
            index = io.trace.index((address, value))
            for offset in range(0, m.PAYLOAD_BYTES, 4):
                expected = struct.unpack_from("<I", m.payload(), offset)[0]
                self.assertIn((m.PAYLOAD_START + offset, expected), io.trace[:index])
        self.assertEqual(io.trace[-1], (m.RECORD + 4, 1))
        self.assertEqual(io.sync, [(start, size, fn) for start, size in m.CACHE_RANGES
                                   for fn in (m.CLEAN_RANGE, m.INVALIDATE_RANGE)])
        self.assertEqual((io.memory[m.CB], io.memory[m.ARG]), (m.ORIG_CB, m.ORIG_ARG))
        self.assertTrue(all(io.memory[a] == 0 for a in range(m.BASE, m.BASE + 64, 4)))

    def test_restores_all_hooks_and_retains_payload(self):
        loader = installed()
        loader.unhook()
        io = loader.io
        self.assertEqual({a: io.memory[a] for a in m.ORIGINAL_HOOKS}, m.ORIGINAL_HOOKS)
        self.assertEqual((io.memory[m.CB], io.memory[m.ARG]), (m.ORIG_CB, m.ORIG_ARG))
        self.assertTrue(all(io.memory[a] == 0 for a in range(m.BASE, m.BASE + 64, 4)))
        self.assertEqual(io.memory[m.PAYLOAD_START], struct.unpack_from("<I", m.payload())[0])
        self.assertEqual(io.memory[m.RECORD + 4], 0)
        self.assertFalse(loader.record["safe_to_overwrite_payload_without_restart"])

    def test_each_install_and_restore_write_failure_stops(self):
        reference = installed()
        reference.unhook()
        total = reference.io.writes
        for after in (False, True):
            for step in range(1, total + 1):
                loader = prepared(step, after)
                with self.assertRaises(RuntimeError):
                    loader.probe()
                    loader.install_disarmed()
                    loader.arm()
                    loader.unhook()
                self.assertTrue(loader.io.failed)
                self.assertEqual(loader.io.writes, step)
                self.assertIsNotNone(loader.last_saved["in_flight"])
        print("HFS1 installation/restoration failure positions:", total * 2)


if __name__ == "__main__":
    raise SystemExit("Provide the fixed FARM and the actual offline ARM record explicitly.")
