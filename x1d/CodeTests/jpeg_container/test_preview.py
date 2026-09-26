"""新 C 预览流程 + 原 1.25.0 ARM TurboJPEG 的有界联合验证。"""
from __future__ import annotations

import ctypes as C
import io
import json
import unittest

from PIL import Image

from test_container import ContainerTests, Info, X1D, embed, inspect, marker, metadata, DLL, extract
from arm_codec import ArmCodec

EVIDENCE = []


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ContainerTests.setUpClass()
        cls.source = ContainerTests.main[:2] + marker(0xE1, metadata()) + ContainerTests.main[2:]

    def test_original_arm_codec_to_embedded_preview(self):
        arm = ArmCodec()
        status, preview, stats = arm.generate(self.source)
        self.assertEqual(status, 0)
        self.assertEqual((stats["width"], stats["height"]), (1108, 830))
        self.assertLessEqual(len(preview), 3 * 1024 * 1024)
        self.assertEqual(stats["quality"], 85)
        self.assertEqual(stats["decodedRgbBytes"], 2044 * 1532 * 3)
        self.assertLess(stats["codecAllocatedPeakBytes"], 16 * 1024 * 1024)
        self.assertEqual(stats["remainingAllocations"], 0)
        self.assertEqual(stats["maximumAllocationBytes"], 2044 * 1532 * 3)
        with Image.open(io.BytesIO(preview)) as opened:
            opened.load()
            self.assertEqual(opened.size, (1108, 830))
            red, green = opened.getpixel((20, 20)), opened.getpixel((1088, 810))
            self.assertGreater(red[0], 200); self.assertLess(red[1], 30)
            self.assertGreater(green[1], 90); self.assertLess(green[0], 30)
        status, output = embed(self.source, preview)
        self.assertEqual(status, 0)
        header = output[:inspect(output)[1].header_bytes]
        info = Info()
        self.assertEqual(DLL.xj_preview_info(header, len(header), C.byref(info)), 0)
        self.assertEqual(extract(header), (0, preview))
        EVIDENCE.append({"case": "original-arm-turbojpeg-to-embedded-preview", "stats": stats,
                         "targetCodecRan": True, "libcMemoryAndErrorsReplaced": True,
                         "containerAndResizeRanAsArm": True, "noCameraAccess": True})

    def test_decoder_error_does_not_publish_output(self):
        bad = bytearray(self.source)
        at = bad.index(b"\xff\xdb")  # DQT 的精度/表号，结构长度仍合法。
        bad[at + 4] = 0xFF
        self.assertEqual(inspect(bytes(bad))[0], 0)
        arm = ArmCodec()
        status, output, stats = arm.generate(bytes(bad))
        self.assertEqual(status, 9)
        self.assertEqual(output, b"")
        self.assertEqual(stats["remainingAllocations"], 0)
        self.assertGreater(arm.calls.get("longjmp", 0), 0)
        EVIDENCE.append({"case": "target-codec-rejects-invalid-dqt", "outputBytes": 0,
                         "remainingAllocations": stats["remainingAllocations"]})

    def test_allocation_failure_and_early_capacity(self):
        for fail, size in [(1, 0), (2, 0), (0, 2044 * 1532 * 3), (0, 1108 * 830 * 3), (0, 1120 * 832 * 3 + 2048)]:
            with self.subTest(fail_allocation=fail, fail_size=size):
                arm = ArmCodec(fail_allocation=fail, fail_allocation_size=size)
                status, output, stats = arm.generate(self.source)
                self.assertNotEqual(status, 0)
                self.assertEqual(output, b"")
                self.assertEqual(stats["remainingAllocations"], 0)
                EVIDENCE.append({"case": "allocation-failure", "allocationIndex": fail,
                                 "allocationBytes": size,
                                 "status": status, "remainingAllocations": stats["remainingAllocations"]})
        arm = ArmCodec()
        status, output, stats = arm.generate(self.source, capacity=2048)
        self.assertEqual(status, 5)
        self.assertEqual(output, b"")
        self.assertEqual(arm.allocation_count, 0)
        EVIDENCE.append({"case": "insufficient-container-budget-before-codec", "allocations": 0})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PreviewTests))
    if result.wasSuccessful():
        report = {"scope": "native-preview-component-with-original-arm-codec", "cameraAccess": False,
                  "nativeDaemonIntegration": False, "cameraTimingMeasurement": False,
                  "tests": result.testsRun, "cases": EVIDENCE}
        path = X1D / "research" / "validation" / "jpeg-preview-arm-codec.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
