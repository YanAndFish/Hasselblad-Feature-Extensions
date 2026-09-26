"""相同 C 实现的主机与 ARM 验证；图像全由本用例在内存生成。"""
from __future__ import annotations

import ctypes as C
import hashlib
import io
import json
from pathlib import Path
import random
import struct
import sys
import unittest

from PIL import Image, ImageDraw

X1D = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(X1D / "tools"))
from binary import ArmElf
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)

OUT = X1D / "artifacts" / "jpeg-container-v1"
EVIDENCE = []


class Info(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                "width height orientation exif_offset exif_size ifd0_next_offset thumbnail_offset thumbnail_size eoi_end icc_bytes has_unique_id".split()] + [("unique_id", C.c_uint8 * 32), ("preview_kind", C.c_uint32), ("header_bytes", C.c_uint32)]


DLL = C.CDLL(str(OUT / "x1d-jpeg-container.dll"))
DLL.xj_inspect.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(Info)]
DLL.xj_inspect.restype = C.c_int
DLL.xj_preview_info.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(Info)]
DLL.xj_preview_info.restype = C.c_int
DLL.xj_embed_preview.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32,
                                C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
DLL.xj_embed_preview.restype = C.c_int
DLL.xj_extract_preview.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
DLL.xj_extract_preview.restype = C.c_int


def marker(number, data):
    return b"\xff" + bytes([number]) + struct.pack(">H", len(data) + 2) + data


def metadata(endian="<", orientation=1, unique=b"102030405060708090a0b0c0d0e0f001"):
    data = bytearray(4096)
    data[:2] = b"II" if endian == "<" else b"MM"
    struct.pack_into(endian + "HIH", data, 2, 42, 8, 2)
    struct.pack_into(endian + "HHI", data, 10, 0x112, 3, 1)
    struct.pack_into(endian + "H", data, 18, orientation)
    struct.pack_into(endian + "HHII", data, 22, 0x8769, 4, 1, 64)
    struct.pack_into(endian + "I", data, 34, 0)
    # 两个合法 Exif 项；MakerNote 值保持在原 TIFF 固定偏移。
    struct.pack_into(endian + "H", data, 64, 2)
    struct.pack_into(endian + "HHII", data, 66, 0x927C, 7, 40, 240)
    struct.pack_into(endian + "HHII", data, 78, 0xA420, 2, 33, 128)
    data[128:161] = unique + b"\0"
    data[240:280] = bytes(range(40))
    return b"Exif\0\0" + data


def inspect(data):
    info = Info()
    result = DLL.xj_inspect(data, len(data), C.byref(info))
    return result, info


def embed(source, preview):
    count = C.c_uint32()
    result = DLL.xj_embed_preview(source, len(source), preview, len(preview), None, 0, C.byref(count))
    if result != 6:
        return result, b""
    target = C.create_string_buffer(count.value)
    result = DLL.xj_embed_preview(source, len(source), preview, len(preview), target, len(target), C.byref(count))
    return result, target.raw[:count.value]


def extract(data):
    needed = C.c_uint32()
    status = DLL.xj_extract_preview(data, len(data), None, 0, C.byref(needed))
    if status != 6: return status, b""
    buffer = C.create_string_buffer(needed.value)
    status = DLL.xj_extract_preview(data, len(data), buffer, len(buffer), C.byref(needed))
    return status, buffer.raw[:needed.value] if status == 0 else b""


def jpeg(image, quality=85):
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=quality, subsampling=1)
    return stream.getvalue()


class Arm:
    """纯 C ELF 指令执行，没有任何外部函数替身或设备地址映射。"""
    def __init__(self):
        self.elf = ArmElf((OUT / "libx1d-jpeg-container.so").read_bytes())
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0, 0x80000)
        for segment in self.elf.elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                self.uc.mem_write(segment["p_vaddr"], segment.data())
        self.uc.mem_map(0x10000000, 0x1000000)
        self.uc.mem_map(0x20000000, 0x100000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.exports = {s.name: s["st_value"] for s in self.elf.symbols if s.name.startswith("xj_")}
        self.stack, self.stop = 0x200F0000, 0x200FF000

    def call(self, name, args):
        regs = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
        for register, value in zip(regs, args):
            self.uc.reg_write(register, value)
        for index, value in enumerate(args[4:]):
            self.uc.mem_write(self.stack + index * 4, struct.pack("<I", value))
        self.uc.reg_write(UC_ARM_REG_SP, self.stack)
        self.uc.reg_write(UC_ARM_REG_LR, self.stop)
        self.uc.emu_start(self.exports[name], self.stop, count=100_000_000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == self.stop, "ARM 指令预算耗尽"
        assert self.uc.reg_read(UC_ARM_REG_SP) == self.stack, "ARM 栈未恢复"
        return self.uc.reg_read(UC_ARM_REG_R0)

    def embed(self, source, preview):
        assert len(source) < 0x400000 and len(preview) < 0x100000
        self.uc.mem_write(0x10000000, source)
        self.uc.mem_write(0x10400000, preview)
        args = [0x10000000, len(source), 0x10400000, len(preview), 0x10500000, 0x800000, 0x20000000]
        status = self.call("xj_embed_preview", args)
        size = struct.unpack("<I", self.uc.mem_read(0x20000000, 4))[0]
        return status, bytes(self.uc.mem_read(0x10500000, size)) if status == 0 else b""


class ContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = Image.new("RGB", (8176, 6128), (65, 110, 160))
        draw = ImageDraw.Draw(image)
        for x in range(0, 8176, 128):
            draw.line((x, 0, x, 6127), fill=(210, (x * 3) % 255, 50), width=3)
        draw.rectangle((0, 0, 800, 600), fill="red")
        draw.rectangle((7375, 5527, 8175, 6127), fill="green")
        cls.main = jpeg(image)
        cls.preview = jpeg(image.resize((1108, 830), Image.Resampling.LANCZOS), 60)
        # 人工 profile 字节仅测试封装保留；不冒充校色或真实 ICC 验证。
        cls.icc = marker(0xE2, b"ICC_PROFILE\0\1\1" + bytes(range(128)))
        cls.arm = Arm()
        image.close()

    def source(self, **kwargs):
        return self.main[:2] + marker(0xE1, metadata(**kwargs)) + self.icc + self.main[2:]

    def test_endian_orientation_and_image_bytes(self):
        for endian in ("<", ">"):
            for orientation in (1, 3, 6, 8):
                with self.subTest(endian=endian, orientation=orientation):
                    source = self.source(endian=endian, orientation=orientation)
                    status, output = embed(source, self.preview)
                    self.assertEqual(status, 0)
                    status, info = inspect(output)
                    self.assertEqual(status, 0)
                    self.assertEqual((info.width, info.height, info.orientation), (8176, 6128, orientation))
                    self.assertEqual(info.has_unique_id, 1)
                    self.assertLessEqual(info.exif_size + 8, 65535)
                    old = inspect(source)[1]
                    original_tiff = bytearray(source[old.exif_offset:old.exif_offset + old.exif_size])
                    self.assertEqual(output[info.exif_offset:info.exif_offset + 4096], original_tiff)
                    self.assertEqual(output[info.exif_offset + info.exif_size:], source[old.exif_offset + old.exif_size:])
                    self.assertEqual(info.preview_kind, 1)
                    self.assertEqual(extract(output[:info.header_bytes])[0], 0)
                    small = extract(output[:info.header_bytes])[1]
                    self.assertEqual(small, self.preview[:2] + self.icc + self.preview[2:])
                    with Image.open(io.BytesIO(output)) as opened, Image.open(io.BytesIO(source)) as original:
                        opened.load(); original.load()
                        self.assertEqual(opened.getexif()[0x112], orientation)
                        self.assertEqual(hashlib.sha256(opened.tobytes()).digest(), hashlib.sha256(original.tobytes()).digest())
                    with Image.open(io.BytesIO(small)) as opened, Image.open(io.BytesIO(self.preview)) as original:
                        opened.load(); original.load()
                        self.assertEqual(opened.size, (1108, 830))
                        self.assertEqual(opened.tobytes(), original.tobytes())
                    EVIDENCE.append({"case": "preserve-main-exif-icc-preview", "endian": endian,
                                     "orientation": orientation, "outputBytes": len(output), "thumbnailBytes": len(small)})

    def test_real_arm_matches_host(self):
        for endian, orientation in [("<", 1), (">", 6)]:
            source = self.source(endian=endian, orientation=orientation)
            host = embed(source, self.preview)
            arm = self.arm.embed(source, self.preview)
            self.assertEqual(arm, host)
            EVIDENCE.append({"case": "arm-byte-identical", "endian": endian, "orientation": orientation})

    def test_errors_do_not_touch_output(self):
        source = self.source()
        count = C.c_uint32()
        output = C.create_string_buffer(b"sentinel", 9)
        result = DLL.xj_embed_preview(source, len(source), self.preview, len(self.preview), output, 9, C.byref(count))
        self.assertEqual(result, 5)
        self.assertEqual(output.raw, b"sentinel\0")
        mutable = C.create_string_buffer(source, len(source) + 65536)
        result = DLL.xj_embed_preview(mutable, len(source), self.preview, len(self.preview), mutable, len(mutable), C.byref(count))
        self.assertEqual(result, 7)
        self.assertEqual(mutable.raw[:len(source)], source)
        self.assertEqual(embed(source[:-1], self.preview)[0], 2)
        self.assertEqual(embed(self.preview, self.preview)[0], 4)
        self.assertEqual(embed(source, source)[0], 4)
        status, output = embed(source, self.preview)
        self.assertEqual(status, 0)
        self.assertEqual(embed(output, self.preview)[0], 4)
        EVIDENCE.append({"case": "capacity-overlap-truncation-dimension-double-embed"})

    def test_metadata_and_icc_corruption(self):
        source = bytearray(self.source())
        info = inspect(bytes(source))[1]
        bad = bytearray(source)
        struct.pack_into("<I", bad, info.exif_offset + 30, 0xFFFFFFF0)
        self.assertEqual(inspect(bytes(bad))[0], 3)
        bad = bytearray(source)
        struct.pack_into("<I", bad, info.ifd0_next_offset, 8)
        self.assertEqual(inspect(bytes(bad))[0], 3)
        bad = bytearray(source)
        bad[info.exif_offset + 66 + 2:info.exif_offset + 66 + 4] = b"\xff\xff"
        self.assertEqual(inspect(bytes(bad))[0], 3)
        duplicate = source[:2] + marker(0xE1, metadata()) + source[2:]
        self.assertEqual(inspect(bytes(duplicate))[0], 3)
        bad = bytes(source).replace(b"ICC_PROFILE\0\1\1", b"ICC_PROFILE\0\2\2", 1)
        self.assertEqual(inspect(bad)[0], 4)
        # 保留合法 marker 结构但超过内嵌容器容量。
        huge = marker(0xFE, bytes(60000)) * 53
        self.assertEqual(embed(bytes(source), self.preview[:2] + huge + self.preview[2:])[0], 5)
        for data in (bytes(source[:100]), bytes(bad)):
            self.assertEqual(self.arm.embed(data, self.preview)[0], embed(data, self.preview)[0])
        EVIDENCE.append({"case": "exif-offset-cycle-type-duplicate-icc-order-segment-budget"})

    def test_id_and_padding(self):
        for unique, expected in [(b"0" * 32, 0), (b"z" * 32, 0), (b"A" * 32, 1)]:
            status, info = inspect(self.source(unique=unique))
            self.assertEqual(status, 0)
            self.assertEqual(info.has_unique_id, expected)
            if expected: self.assertEqual(bytes(info.unique_id), b"a" * 32)
        self.assertEqual(inspect(self.source() + bytes(511))[0], 0)
        self.assertEqual(inspect(self.source() + bytes(512))[0], 2)
        self.assertEqual(inspect(self.source() + b"\1")[0], 2)
        EVIDENCE.append({"case": "id-validation-and-storage-padding"})

    def test_preview_from_prefix_without_main_decode(self):
        status, output = embed(self.source(), self.preview)
        self.assertEqual(status, 0)
        info = Info()
        prefix = output[:inspect(output)[1].header_bytes]
        self.assertGreater(len(output), len(prefix))
        self.assertEqual(DLL.xj_preview_info(prefix, len(prefix), C.byref(info)), 0)
        self.assertEqual(info.eoi_end, 0)  # 没有宣称主文件完整。
        self.assertEqual(extract(prefix)[0], 0)
        thumb = extract(prefix)[1]
        with Image.open(io.BytesIO(thumb)) as opened:
            opened.load()
            self.assertEqual(opened.size, (1108, 830))
        self.assertEqual(DLL.xj_preview_info(prefix, 1000, C.byref(info)), 8)
        self.assertEqual(DLL.xj_preview_info(output, 4 * 1024 * 1024 + 1, C.byref(info)), 1)
        self.assertEqual(DLL.xj_preview_info(self.source(), 131072, C.byref(info)), 4)
        EVIDENCE.append({"case": "preview-from-indexed-header", "fullFileRead": False,
                         "fullImageDecoded": False, "headerDoesNotProveFileCompletion": True})

    def test_bounded_malformed_inputs(self):
        rng = random.Random(1250)
        source = self.source()
        statuses = {}
        # 只记录分类数量，输入不含真实照片或相机标识。
        for _ in range(800):
            sample = bytearray(source)
            if rng.randrange(2): sample = sample[:rng.randrange(len(sample))]
            else:
                for _ in range(rng.randrange(1, 5)):
                    at = rng.randrange(min(len(sample), 5000))
                    sample[at] = rng.randrange(256)
            status, info = inspect(bytes(sample))
            statuses[status] = statuses.get(status, 0) + 1
            if status == 0:
                self.assertLessEqual(info.exif_offset + info.exif_size, len(sample))
                self.assertLessEqual(info.eoi_end, len(sample))
        EVIDENCE.append({"case": "bounded-mutated-and-truncated-inputs", "count": 800, "statuses": statuses})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContainerTests))
    if result.wasSuccessful():
        report = {"scope": "standalone-c-component", "cameraAccess": False,
                  "nativeProcessIntegration": False, "entropyDecode": "Pillow on synthetic images; ARM runs container code only",
                  "tests": result.testsRun, "cases": EVIDENCE}
        path = X1D / "research" / "validation" / "jpeg-container-native.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
