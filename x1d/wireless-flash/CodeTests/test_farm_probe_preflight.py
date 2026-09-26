"""读取白名单、固定回包与失败停止的电脑端检查。"""
import importlib.util
from pathlib import Path
import struct
import unittest

PATH = Path(__file__).resolve().parents[1] / "research/farm_probe_preflight.py"
spec = importlib.util.spec_from_file_location("probe_preflight_checks", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PreflightContractTests(unittest.TestCase):
    def test_exact_messages_and_boundaries(self):
        self.assertEqual(m.request("version")[:8], bytes.fromhex("0d00080100000000"))
        self.assertEqual(m.request("read", 0x2b26a0)[:8], bytes.fromhex("f4000801a0262b00"))
        self.assertEqual(len(m.request("read", 0x2b3ffc, 1024)), 1024)
        for a in (None, True, 0, 0x2b269c, 0x2b2800, 0x2b2880, 0x2b4000, 0x42000014, 0xf8f00200):
            with self.assertRaises(ValueError):
                m.request("read", a)
        with self.assertRaises(ValueError):
            m.request("write", 0x2b26a0)

    def test_read_reply_rejects_wrong_or_failed_response(self):
        good = bytes.fromhex("f50001087856341200") + bytes(503)
        self.assertEqual(m.reply("read", good, 512), 0x12345678)
        for index in (0, 1, 2, 3, 8):
            changed = bytearray(good)
            changed[index] ^= 1
            with self.assertRaises(ValueError):
                m.reply("read", bytes(changed), 512)
        for value in (good[:-1], good + b"\0", bytearray(good)):
            with self.assertRaises(ValueError):
                m.reply("read", value, 512)

    def test_version_requires_all_three_fixed_identifiers(self):
        good = bytearray(512)
        good[:4] = bytes.fromhex("0e000108")
        for offset, value in zip((4, 68, 132), m.VERSION):
            good[offset:offset + 7] = value.encode("ascii")
        self.assertEqual(m.reply("version", bytes(good), 512), m.VERSION)
        good[132] = ord("0")
        with self.assertRaises(ValueError):
            m.reply("version", bytes(good), 512)

    def test_no_retry_after_io_failure_and_close_called(self):
        instances = []
        class Failed:
            sent = False
            def __init__(self, *args):
                self.closed = False
                instances.append(self)
            def open(self):
                raise RuntimeError("synthetic open failure")
            def close(self):
                self.closed = True
                return {"enumerationClosed": True, "winUsbFreed": True, "deviceHandleClosed": True}
        original = m.FixedReadUsb
        m.FixedReadUsb = Failed
        try:
            io = m.FixedReadIO()
            with self.assertRaises(RuntimeError):
                io.exchange("version")
            with self.assertRaises(RuntimeError):
                io.exchange("version")
            self.assertEqual(len(instances), 1)
            self.assertTrue(instances[0].closed)
            self.assertEqual(io.operations[0]["requests"], 0)
        finally:
            m.FixedReadUsb = original


if __name__ == "__main__":
    unittest.main()
