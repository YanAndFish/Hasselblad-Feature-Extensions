"""人工构造的正常/异常回复；不打开设备，不执行原厂固件。"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from usb_diagnostic_contract import build_fx3_link_query, parse_fx3_link_reply


class Fx3LinkContractTests(unittest.TestCase):
    def test_single_request_and_zero_padding_at_each_speed(self):
        for size in (64, 512, 1024):
            with self.subTest(size=size):
                packet = build_fx3_link_query(size)
                self.assertEqual(len(packet), size)
                self.assertEqual(packet[:5], b"\x71\x04\x08\x09\x00")
                self.assertEqual(packet[5:], bytes(size - 5))

    def test_only_getter_reachable_states(self):
        for size in (64, 512, 1024):
            for flags, active, superspeed in ((0, False, False), (1, True, False), (3, True, True)):
                with self.subTest(size=size, flags=flags):
                    packet = b"\x72\x04\x09\x08" + struct.pack("<I", flags) + bytes(size - 8)
                    self.assertEqual(asdict(parse_fx3_link_reply(packet, size)),
                                     {"flags": flags, "link_active": active, "super_speed": superspeed})

    def test_unknown_kind_or_node_is_rejected_without_echo(self):
        for header in (b"\x73\x04\x09\x08", b"\x72\x04\x03\x08", b"\x72\x04\x09\x05"):
            with self.subTest(header=header):
                with self.assertRaisesRegex(ValueError, "白名单"):
                    parse_fx3_link_reply(header + bytes(60), 64)

    def test_unknown_states_are_rejected(self):
        for flags in (2, 4, 0x10000001, 0xffffffff):
            with self.subTest(flags=flags):
                packet = b"\x72\x04\x09\x08" + struct.pack("<I", flags) + bytes(56)
                with self.assertRaisesRegex(ValueError, "未定义"):
                    parse_fx3_link_reply(packet, 64)

    def test_truncation_extra_data_and_invalid_types_are_rejected(self):
        for packet in (b"", bytes(8), bytes(63), bytes(65), bytearray(64), "x" * 64):
            with self.subTest(length=len(packet), kind=type(packet).__name__):
                with self.assertRaisesRegex(ValueError, "长度"):
                    parse_fx3_link_reply(packet, 64)

    def test_invalid_packet_sizes_are_rejected(self):
        for size in (0, 5, 256, 2048, True, 64.0, "64"):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    build_fx3_link_query(size)
                with self.assertRaises(ValueError):
                    parse_fx3_link_reply(bytes(64), size)

    def test_opaque_padding_is_not_retained(self):
        marker = b"synthetic-opaque-padding"
        packet = b"\x72\x04\x09\x08\x01\x00\x00\x00" + (marker * 3)[:56]
        result = parse_fx3_link_reply(packet, 64)
        self.assertEqual(asdict(result), {"flags": 1, "link_active": True, "super_speed": False})
        self.assertNotIn("padding", repr(result))


if __name__ == "__main__":
    unittest.main()
