"""三份源固件摘要查询的必要离线验证；不访问设备。"""
import binascii
import json
import re
import struct
import unittest

from test_sutest_ram_once import MockUsb, TOKEN, reply
from read_usb_link_once import UsbFailure
from sutest_source_hash_contract import COMMAND, SOURCES, build_query, parse_envelope, parse_sources
from read_sutest_source_hash_once import attempt_once


def output(version=b"v1.25.0", hashes=None):
    hashes = hashes if hashes is not None else [x[3].encode() for x in SOURCES]
    return b'VERSION="' + version + b'"\n' + b"\n".join(hashes) + b"\n"


def parse(text):
    return parse_sources(parse_envelope(reply(text), TOKEN).output_field)


class SourceHashTests(unittest.TestCase):
    def test_only_exact_reviewed_query_and_packet(self):
        expected = ("/bin/grep -E '^VERSION=\"v[0-9.]{3,11}\"$' /etc/os-release;"
                    "cd /lib/firmware/hbl&&/usr/bin/sha256sum farm/bootimage_even-wedge.bin "
                    "farm/bootimage_odd-wedge.bin power-control/power-control.bin|/bin/grep -oE '^[0-9a-f]{64}'")
        self.assertEqual(COMMAND, expected)
        self.assertEqual(len(COMMAND), 218)
        packet = build_query(TOKEN)
        self.assertEqual(len(packet), 512)
        self.assertEqual(packet[25:243], expected.encode())
        self.assertEqual(packet[243:], bytes(269))
        self.assertEqual(struct.unpack_from("<3I", packet, 5), (52, 0, TOKEN))
        self.assertEqual(struct.unpack_from("<I", packet, 17)[0], binascii.crc_hqx(packet[21:257], 0))

    def test_version_and_fixed_positions_match_baseline(self):
        result = parse(output())
        self.assertEqual(result["declaredRootfsVersion"], "v1.25.0")
        self.assertTrue(result["allThreeSourcesMatch"])
        self.assertEqual([x["role"] for x in result["files"]], ["FARM even", "FARM odd", "SPC"])
        self.assertEqual([x["byteLengthInferredFromMatchingDigest"] for x in result["files"]],
                         [3954444, 3954444, 48455])
        self.assertTrue(all(x["independentlyMeasuredBytes"] is None for x in result["files"]))
        self.assertFalse(result["allRetryInputsChecked"] or result["targetControllerFlashChecked"])

    def test_mismatch_and_unknown_version_not_invented_damage(self):
        different = parse(output(b"v1.24.0"))
        self.assertFalse(different["sameVersionReferenceAvailable"] or different["allThreeSourcesMatch"])
        self.assertTrue(all(x["digestMatchesReference"] is None for x in different["files"]))
        values = [x[3].encode() for x in SOURCES]
        values[0], values[1] = values[1], values[0]
        swapped = parse(output(hashes=values))
        self.assertFalse(swapped["allThreeSourcesMatch"])
        self.assertEqual([x["digestMatchesReference"] for x in swapped["files"]], [False, False, True])

    def test_missing_partial_extra_malformed_outputs_unknown(self):
        valid = output()
        h = [x[3].encode() for x in SOURCES]
        bad = [b"", output(hashes=h[:2]), output(hashes=h[1:]), output(hashes=h + h[:1]),
               valid[:-1], valid + b"extra\n", valid + b"\0extra",
               output(b"1.25.0"), output(b"v1..25"), output(b"v1000.2.3"),
               output(b"v1.25.0\nVERSION=\"v1.25.0"), b"x" * 232,
               output(hashes=[h[0][:-1], h[1], h[2]]),
               output(hashes=[h[0].upper(), h[1], h[2]]),
               valid.replace(b"\n", b"\r\n")]
        for value in bad:
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                parse(value)
        self.assertEqual(parse(output(b"v999.999.999"))["declaredRootfsVersion"], "v999.999.999")

    def test_camera_filter_keeps_only_whitelisted_tokens(self):
        version_source = ['VERSION="v1.25.0"', 'VERSION_ID="42"', "OTHER=PRIVATE_TEST_ONLY"]
        versions = [s for s in version_source if re.fullmatch(r'VERSION="v[0-9.]{3,11}"', s)]
        digest_source = [x[3] + "  " + x[1] for x in SOURCES]
        filtered = [re.match(r"^[0-9a-f]{64}", s).group() for s in digest_source]
        text = ("\n".join(versions + filtered) + "\n").encode()
        self.assertTrue(parse(text)["allThreeSourcesMatch"])
        self.assertNotIn(b"PRIVATE_TEST_ONLY", text)
        self.assertNotIn(b"/lib/", text)

    def test_success_closes_and_does_not_claim_pipeline_or_whole_system(self):
        transport = MockUsb([reply(output())])
        result = attempt_once(transport, TOKEN)
        self.assertTrue(result["ok"] and transport.closed)
        self.assertEqual((transport.sent, transport.read), (1, 1))
        self.assertTrue(result["sourceCheck"]["allThreeSourcesMatch"])
        self.assertFalse(result["pipelineUpstreamSuccessVerified"] or result["rawReplySaved"] or result["stderrSaved"])
        self.assertNotIn("records", result)

    def test_failures_stop_without_partial_data_or_retry(self):
        broken = bytearray(reply(output()))
        broken[30] ^= 1
        cases = [reply(output(), token=TOKEN + 1), bytes(broken),
                 reply(output())[:260], reply(output(), result=1),
                 reply(output(hashes=[SOURCES[0][3].encode()])), UsbFailure("USB_READ", 121)]
        for value in cases:
            transport = MockUsb([value, reply(output())])
            result = attempt_once(transport, TOKEN)
            self.assertFalse(result["ok"])
            self.assertTrue(transport.closed)
            self.assertEqual((transport.sent, transport.read), (1, 1))
            self.assertNotIn("sourceCheck", result)
            self.assertNotIn("output_field", json.dumps(result))

    def test_one_late_farm_reply_keeps_shared_deadline(self):
        transport = MockUsb([bytes.fromhex("2e02010800") + bytes(507), reply(output())])
        times = iter((0, 0, 0, 1, 1))
        result = attempt_once(transport, TOKEN, clock=lambda: next(times))
        self.assertTrue(result["ok"])
        self.assertEqual(transport.timeouts, [6000, 5000])
        self.assertEqual((transport.sent, transport.read), (1, 2))


if __name__ == "__main__":
    unittest.main()

