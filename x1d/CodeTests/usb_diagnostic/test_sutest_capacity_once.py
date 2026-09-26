"""固定容量查询的离线契约验证；不访问相机。"""
import binascii
import re
import struct
import unittest
from test_sutest_ram_once import MockUsb, TOKEN, reply
from read_usb_link_once import UsbFailure
from sutest_capacity_contract import COMMAND, build_query, parse_envelope, parse_capacity
from read_sutest_capacity_once import attempt_once


def text(sectors=b"8388608", root=b"root=/dev/mmcblk3p5"):
    return b"MMC\n0\n" + sectors + b"\n" + root + b"\n"


def parse(value):
    return parse_capacity(parse_envelope(reply(value), TOKEN).output_field)


def root_filter(cmdline):
    roots = [word for word in cmdline.split() if word.startswith("root=")]
    return roots[0] if len(roots) == 1 and re.fullmatch(r"root=/dev/mmcblk3p[1-9][0-9]?", roots[0]) else "UNKNOWN"


class CapacityTests(unittest.TestCase):
    def test_exact_command_packet_crc(self):
        expected = ("cd /sys/class/block/mmcblk3&&/bin/cat device/type removable size;"
                    "/usr/bin/awk '{for(i=1;i<=NF;i++)if($i~/^root=/){n++;r=$i}}"
                    'END{print n==1&&r~/^root=\\/dev\\/mmcblk3p[1-9][0-9]?$/?r:"UNKNOWN"}'
                    "' /proc/cmdline")
        self.assertEqual(COMMAND, expected)
        self.assertEqual(len(COMMAND), 205)
        packet = build_query(TOKEN)
        self.assertEqual(len(packet), 512)
        self.assertEqual(packet[25:230], expected.encode())
        self.assertEqual(packet[230:], bytes(282))
        self.assertEqual(struct.unpack_from("<3I", packet, 5), (52, 0, TOKEN))
        self.assertEqual(struct.unpack_from("<I", packet, 17)[0], binascii.crc_hqx(packet[21:257], 0))

    def test_exact_integer_capacity_and_unit_conversion(self):
        result = parse(text())
        self.assertEqual(result["capacityBytes"], 4294967296)
        self.assertEqual(result["decimalGB"], "4.294967")
        self.assertEqual(result["binaryGiB"], "4.000000")
        self.assertEqual(result["rootPartition"], "/dev/mmcblk3p5")
        self.assertFalse(result["freeSpaceMeasured"] or result["serialOrCidRead"])
        self.assertFalse(result["removableFlagAloneProvesPhysicalMounting"])
        self.assertEqual(parse(text(b"18446744073709551615", b"root=/dev/mmcblk3p99"))["capacityBytes"],
                         18446744073709551615 * 512)

    def test_complete_fields_and_fixed_device_required(self):
        valid = text()
        bad = [b"", valid.replace(b"MMC", b"SD"), valid.replace(b"0\n", b"1\n", 1),
               b"MMC\n8388608\nroot=/dev/mmcblk3p5\n", valid[:-1], valid + b"extra\n",
               valid + b"\0extra", b"x" * 232, text(root=b"UNKNOWN"),
               text(root=b"root=/dev/mmcblk2p5"), text(root=b"root=/dev/mmcblk3p0"),
               text(root=b"root=/dev/mmcblk3p100"), text(root=b"root=/dev/mmcblk3p01"),
               text(root=b"root=/dev/mmcblk3p5\nroot=/dev/mmcblk3p6"),
               text(root=b" root=/dev/mmcblk3p5 "), text(b"0"), text(b"-1"),
               text(b"01"), text(b"18446744073709551616"), text(b"1.5")]
        for value in bad:
            with self.subTest(value=value[:30]), self.assertRaises(ValueError):
                parse(value)

    def test_root_filter_counts_all_complete_parameters_and_redacts(self):
        self.assertEqual(root_filter("console=x root=/dev/mmcblk3p5 rw"), "root=/dev/mmcblk3p5")
        for cmdline in ("oldroot=/dev/mmcblk3p5", "root=/dev/mmcblk3p5junk",
                        "root=/dev/mmcblk3p5 root=/dev/mmcblk3p6 rw",
                        "root=/dev/mmcblk3p5 quiet rw root=/dev/mmcblk3p6",
                        "root=/dev/mmcblk3p5 root=/dev/mmcblk2p6",
                        "root=/dev/mmcblk3p5 root=UUID=PRIVATE_TEST_ONLY",
                        "root=/dev/mmcblk2p5", "root=/dev/mmcblk3p100", ""):
            self.assertEqual(root_filter(cmdline), "UNKNOWN")

    def test_success_closes_without_extra_camera_work(self):
        transport = MockUsb([reply(text())])
        result = attempt_once(transport, TOKEN)
        self.assertTrue(result["ok"] and transport.closed)
        self.assertEqual((transport.sent, transport.read), (1, 1))
        self.assertEqual(result["capacity"]["capacityBytes"], 4294967296)
        self.assertFalse(result["pipelineUpstreamSuccessVerified"] or result["rawReplySaved"] or result["stderrSaved"])
        self.assertNotIn("sourceCheck", result)

    def test_malformed_envelope_failed_cat_or_timeout_stop(self):
        damaged = bytearray(reply(text()))
        damaged[30] ^= 1
        for value in (reply(text(), token=TOKEN + 1), bytes(damaged), reply(text())[:260],
                      reply(text(), result=1), reply(b"root=/dev/mmcblk3p5\n"), UsbFailure("USB_READ", 121)):
            transport = MockUsb([value, reply(text())])
            result = attempt_once(transport, TOKEN)
            self.assertFalse(result["ok"])
            self.assertTrue(transport.closed)
            self.assertEqual((transport.sent, transport.read), (1, 1))
            self.assertNotIn("capacity", result)


if __name__ == "__main__":
    unittest.main()
