"""一次读取的停止、机型隔离和句柄收尾测试；全部使用替身，无 USB 会话。"""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from read_usb_link_once import (NativeWinUsb, UsbFailure, attempt_once,
                                is_x1d_interface_path, validate_interface)


def interface(size=1024):
    return {"number": 2 if size == 64 else 0, "alternate": 0, "class": 255,
            "subclass": 0, "protocol": 0, "pipes": [
                {"id": ident, "type": 2, "maximumPacketSize": size}
                for ident in (1, 2, 129, 130)]}


class FakeTransport:
    def __init__(self, failure=None, info=None, partial=False, mismatch=False, close_failure=False):
        self.failure, self.partial, self.mismatch = failure, partial, mismatch
        self.info = info if info is not None else interface()
        self.close_failure = close_failure
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
        return size - 1 if self.partial else size

    def read_reply(self, size):
        self.read = True
        self.fail("read")
        header = b"\x73\x04\x09\x08" if self.mismatch else b"\x72\x04\x09\x08"
        return header + b"\x03\0\0\0" + bytes(size - 8)

    def close(self):
        self.calls.append("close")
        return {"enumerationClosed": True, "winUsbFreed": not self.close_failure, "deviceHandleClosed": True}


class OnceTests(unittest.TestCase):
    def test_x1d_path_and_x2d_separation(self):
        suffix = "#{CC135687-5267-4313-B0C7-C344609D6EF0}"
        self.assertTrue(is_x1d_interface_path(r"\\?\usb#vid_2756&pid_0002#synthetic" + suffix))
        self.assertFalse(is_x1d_interface_path(r"\\?\usb#vid_2756&pid_0009&mi_03#synthetic" + suffix))
        self.assertFalse(is_x1d_interface_path(r"\\?\usb#vid_2756&pid_00020#synthetic" + suffix))
        self.assertFalse(is_x1d_interface_path(r"\\?\usb#vid_2756&pid_0002#synthetic#{wrong}"))

    def test_all_three_verified_interfaces(self):
        for size in (64, 512, 1024):
            with self.subTest(size=size):
                self.assertEqual(validate_interface(interface(size)), size)

    def test_x2d_pipes_and_other_interface_changes_are_rejected(self):
        variants = []
        wrong = interface(); wrong["pipes"][1]["id"] = 4; wrong["pipes"][3]["id"] = 133; variants.append(wrong)
        wrong = interface(); wrong["number"] = 3; variants.append(wrong)
        wrong = interface(); wrong["alternate"] = 1; variants.append(wrong)
        wrong = interface(); wrong["pipes"][3]["maximumPacketSize"] = 512; variants.append(wrong)
        wrong = interface(); wrong["pipes"][0]["type"] = 3; variants.append(wrong)
        for info in variants:
            transport = FakeTransport(info=copy.deepcopy(info))
            result = attempt_once(transport)
            self.assertFalse(result["ok"])
            self.assertEqual(result["applicationRequestsSubmitted"], 0)
            self.assertEqual(transport.calls, ["open", "close"])

    def test_success_has_exactly_one_write_and_read_then_close(self):
        transport = FakeTransport()
        result = attempt_once(transport)
        self.assertTrue(result["ok"])
        self.assertEqual(result["applicationRequestsSubmitted"], 1)
        self.assertEqual(result["readCalls"], 1)
        self.assertEqual(transport.calls, ["open", "prepare", "write", "read", "close"])
        self.assertEqual(result["value"], {"flags": 3, "link_active": True, "super_speed": True})

    def test_errors_never_retry_and_always_close(self):
        for stage, calls, requests, reads in (
            ("open", ["open", "close"], 0, 0),
            ("prepare", ["open", "prepare", "close"], 0, 0),
            ("write", ["open", "prepare", "write", "close"], 1, 0),
            ("read", ["open", "prepare", "write", "read", "close"], 1, 1),
        ):
            with self.subTest(stage=stage):
                transport = FakeTransport(failure=stage)
                result = attempt_once(transport)
                self.assertFalse(result["ok"])
                self.assertEqual(result["applicationRequestsSubmitted"], requests)
                self.assertEqual(result["readCalls"], reads)
                self.assertEqual(transport.calls, calls)
                self.assertTrue(all(result["closure"].values()))

    def test_partial_write_prevents_read(self):
        transport = FakeTransport(partial=True)
        result = attempt_once(transport)
        self.assertEqual(result["error"], "USB_SHORT_WRITE")
        self.assertFalse(result["writeCompleted"])
        self.assertEqual(result["readCalls"], 0)
        self.assertEqual(transport.calls.count("write"), 1)

    def test_reply_mismatch_stops_without_values_or_raw_data(self):
        transport = FakeTransport(mismatch=True)
        result = attempt_once(transport)
        self.assertEqual(result["error"], "USB_REPLY_UNREVIEWED")
        self.assertNotIn("value", result)
        self.assertEqual(result["replyBytes"], 1024)
        self.assertFalse(result["rawReplySaved"])
        self.assertEqual(transport.calls.count("read"), 1)

    def test_close_failure_prevents_success(self):
        result = attempt_once(FakeTransport(close_failure=True))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "USB_CLOSE")

    def test_native_abi_and_bindings_without_opening_device(self):
        native = NativeWinUsb()
        self.assertFalse(native.opened or native.initialized or native.sent or native.read)
        self.assertTrue(all(native.close().values()))


if __name__ == "__main__":
    unittest.main()
