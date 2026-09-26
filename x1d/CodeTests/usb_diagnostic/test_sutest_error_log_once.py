"""有限日志查询离线验证；复用已有虚拟USB，不接触相机。"""
import binascii
import re
import struct
import unittest

from test_sutest_ram_once import MockUsb, TOKEN, reply
from read_usb_link_once import UsbFailure
from sutest_error_log_contract import COMMAND, build_query, parse_envelope, parse_records
from read_sutest_error_log_once import attempt_once


def records(text):
    return parse_records(parse_envelope(reply(text), TOKEN).output_field)


class ErrorLogTests(unittest.TestCase):
    def test_exact_fixed_packet_and_crc(self):
        packet = build_query(TOKEN)
        self.assertEqual(len(COMMAND.encode("ascii")), 184)
        self.assertEqual(packet[25:209], COMMAND.encode("ascii"))
        self.assertEqual(packet[209:], bytes(303))
        self.assertEqual(struct.unpack_from("<3I", packet, 5), (52, 0, TOKEN))
        self.assertEqual(struct.unpack_from("<I", packet, 17)[0], binascii.crc_hqx(packet[21:257], 0))

    def test_order_and_allowed_fields_only(self):
        text = b"SUC: true FARM: false SPC: true\nonErrorReportReceived 1000 5 1 \nonErrorReportReceived 1005 0 2 \n"
        parsed = records(text)
        self.assertEqual([x["kind"] for x in parsed], ["link-history", "error-report", "error-report"])
        self.assertEqual(parsed[1], {"kind": "error-report", "code": 1000, "category": 5, "severity": 1})
        self.assertFalse(parsed[0]["farm"])

    def test_synthetic_filter_drops_other_fields(self):
        pattern = re.compile(r"onErrorReportReceived [0-9 ]+|SUC: (true|false) FARM: (true|false) SPC: (true|false)")
        source = ['unrelated REDACT_TEST_ONLY',
                  'tag onErrorReportReceived 1000 5 1 "source.cpp" "function" 123',
                  'tag All links are not yet up: SUC: true FARM: false SPC: true']
        selected = [m.group() for line in source for m in pattern.finditer(line)][-3:]
        text = ("\n".join(selected) + "\n").encode()
        self.assertEqual(len(records(text)), 2)
        for forbidden in (b"REDACT_TEST_ONLY", b"source.cpp", b"function", b"123"):
            self.assertNotIn(forbidden, text)

    def test_empty_partial_extra_and_truncated_are_unknown(self):
        bad = [b"", b"onErrorReportReceived 1000 5\n", b"onErrorReportReceived 1000 5 1",
               b"onErrorReportReceived 1000 5 1 20\n", b"onErrorReportReceived 1000 5 1\0extra",
               b"SUC: true FARM: false SPC: true\nextra\n", b"SUC: true FARM: false SPC: true\n" * 4,
               b"onErrorReportReceived 9999999999 5 1\n", b"X" * 232]
        for text in bad:
            with self.subTest(length=len(text)), self.assertRaises(ValueError):
                records(text)

    def test_failed_process_and_zero_result_empty_not_success(self):
        for packet, error in ((reply(result=1), "SUTEST_PROCESS_FAILED"),
                              (reply(b""), "DIAGNOSTIC_OUTPUT_UNKNOWN")):
            transport = MockUsb([packet])
            result = attempt_once(transport, TOKEN)
            self.assertTrue(result["replyMatched"])
            self.assertFalse(result["ok"])
            self.assertFalse(result["pipelineUpstreamSuccessVerified"])
            self.assertEqual(result["error"], error)
            self.assertNotIn("records", result)

    def test_success_is_historical_records_not_pipeline_completeness(self):
        transport = MockUsb([reply(b"onErrorReportReceived 1000 5 1 \n")])
        result = attempt_once(transport, TOKEN)
        self.assertTrue(result["ok"] and transport.closed)
        self.assertEqual((transport.sent, transport.read), (1, 1))
        self.assertFalse(result["pipelineUpstreamSuccessVerified"])
        self.assertFalse(result["currentRealtimeStateVerified"])
        self.assertFalse(result["rawReplySaved"] or result["stderrSaved"])

    def test_bad_envelope_or_timeout_stops(self):
        bad_crc = bytearray(reply())
        bad_crc[30] ^= 1
        for packet in (reply(token=TOKEN + 1), bytes(bad_crc), reply()[:260], UsbFailure("USB_READ", 121)):
            transport = MockUsb([packet, reply(b"onErrorReportReceived 1000 5 1\n")])
            result = attempt_once(transport, TOKEN)
            self.assertFalse(result["ok"])
            self.assertEqual((transport.sent, transport.read), (1, 1))
            self.assertTrue(transport.closed)

    def test_late_farm_uses_remaining_budget_once(self):
        late = bytes.fromhex("2e02010800") + bytes(507)
        transport = MockUsb([late, reply(b"onErrorReportReceived 1000 5 1\n")])
        times = iter((0, 0, 0, 1, 1))
        result = attempt_once(transport, TOKEN, clock=lambda: next(times))
        self.assertTrue(result["ok"])
        self.assertEqual(transport.timeouts, [6000, 5000])
        self.assertEqual((transport.sent, transport.read), (1, 2))


if __name__ == "__main__":
    unittest.main()
