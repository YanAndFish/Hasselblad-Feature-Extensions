"""无相机验证：固定命令、原厂 CRC、关联、异常即停及资源关闭。"""
import binascii
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import sutest_ram_contract as contract
from read_sutest_ram_once import attempt_once
from read_usb_link_once import UsbFailure

TOKEN = 0x71408abc


def reply(text=b"v i 1\n", *, token=TOKEN, command=52, operation=0, result=0):
    payload = bytearray(252)
    struct.pack_into("<5I", payload, 0, command, operation, token, 0, result)
    payload[20:20 + len(text)] = text
    struct.pack_into("<I", payload, 12, binascii.crc_hqx(payload[16:], 0))
    return contract.RESPONSE_HEADER + bytes(payload) + bytes(255)


class MockUsb:
    def __init__(self, replies, *, count=512, packet_size=512, fail_close=False):
        self.replies = list(replies)
        self.count, self.packet_size, self.fail_close = count, packet_size, fail_close
        self.sent = self.read = 0
        self.opened = self.initialized = False
        self.prepared = False
        self.closed = False
        self.timeouts = []

    def open(self):
        self.opened = self.initialized = True
        return {"number": 0, "alternate": 0, "class": 255, "subclass": 0, "protocol": 0,
                "pipes": [{"id": i, "type": 2, "maximumPacketSize": self.packet_size} for i in (1, 2, 129, 130)]}

    def prepare(self):
        self.prepared = True

    def write_query(self, size):
        assert self.prepared and not self.sent and size == 512
        self.sent += 1
        return self.count

    def read_reply(self, size, timeout):
        assert self.sent == 1 and self.read < 2 and size == 512 and 1 <= timeout <= 6000
        self.read += 1
        self.timeouts.append(timeout)
        packet = self.replies.pop(0)
        if isinstance(packet, Exception):
            raise packet
        return packet

    def close(self):
        self.closed = True
        return {"enumerationClosed": True, "winUsbFreed": not self.fail_close, "deviceHandleClosed": True}


class SutestTests(unittest.TestCase):
    def test_fixed_request_and_independent_crc(self):
        packet = contract.build_query(TOKEN)
        self.assertEqual(len(packet), 512)
        self.assertEqual(packet[:5], bytes.fromhex("0a 00 08 05 fc"))
        self.assertEqual(struct.unpack_from("<3I", packet, 5), (52, 0, TOKEN))
        self.assertEqual(packet[25:224], contract.COMMAND.encode("ascii"))
        self.assertEqual(packet[224:], bytes(288))
        self.assertEqual(struct.unpack_from("<I", packet, 17)[0], binascii.crc_hqx(packet[21:257], 0))
        self.assertIn("--auto-start=no --allow-interactive-authorization=no --timeout=2s call", contract.COMMAND)

    def test_token_whitelist(self):
        for value in (0, -1, 2**32, True, "52", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.build_query(value)

    def test_only_two_typed_values(self):
        for value in (0, 1):
            result = contract.parse_reply(reply(f"v i {value}\n".encode()), TOKEN)
            self.assertEqual(result.cached_value, value)
            self.assertFalse(result.freshness_verified)
            self.assertFalse(result.current_demo_mode_confirmed)

    def test_wrong_association_and_operation(self):
        for args in ({"token": TOKEN + 1}, {"command": 66}, {"operation": 4}, {"result": 1}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                contract.parse_reply(reply(**args), TOKEN)

    def test_crc_and_length_and_route(self):
        valid = reply()
        crc_bad = bytearray(valid)
        crc_bad[30] ^= 1
        bad_header = bytearray(valid)
        bad_header[2] = 1
        bad_declared = bytearray(valid)
        bad_declared[4] = 251
        for packet in (valid[:256], valid[:257], valid[:260], valid + b"\0",
                       bytes(crc_bad), bytes(bad_header), bytes(bad_declared)):
            with self.subTest(length=len(packet)), self.assertRaises(ValueError):
                contract.parse_reply(packet, TOKEN)

    def test_no_untyped_or_unexpected_output(self):
        for text in (b"i 1\n", b"v b true\n", b"v i 2\n", b"v i -1\n", b"v i 1\n\0EXTRA", b"", b"v i 1"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                contract.parse_reply(reply(text), TOKEN)

    def test_uninitialized_transport_padding_is_not_data(self):
        packet = reply()[:257] + b"X" * 255
        self.assertEqual(contract.parse_reply(packet, TOKEN).cached_value, 1)

    def test_success_one_send_one_read_and_close(self):
        transport = MockUsb([reply()])
        result = attempt_once(transport, TOKEN)
        self.assertTrue(result["ok"] and transport.closed)
        self.assertEqual((result["applicationRequestsSubmitted"], result["readCalls"]), (1, 1))
        self.assertFalse(result["rawReplySaved"])

    def test_only_one_late_farm_frame_and_shared_deadline(self):
        late = bytes.fromhex("2e02010801") + bytes(507)
        transport = MockUsb([late, reply()])
        times = iter((0, 0, 0, 1, 1))
        result = attempt_once(transport, TOKEN, clock=lambda: next(times))
        self.assertTrue(result["ok"])
        self.assertEqual(transport.timeouts, [6000, 5000])
        self.assertEqual(result["lateFarmRepliesDiscarded"], 1)
        self.assertEqual((transport.sent, transport.read), (1, 2))

    def test_unexpected_frame_or_timeout_stops_without_retry(self):
        for first in (bytes(512), reply(token=TOKEN + 1), UsbFailure("USB_READ", 121)):
            transport = MockUsb([first, reply()])
            result = attempt_once(transport, TOKEN)
            self.assertFalse(result["ok"])
            self.assertTrue(transport.closed)
            self.assertEqual((transport.sent, transport.read), (1, 1))
            self.assertNotIn("value", result)

    def test_duplicate_late_or_expired_budget_stops(self):
        late = bytes.fromhex("2e02010800") + bytes(507)
        transport = MockUsb([late, late, reply()])
        result = attempt_once(transport, TOKEN)
        self.assertFalse(result["ok"])
        self.assertEqual(transport.read, 2)
        transport = MockUsb([late, reply()])
        times = iter((0, 0, 0, 6.1, 6.1))
        result = attempt_once(transport, TOKEN, clock=lambda: next(times))
        self.assertEqual(result["error"], "USB_READ_BUDGET")
        self.assertEqual(transport.read, 1)

    def test_short_write_interface_and_close_failures(self):
        for transport, writes, reads in ((MockUsb([], count=257), 1, 0),
                                         (MockUsb([], packet_size=1024), 0, 0),
                                         (MockUsb([reply()], fail_close=True), 1, 1)):
            result = attempt_once(transport, TOKEN)
            self.assertFalse(result["ok"])
            self.assertEqual((transport.sent, transport.read), (writes, reads))
            self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
