"""APP15 分段边界与拒绝路径；不把目录完整等同写卡完成。"""
from __future__ import annotations
import ctypes as C
import json
import struct
import unittest
from test_container import ContainerTests, DLL, Info, X1D, embed, extract, inspect, marker

EVIDENCE = []


def parts(data):
    at, result = 2, []
    while data[at:at + 2] == b"\xff\xef":
        length = struct.unpack_from(">H", data, at + 2)[0]
        result.append((at, at + length + 2))
        at += length + 2
    return result


class SegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ContainerTests.setUpClass()
        cls.base = ContainerTests()
        cls.source = cls.base.source()
        cls.preview = cls.base.preview
        cls.arm = cls.base.arm

    def arm_extract(self, prefix):
        self.arm.uc.mem_write(0x10000000, prefix)
        self.arm.uc.mem_write(0x20000000, bytes(4))
        status = self.arm.call("xj_extract_preview", [0x10000000, len(prefix), 0x10500000, 0x300000, 0x20000000])
        size = struct.unpack("<I", self.arm.uc.mem_read(0x20000000, 4))[0]
        return status, bytes(self.arm.uc.mem_read(0x10500000, size)) if status == 0 else b""

    def test_exact_segment_boundaries(self):
        for total in [65512, 65513, 65514, 131026, 131027, 196539]:
            wanted = total - len(self.base.icc)
            missing = wanted - len(self.preview)
            comments = b""
            while missing:
                length = min(missing, 65537)
                if 0 < missing - length < 4: length -= 4
                self.assertGreaterEqual(length, 4)
                comments += marker(0xfe, bytes(length - 4))
                missing -= length
            small = self.preview[:2] + comments + self.preview[2:]
            status, combined = embed(self.source, small)
            self.assertEqual(status, 0)
            info = inspect(combined)[1]
            self.assertEqual(info.thumbnail_size, total)
            self.assertEqual(len(parts(combined)), (total + 65512) // 65513)
            wanted_bytes = small[:2] + self.base.icc + small[2:]
            prefix = combined[:info.header_bytes]
            self.assertEqual(extract(prefix), (0, wanted_bytes))
            self.assertEqual(self.arm_extract(prefix), (0, wanted_bytes))
            EVIDENCE.append({"case": "chunk-boundary", "previewBytes": total,
                             "parts": len(parts(combined)), "armExact": True})

    def test_missing_duplicate_order_length_and_truncation(self):
        small = self.preview[:2] + marker(0xfe, bytes(60000)) * 2 + self.preview[2:]
        status, combined = embed(self.source, small)
        self.assertEqual(status, 0)
        info = inspect(combined)[1]
        header = combined[:info.header_bytes]
        spans = parts(header)
        self.assertGreaterEqual(len(spans), 3)
        a, b = spans[0]
        c, d = spans[1]
        cases = {
            "missing-first": header[:a] + header[b:],
            "missing-middle": header[:c] + header[d:],
            "duplicate": header[:b] + header[a:b] + header[b:],
            "out-of-order": header[:a] + header[c:d] + header[a:b] + header[d:],
            "truncated-payload": header[:b - 1] + header[b:],
            "short-header": header[:100],
        }
        for name, offset, value, fmt in [
            ("total-over-limit", a + 12, 3 * 1024 * 1024 + 1, ">I"),
            ("zero-parts", a + 18, 0, ">H"),
            ("too-many-parts", a + 18, 65, ">H"),
            ("wrong-offset", c + 20, 0xffffffff, ">I"),
            ("wrong-index", c + 16, 0, ">H"),
            ("inconsistent-total", c + 12, 100, ">I"),
        ]:
            bad = bytearray(header)
            struct.pack_into(fmt, bad, offset, value)
            cases[name] = bytes(bad)
        for name, data in cases.items():
            with self.subTest(name=name):
                host = extract(data)
                self.assertNotEqual(host[0], 0)
                self.assertEqual(host[1], b"")
                self.assertEqual(self.arm_extract(data), host)
                EVIDENCE.append({"case": name, "status": host[0], "outputBytes": 0, "armMatched": True})

    def test_preview_decode_shape_and_icc_mismatch(self):
        status, combined = embed(self.source, self.preview)
        self.assertEqual(status, 0)
        info = inspect(combined)[1]
        header = bytearray(combined[:info.header_bytes])
        payload = 2 + 24
        bad = bytearray(header); bad[payload] = 0
        self.assertNotEqual(extract(bytes(bad))[0], 0)
        sof = header.index(b"\xff\xc0", payload)
        bad = bytearray(header)
        struct.pack_into(">H", bad, sof + 7, 1107)
        self.assertEqual(extract(bytes(bad)), (4, b""))
        self.assertEqual(self.arm_extract(bytes(bad)), (4, b""))
        # 目录仍合法；预览内容验证负责发现尺寸错误。
        shape = Info()
        self.assertEqual(DLL.xj_preview_info(bytes(bad), len(bad), C.byref(shape)), 0)
        bad = bytearray(header)
        profile = bad.index(b"ICC_PROFILE", payload)
        bad[profile + 14] ^= 1
        self.assertEqual(extract(bytes(bad)), (4, b""))
        EVIDENCE.append({"case": "embedded-jpeg-shape-and-icc", "rejectsWrongDimensions": True,
                         "headerAloneDoesNotValidatePreview": True})

    def test_limits_and_overlap(self):
        _, combined = embed(self.source, self.preview)
        info = inspect(combined)[1]
        prefix = combined[:info.header_bytes]
        needed = C.c_uint32(999)
        self.assertEqual(DLL.xj_extract_preview(prefix, 4 * 1024 * 1024 + 1, None, 0, C.byref(needed)), 1)
        self.assertEqual(needed.value, 0)
        sentinel = C.create_string_buffer(b"sentinel", 8)
        self.assertEqual(DLL.xj_extract_preview(prefix, len(prefix), sentinel, len(sentinel), C.byref(needed)), 5)
        self.assertEqual(sentinel.raw, b"sentinel")
        overlap = C.create_string_buffer(prefix, len(prefix))
        self.assertEqual(DLL.xj_extract_preview(overlap, len(prefix), overlap, len(prefix), C.byref(needed)), 7)
        EVIDENCE.append({"case": "header-budget-output-budget-overlap", "inputLimitBytes": 4 * 1024 * 1024,
                         "previewLimitBytes": 3 * 1024 * 1024})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SegmentTests))
    if result.wasSuccessful():
        (X1D / "research/validation/preview-segments-native.json").write_text(
            json.dumps({"tests": result.testsRun, "cases": EVIDENCE, "cameraAccess": False,
                        "standardExifThumbnail": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
