"""FARM getter 的白名单、停止边界与脱敏；仅人工数据和替身。"""
import ctypes as c
from dataclasses import asdict
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from farm_ram_contract import build_farm_ram_query, parse_farm_ram_reply
from read_farm_ram_once import FarmRamWinUsb, UsbFailure, U32, attempt_once, main


def interface(size=512):
    return {"number": 2 if size == 64 else 0, "alternate": 0, "class": 255,
            "subclass": 0, "protocol": 0, "pipes": [
                {"id": ident, "type": 2, "maximumPacketSize": size} for ident in (1, 2, 129, 130)]}


class FakeTransport:
    def __init__(self, failure=None, value=1, mismatch=False, short=False, info=None, close_failure=False):
        self.failure, self.value, self.mismatch, self.short = failure, value, mismatch, short
        self.info, self.close_failure = interface() if info is None else info, close_failure
        self.opened = self.initialized = self.sent = self.read = False
        self.calls = []

    def fail(self, stage):
        self.calls.append(stage)
        if self.failure == stage:
            raise UsbFailure("FAKE_" + stage.upper(), 121)

    def open(self):
        self.opened = True
        self.fail("open")
        self.initialized = True
        return self.info

    def prepare(self):
        self.fail("prepare")

    def write_query(self, size):
        self.sent = True
        self.fail("write")
        return size - 1 if self.short else size

    def read_reply(self, size):
        self.read = True
        self.fail("read")
        header = bytes.fromhex("30 02 01 08" if self.mismatch else "2e 02 01 08")
        return header + bytes([self.value]) + bytes([0xA5]) * (size - 5)

    def close(self):
        self.calls.append("close")
        return {"enumerationClosed": True, "winUsbFreed": not self.close_failure, "deviceHandleClosed": True}


class ContractTests(unittest.TestCase):
    def test_exact_getter_only_with_zero_padding(self):
        for size in (64, 512, 1024):
            self.assertEqual(build_farm_ram_query(size), bytes.fromhex("2d 02 08 01 00") + bytes(size - 5))
        with self.assertRaises(TypeError):
            build_farm_ram_query(512, 559)

    def test_unreviewed_slot_sizes_are_rejected(self):
        for size in (0, 5, 63, 65, 511, 513, 1025, True, "512", 512.0):
            with self.subTest(size=size), self.assertRaises(ValueError):
                build_farm_ram_query(size)

    def test_only_two_values_are_returned_without_padding(self):
        for size in (64, 512, 1024):
            for value in (0, 1):
                packet = bytes.fromhex("2e 02 01 08") + bytes([value]) + bytes([0xA5]) * (size - 5)
                self.assertEqual(asdict(parse_farm_ram_reply(packet, size)), {
                    "reported_value": value, "ram_mode_reported_active": value == 1})

    def test_direction_message_and_all_unknown_values_rejected(self):
        variants = [bytes.fromhex(header) + b"\x01" for header in (
            "30 02 01 08", "2e 02 08 01", "72 04 09 08", "2e 02 03 08", "2e 02 01 05")]
        variants += [bytes.fromhex("2e 02 01 08") + bytes([value]) for value in range(2, 256)]
        for prefix in variants:
            with self.assertRaises(ValueError):
                parse_farm_ram_reply(prefix + bytes(507), 512)

    def test_short_long_and_nonbytes_packets_rejected(self):
        packet = bytes.fromhex("2e 02 01 08 01") + bytes(507)
        for wrong in (packet[:-1], packet + b"\0", bytearray(packet), "", None):
            with self.assertRaises(ValueError):
                parse_farm_ram_reply(wrong, 512)


class OnceTests(unittest.TestCase):
    def test_success_sends_and_reads_once_then_closes(self):
        transport = FakeTransport()
        result = attempt_once(transport)
        self.assertTrue(result["ok"])
        self.assertEqual((result["applicationRequestsSubmitted"], result["readCalls"]), (1, 1))
        self.assertEqual(transport.calls, ["open", "prepare", "write", "read", "close"])
        self.assertEqual(result["value"], {"reported_value": 1, "ram_mode_reported_active": True})
        self.assertFalse(result["rawReplySaved"])

    def test_zero_does_not_claim_recovery_or_ready(self):
        result = attempt_once(FakeTransport(value=0))
        self.assertTrue(result["ok"])
        self.assertEqual(result["value"], {"reported_value": 0, "ram_mode_reported_active": False})
        self.assertNotIn("recovered", result)
        self.assertNotIn("storage_ready", result)
        self.assertIsNone(result["firmwareVersion"])

    def test_all_transport_failures_stop_without_retry(self):
        for stage, count in (("open", (0, 0)), ("prepare", (0, 0)), ("write", (1, 0)), ("read", (1, 1))):
            transport = FakeTransport(failure=stage)
            result = attempt_once(transport)
            self.assertFalse(result["ok"])
            self.assertEqual((result["applicationRequestsSubmitted"], result["readCalls"]), count)
            self.assertEqual(transport.calls[-1], "close")
            self.assertEqual(transport.calls.count(stage), 1)
            self.assertNotIn("value", result)

    def test_wrong_interface_never_sends(self):
        info = interface()
        info["pipes"][1]["id"] = 4
        transport = FakeTransport(info=info)
        result = attempt_once(transport)
        self.assertFalse(result["ok"])
        self.assertEqual(result["applicationRequestsSubmitted"], 0)
        self.assertEqual(transport.calls, ["open", "close"])

    def test_short_write_prevents_read(self):
        transport = FakeTransport(short=True)
        result = attempt_once(transport)
        self.assertEqual(result["error"], "USB_SHORT_WRITE")
        self.assertEqual(result["readCalls"], 0)
        self.assertFalse(result["writeCompleted"])

    def test_unreviewed_reply_stops_and_keeps_no_value(self):
        for transport in (FakeTransport(mismatch=True), FakeTransport(value=2)):
            result = attempt_once(transport)
            self.assertEqual(result["error"], "USB_REPLY_UNREVIEWED")
            self.assertNotIn("value", result)
            self.assertEqual(result["readCalls"], 1)
            self.assertFalse(result["rawReplySaved"])

    def test_close_failure_prevents_success(self):
        result = attempt_once(FakeTransport(close_failure=True))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "USB_CLOSE")

    def test_native_write_builds_only_reviewed_getter_and_disallows_second(self):
        # 不调用原生构造器或加载设备；只替换 WinUsb_WritePipe 观察固定发包。
        calls = []

        class FakeApi:
            def WinUsb_WritePipe(self, handle, endpoint, buffer, size, count, overlapped):
                calls.append((endpoint, bytes(buffer.raw), size))
                c.cast(count, c.POINTER(U32)).contents.value = size
                return True

        native = FarmRamWinUsb.__new__(FarmRamWinUsb)
        native.prepared, native.sent, native.packet_size = True, False, 512
        native.usb, native.winusb = None, FakeApi()
        self.assertEqual(native.write_query(512), 512)
        self.assertEqual(calls, [(2, bytes.fromhex("2d 02 08 01 00") + bytes(507), 512)])
        with self.assertRaises(UsbFailure):
            native.write_query(512)
        self.assertEqual(len(calls), 1)

    def test_default_entrypoint_never_constructs_native_transport(self):
        with patch("sys.argv", ["read_farm_ram_once.py"]), patch("read_farm_ram_once.FarmRamWinUsb") as native:
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                main()
            native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
