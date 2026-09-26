"""固定 920K 尺寸的容量退让；实际 JPEG 由 Pillow 编解码，原生 C 执行调整流程。"""
from __future__ import annotations
import ctypes as C
import io
import json
import unittest
from PIL import Image
import numpy as np
from test_container import DLL, X1D, marker, metadata, jpeg, embed, extract, inspect

P = C.c_void_p
I = C.c_int
U = C.c_ulong
Init = C.CFUNCTYPE(P)
Destroy = C.CFUNCTYPE(I, P)
Allocate = C.CFUNCTYPE(P, I)
Release = C.CFUNCTYPE(None, P)
Header = C.CFUNCTYPE(I, P, P, U, C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(I))
Scaling = C.CFUNCTYPE(P, C.POINTER(I))
Decompress = C.CFUNCTYPE(I, P, P, U, P, I, I, I, I, I)
BufferSize = C.CFUNCTYPE(U, I, I, I)
Compress = C.CFUNCTYPE(I, P, P, I, I, I, I, C.POINTER(P), C.POINTER(U), I, I, I)


class Api(C.Structure):
    _fields_ = [("size", C.c_uint32), ("version", C.c_uint32)] + list(zip(
        ["init_decompress", "init_compress", "destroy", "allocate", "release", "header", "scaling", "decompress", "buffer_size", "compress"],
        [Init, Init, Destroy, Allocate, Release, Header, Scaling, Decompress, BufferSize, Compress]))


class Result(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ["bytes", "width", "height", "quality", "attempts", "decoded_bytes", "scratch_bytes"]]


class HostCodec:
    def __init__(self):
        self.live = {}
        self.qualities = []
        self.sizes = []
        self.factors = (I * 2)(1, 4)
        self.api = Api(C.sizeof(Api), 1, Init(lambda: 1), Init(lambda: 2), Destroy(lambda _: 0),
                       Allocate(self.allocate), Release(self.release), Header(self.header), Scaling(self.scaling),
                       Decompress(self.decompress), BufferSize(lambda w, h, s: ((w + 15) // 16 * 16) * ((h + 15) // 16 * 16) * 3 + 2048),
                       Compress(self.compress))

    def allocate(self, size):
        assert 0 < size <= 2044 * 1532 * 3
        buffer = C.create_string_buffer(size)
        pointer = C.addressof(buffer)
        self.live[pointer] = buffer
        return pointer

    def release(self, pointer): self.live.pop(pointer)

    def header(self, handle, data, size, w, h, sampling, color):
        with Image.open(io.BytesIO(C.string_at(data, size))) as image:
            w[0], h[0] = image.size
            sampling[0], color[0] = 1, 1
        return 0

    def scaling(self, count):
        count[0] = 1
        return C.addressof(self.factors)

    def decompress(self, handle, data, size, output, w, pitch, h, pixel, flags):
        assert (w, h, pitch, pixel) == (2044, 1532, 2044 * 3, 0)
        with Image.open(io.BytesIO(C.string_at(data, size))) as image:
            image.draft("RGB", (w, h))
            image.load()
            assert image.size == (w, h)
            C.memmove(output, image.tobytes(), w * h * 3)
        return 0

    def compress(self, handle, data, w, pitch, h, pixel, output, size, sampling, quality, flags):
        assert (w, h, pitch, pixel, sampling) == (1108, 830, 1108 * 3, 0, 2)
        with Image.frombytes("RGB", (w, h), C.string_at(data, w * h * 3)) as image:
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=quality, subsampling=2)
        content = stream.getvalue()
        assert len(content) <= size[0]
        C.memmove(output[0], content, len(content))
        size[0] = len(content)
        self.qualities.append(quality); self.sizes.append(len(content))
        return 0

    def generate(self, source, capacity=3 * 1024 * 1024):
        out = C.create_string_buffer(b"\xa5" * capacity, capacity)
        result = Result()
        DLL.xj_make_preview.argtypes = [P, C.c_uint32, P, C.c_uint32, C.POINTER(Result), C.POINTER(Api)]
        status = DLL.xj_make_preview(source, len(source), out, capacity, C.byref(result), C.byref(self.api))
        assert not self.live
        if status: assert out.raw == b"\xa5" * capacity
        return status, out.raw[:result.bytes], result


EVIDENCE = []


class CapacityTests(unittest.TestCase):
    def test_complex_images_keep_920k_dimensions(self):
        rng = np.random.default_rng(1250920)
        for kind in ["color-block-noise", "black-white-block-noise"]:
            small = rng.integers(0, 256, (768, 1024, 3), dtype=np.uint8)
            if kind == "black-white-block-noise":
                small[:] = ((small[:, :, :1] > 127) * 255).astype(np.uint8)
            image = Image.fromarray(small).resize((8176, 6128), Image.Resampling.NEAREST)
            encoded = jpeg(image, 85)
            image.close()
            source = encoded[:2] + marker(0xe1, metadata()) + encoded[2:]
            codec = HostCodec()
            status, preview, result = codec.generate(source)
            self.assertEqual(status, 0)
            self.assertEqual((result.width, result.height), (1108, 830))
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.quality, 85)
            self.assertGreater(len(preview), 61325)
            status, combined = embed(source, preview)
            self.assertEqual(status, 0)
            status, info = inspect(combined)
            self.assertEqual(status, 0)
            self.assertEqual(extract(combined[:info.header_bytes]), (0, preview))
            with Image.open(io.BytesIO(preview)) as decoded:
                decoded.load()
                self.assertEqual(decoded.size, (1108, 830))
            EVIDENCE.append({"case": kind, "qualitiesTried": codec.qualities, "encodedBytes": codec.sizes,
                             "selectedQuality": result.quality, "width": result.width, "height": result.height,
                             "beyondExifCapacity": True, "segmentedExtractionExact": True})
            if kind == "black-white-block-noise":
                tiny = HostCodec()
                result_code, output, result = tiny.generate(source, 4096)
                self.assertEqual(result_code, 5)
                self.assertEqual(output, b"")
                self.assertEqual(result.attempts, 1)
                EVIDENCE.append({"case": "fixed-size-capacity-exhausted", "attempts": result.attempts,
                                 "publishedBytes": 0, "silentlyDownsized": False})


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CapacityTests))
    if result.wasSuccessful():
        path = X1D / "research/validation/preview-920k-capacity.json"
        path.write_text(json.dumps({"tests": result.testsRun, "cases": EVIDENCE,
            "nativeAlgorithm": True, "codec": "Pillow host JPEG callbacks, not target ARM codec",
            "cameraAccess": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
