"""GFP3 原厂启动边界、双入口装入/恢复及故障停止模型；无设备访问。"""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "research/farm_capture_v3_loader.py"
spec = importlib.util.spec_from_file_location("capture_v3_loader_checks", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FARM = None
ARM_RECORD = None


class FakeIO:
    def __init__(self, fail=None, after=False):
        self.requests, self.writes, self.closed, self.failed = 0, 0, True, False
        self.memory = {a: 0 for a in m.READ_SET}
        for address in m.CACHE_CODE + m.HOOK_LINES + m.AF_CODE:
            self.memory[address] = struct.unpack_from("<I", FARM, address - 0x100000)[0]
        for address, (_, expected) in m.IRQ_GUARDS.items():
            self.memory[address] = expected
        for address in m.AF_SPEEDS:
            self.memory[address] = 5000
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
    loader.prepare(FARM, m.HERE / "build/v3-model-only-no-file-is-written.json")
    return loader


def installed(fail=None, after=False):
    loader = prepared(fail, after)
    loader.probe()
    loader.install_disarmed()
    loader.arm_once()
    return loader


class CaptureV3LoaderTests(unittest.TestCase):
    def test_real_transport_cannot_start_without_matching_offline_evidence(self):
        loader = m.Loader()
        with mock.patch.object(m, "offline_ready", return_value=False):
            with self.assertRaises(RuntimeError):
                loader.prepare(FARM, m.HERE / "build/v3-model-only-no-file-is-written.json")
        self.assertEqual((loader.io.requests, loader.io.writes), (0, 0))

    def test_fixed_write_scope_and_no_before_prepare_writes(self):
        for address, value in ((0x2B4000, 0), (0x42000010, 3), (0xF8F00208, 1),
                               (m.AF_SPEEDS[0], 20000), (0x2B26A0, 0), (m.SGIR, 15),
                               (m.PAYLOAD_START, 0xFFFFFFFF)):
            with self.subTest(address=hex(address), value=value):
                with self.assertRaises(ValueError):
                    m.request("write", address, value)
        loader = MemoryLoader(FakeIO())
        with self.assertRaises(RuntimeError):
            loader.write(m.CB, m.NOOP)
        self.assertEqual(loader.io.writes, 0)

    def test_rejects_resident_af_previous_observer_and_busy_state(self):
        for address, value in ((m.AF_SPEEDS[0], 20000), (m.AF_ENTRY_POINTS[0], 0),
                               (0x2B26A0, 1), (0x2B3E80, 1), (m.PAYLOAD_START, 1),
                               (m.pre.AF_IDLE, 1), (0xF8F01300, 0x8000)):
            with self.subTest(address=hex(address)):
                io = FakeIO()
                io.memory[address] = value
                loader = MemoryLoader(io)
                with self.assertRaises(RuntimeError):
                    loader.prepare(FARM, m.HERE / "build/v3-model-only-no-file-is-written.json")
                self.assertEqual(io.writes, 0)

    def test_payload_precedes_both_hooks_and_arm(self):
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

    def test_reads_actual_arm_model_record_and_keeps_no_physical_claim(self):
        loader = installed()
        self.assertEqual(len(ARM_RECORD), 29)
        for index, value in enumerate(ARM_RECORD):
            loader.io.memory[m.RECORD + index * 4] = value
        before = loader.io.requests, loader.io.writes
        result = loader.read_record()
        self.assertEqual(loader.io.requests - before[0], 31)
        self.assertEqual(loader.io.writes, before[1])
        self.assertEqual(result["encoding_snapshot"]["input_exposure_us"], 1_000_000)
        self.assertEqual(result["encoding_snapshot"]["encoded_r"], 4366)
        self.assertFalse(result["physical_integration_event_verified"])
        self.assertEqual(loader.last_saved["capture_raw"]["words"], list(ARM_RECORD))

    def test_restores_both_hooks_and_retains_payload(self):
        loader = installed()
        loader.unhook()
        io = loader.io
        self.assertEqual({a: io.memory[a] for a in m.ORIGINAL_HOOKS}, m.ORIGINAL_HOOKS)
        self.assertEqual((io.memory[m.CB], io.memory[m.ARG]), (m.ORIG_CB, m.ORIG_ARG))
        self.assertTrue(all(io.memory[a] == 0 for a in range(m.BASE, m.BASE + 64, 4)))
        self.assertEqual(io.memory[m.PAYLOAD_START], struct.unpack_from("<I", m.payload())[0])
        self.assertEqual(io.memory[m.RECORD + 4], 0)
        self.assertFalse(loader.record["safe_to_overwrite_payload_without_restart"])
        self.assertEqual([io.memory[a] for a in m.AF_SPEEDS], [5000] * 3)
        for address in m.AF_CODE:
            self.assertEqual(io.memory[address], struct.unpack_from("<I", FARM, address - 0x100000)[0])

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
                    loader.arm_once()
                    loader.unhook()
                self.assertTrue(loader.io.failed)
                self.assertEqual(loader.io.writes, step)
                self.assertIsNotNone(loader.last_saved["in_flight"])
                self.assertEqual([loader.io.memory[a] for a in m.AF_SPEEDS], [5000] * 3)
        print("GFP3 installation/restoration failure positions:", total * 2)


if __name__ == "__main__":
    raise SystemExit("Provide the fixed FARM and the actual offline ARM record explicitly.")
