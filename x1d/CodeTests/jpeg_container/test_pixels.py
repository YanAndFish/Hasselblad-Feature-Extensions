"""用独立图像库核对颜色/八种方位，并在 ARM 上运行同一实现。"""
from __future__ import annotations
import ctypes as C
import io
import json
import random
import struct
import unittest
from PIL import Image, ImageCms
from test_container import Arm, DLL, X1D, metadata
from binary import ArmElf

EVIDENCE = []
DLL.xj_display_bgra.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_int]
DLL.xj_display_bgra.restype = C.c_int
DLL.xj_orient_bgra.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32]
DLL.xj_orient_bgra.restype = C.c_int
DLL.xj_tiff_unique_id.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p]
DLL.xj_tiff_unique_id.restype = C.c_int


class PixelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.arm = Arm()

    def test_all_orientations_against_pillow(self):
        methods = [None, Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_180,
                   Image.Transpose.FLIP_TOP_BOTTOM, Image.Transpose.TRANSPOSE,
                   Image.Transpose.ROTATE_270, Image.Transpose.TRANSVERSE, Image.Transpose.ROTATE_90]
        for w, h in [(5, 3), (71, 63), (1, 7), (6, 1), (8, 8)]:
            rng = random.Random(w * 1250 + h)
            pixels = bytes(rng.randrange(256) for _ in range(w * h * 4))
            source = Image.frombytes("RGBA", (w, h), pixels)
            for orientation, method in enumerate(methods, 1):
                expected = source if method is None else source.transpose(method)
                output = C.create_string_buffer(pixels, len(pixels))
                visited = C.create_string_buffer((w * h + 7) // 8)
                self.assertEqual(DLL.xj_orient_bgra(output, len(pixels), w, h, orientation, visited, len(visited)), 0)
                self.assertEqual(output.raw, expected.tobytes())
                self.arm.uc.mem_write(0x10000000, pixels)
                status = self.arm.call("xj_orient_bgra", [0x10000000, len(pixels), w, h, orientation, 0x10100000, len(visited)])
                self.assertEqual(status, 0)
                self.assertEqual(bytes(self.arm.uc.mem_read(0x10000000, len(pixels))), expected.tobytes())
        EVIDENCE.append({"case": "all-eight-orientations", "rectangles": 5, "armCases": 40,
                         "oracle": "Pillow transpose", "secondFullPixelBuffer": False})

    def test_color_against_littlecms(self):
        rgb = [(v, v, v) for v in range(256)]
        rgb += [(r, g, b) for r in range(0, 256, 17) for g in range(0, 256, 17) for b in range(0, 256, 17)]
        source = Image.new("RGB", (len(rgb), 1)); source.putdata(rgb)
        profile = ArmElf.load("usr/bin/jpeg-daemon").read(0x27700, 560)
        expected = ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                    ImageCms.createProfile("sRGB"), renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC).tobytes()
        bgra = b"".join(bytes([b, g, r, 19]) for r, g, b in rgb)
        output = C.create_string_buffer(bgra, len(bgra))
        self.assertEqual(DLL.xj_display_bgra(output, len(bgra), len(rgb), 1, 1), 0)
        raw = output.raw
        actual = b"".join(bytes([raw[i + 2], raw[i + 1], raw[i]]) for i in range(0, len(raw), 4))
        maximum = max(abs(a - b) for a, b in zip(actual, expected))
        self.assertLessEqual(maximum, 2)
        self.assertEqual(raw[3::4], b"\xff" * len(rgb))
        self.arm.uc.mem_write(0x10000000, bgra)
        self.assertEqual(self.arm.call("xj_display_bgra", [0x10000000, len(bgra), len(rgb), 1, 1]), 0)
        self.assertEqual(bytes(self.arm.uc.mem_read(0x10000000, len(bgra))), raw)
        unchanged = C.create_string_buffer(bgra, len(bgra))
        self.assertEqual(DLL.xj_display_bgra(unchanged, len(bgra), len(rgb), 1, 0), 0)
        self.assertEqual(unchanged.raw[0::4], bgra[0::4])
        self.assertEqual(unchanged.raw[1::4], bgra[1::4])
        self.assertEqual(unchanged.raw[2::4], bgra[2::4])
        EVIDENCE.append({"case": "fixed-adobe-rgb-to-srgb", "samples": len(rgb), "maxChannelDifference": maximum,
                         "oracle": "LittleCMS relative colorimetric", "armByteIdentical": True,
                         "physicalDisplayCalibration": False})

    def test_raw_prefix_uid_and_refusals(self):
        wanted = b"abcdef0123456789abcdef0123456789"
        for endian in ["<", ">"]:
            data = bytearray(metadata(endian, 1, wanted.upper())[6:])
            # 一个 RAW 数据块在前缀外：取 ID 不要求读像素。
            struct.pack_into(endian + "HHII", data, 10, 0x112, 7, 50000000, 131072)
            data.extend(bytes(131072 - len(data)))
            output = C.create_string_buffer(32)
            self.assertEqual(DLL.xj_tiff_unique_id(bytes(data), len(data), output), 0)
            self.assertEqual(output.raw, wanted)
            self.arm.uc.mem_write(0x10000000, bytes(data))
            self.assertEqual(self.arm.call("xj_tiff_unique_id", [0x10000000, len(data), 0x10100000]), 0)
            self.assertEqual(bytes(self.arm.uc.mem_read(0x10100000, 32)), wanted)
            for bad in [bytes(data[:100]), b"XY" + bytes(data[2:]), bytes(data[:128]) + b"0" * 32 + bytes(data[160:])]:
                output.raw = b"x" * 32
                self.assertNotEqual(DLL.xj_tiff_unique_id(bad, len(bad), output), 0)
                self.assertEqual(output.raw, bytes(32))
        EVIDENCE.append({"case": "bounded-raw-tiff-id", "endianCases": 2,
                         "rawPixelsOutsidePrefix": True, "rejectsMissingMalformedZeroId": True})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PixelTests))
    if result.wasSuccessful():
        path = X1D / "research/validation/display-pixels-native.json"
        path.write_text(json.dumps({"tests": result.testsRun, "cases": EVIDENCE, "cameraAccess": False,
                                    "qtGraphicsIntegration": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
