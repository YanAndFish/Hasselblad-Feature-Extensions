"""分段装载顺序、写入白名单、解除和中途失败的离线模型。"""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest

PATH = Path(__file__).resolve().parents[1] / "research/farm_probe_loader.py"
spec = importlib.util.spec_from_file_location("probe_loader_checks", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FARM = None  # 运行者提供已核完整 SHA256 的原厂离线 bytes。


class FakeIO:
    def __init__(self, fail=None, after=False):
        self.requests, self.writes, self.closed, self.failed = 0, 0, True, False
        self.memory = {a: 0 for a in m.READ_SET}
        for a in m.CACHE_CODE + m.pre.HOOK_LINE:
            self.memory[a] = struct.unpack_from("<I", FARM, a - 0x100000)[0]
        for a, (_, expected) in m.IRQ_GUARDS.items():
            self.memory[a] = expected
        self.memory.update({m.pre.AF_R2_STATE: 0x41464f57, m.pre.AF_R2_STATE + 4: 3, m.pre.AF_R2_STATE + 8: 2})
        self.fail, self.after = fail, after
        self.trace, self.sync = [], []

    def exchange(self, kind, address=None, value=None):
        m.request(kind, address, value)
        if self.failed:
            raise AssertionError("operation attempted after failure")
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
            arg = self.memory[m.ARG]
            if self.memory[m.BASE] == struct.unpack_from("<I", m.PROBE)[0]:
                self.memory[arg] = m.PROBE_MAGIC
            else:
                assert self.memory[m.BASE] == struct.unpack_from("<I", m.THUNK)[0]
                assert self.memory[arg + 8] in (m.CLEAN_RANGE, m.INVALIDATE_RANGE)
                self.sync.append((self.memory[arg], self.memory[arg + 4], self.memory[arg + 8]))
                self.memory[arg + 12] = 1
        if self.writes == self.fail and self.after:
            self.failed = True
            raise RuntimeError("synthetic after-write failure")
        return 0

    def read(self, address):
        return self.exchange("read", address)


class MemoryRecordLoader(m.Loader):
    def __init__(self, io):
        super().__init__(io)
        self.last_saved = None

    def save(self):
        self.record.update(requests=self.io.requests, writes=self.io.writes, all_handles_closed=self.io.closed)
        self.last_saved = copy.deepcopy(self.record)


def make_loader(fail=None, after=False):
    io = FakeIO(fail, after)
    loader = MemoryRecordLoader(io)
    loader.prepare(FARM, m.HERE / "build/model-only-no-file-is-written.json")
    return loader


def installed(fail=None, after=False):
    loader = make_loader(fail, after)
    loader.probe()
    loader.install_disarmed()
    loader.arm_once()
    return loader


class ProbeLoaderTests(unittest.TestCase):
    def test_denies_af_mmu_timer_and_wrong_sgi(self):
        for address in tuple(range(0x2b2880, 0x2b3e80, 4)) + (0x2b4000, 0xf8f00208, 0x42000010):
            with self.assertRaises(ValueError):
                m.request("write", address, 0)
        with self.assertRaises(ValueError):
            m.request("write", m.SGIR, 15)
        with self.assertRaises(ValueError):
            m.request("read", m.SGIR)
        self.assertEqual(m.request("write", m.HOOK, m.NEW_HOOK)[:4], bytes.fromhex("f2000801"))

    def test_installation_order_and_scratch_restore(self):
        loader = installed()
        io = loader.io
        self.assertEqual(io.memory[m.HOOK], m.NEW_HOOK)
        self.assertEqual(io.memory[m.RECORD + 4], 1)
        self.assertEqual((io.memory[m.CB], io.memory[m.ARG]), (m.ORIG_CB, m.ORIG_ARG))
        self.assertTrue(all(io.memory[a] == 0 for a in range(m.BASE, m.BASE + 64, 4)))
        expected = [(start, size, fn) for start, size, _, _ in m.SEGMENTS for fn in (m.CLEAN_RANGE, m.INVALIDATE_RANGE)]
        self.assertEqual(io.sync[:4], expected)
        self.assertEqual(io.sync[-2:], [(m.HOOK & ~31, 32, fn) for fn in (m.CLEAN_RANGE, m.INVALIDATE_RANGE)])
        hook_index = io.trace.index((m.HOOK, m.NEW_HOOK))
        for start, data in m.load_payloads():
            for off in range(0, len(data), 4):
                self.assertIn((start + off, struct.unpack_from("<I", data, off)[0]), io.trace[:hook_index])

    def test_unhook_retains_code_and_restores_factory_entry(self):
        loader = installed()
        loader.unhook()
        io = loader.io
        self.assertEqual(io.memory[m.HOOK], m.OLD_HOOK)
        self.assertEqual(io.memory[m.RECORD + 4], 0)
        self.assertEqual((io.memory[m.CB], io.memory[m.ARG]), (m.ORIG_CB, m.ORIG_ARG))
        self.assertTrue(all(io.memory[a] == 0 for a in range(m.BASE, m.BASE + 64, 4)))
        self.assertTrue(loader.record["unreferenced_payload_retained"])
        self.assertFalse(loader.record["safe_to_overwrite_payload_without_restart"])
        self.assertEqual(io.memory[0x2b26a0], struct.unpack_from("<I", m.load_payloads()[0][1])[0])
        self.assertEqual([io.memory[m.pre.AF_R2_STATE + a] for a in (0, 4, 8)], [0x41464f57, 3, 2])

    def test_bad_irq_guard_has_no_writes(self):
        io = FakeIO()
        io.memory[0xf8f01300] = 0x8000
        loader = MemoryRecordLoader(io)
        with self.assertRaises(RuntimeError):
            loader.prepare(FARM, m.HERE / "build/model-only-no-file-is-written.json")
        self.assertEqual(io.writes, 0)

    def test_every_write_failure_stops_with_saved_inflight(self):
        normal = installed()
        total = normal.io.writes
        for after in (False, True):
            for step in range(1, total + 1):
                loader = make_loader(step, after)
                with self.assertRaises(RuntimeError):
                    loader.probe()
                    loader.install_disarmed()
                    loader.arm_once()
                self.assertTrue(loader.io.failed)
                self.assertIsNotNone(loader.last_saved["in_flight"])
                self.assertEqual(loader.io.writes, step)
                if loader.io.memory[m.HOOK] == m.NEW_HOOK:
                    for start, data in m.load_payloads():
                        for offset in range(0, len(data), 4):
                            address = start + offset
                            if address == m.RECORD + 4:
                                continue
                            self.assertEqual(loader.io.memory[address], struct.unpack_from("<I", data, offset)[0])
        print("split-loader-failure-positions:", total * 2)


if __name__ == "__main__":
    from farm_diagnostic_binary import FarmApplication
    FARM = FarmApplication().data
    unittest.main()
