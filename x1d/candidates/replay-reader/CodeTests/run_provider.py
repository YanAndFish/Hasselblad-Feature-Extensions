"""候选 ARM provider + 固定 Qt 5.5.1 QImage/JSON + 原 TurboJPEG 的有界验证。

Storage/File、record 文件读取、同步、QObject 基类和 GL 窗口入口是显式替身。
替身只返回本用例生成的数据；未知外部调用拒绝。没有 Linux/DBus/事件循环或 GPU。
"""
from __future__ import annotations
import ctypes as C
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import time
from PIL import Image

from arm_machine import ArmMachine, HERE, X1D, REGS, UC_HOOK_CODE

OUT = HERE / "artifacts/provider"
ROOT = X1D.parent
ADD = "_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase"
REQUEST = "_ZN12_GLOBAL__N_18Provider14requestTextureERK7QStringP5QSizeRKS4_"
TEXTURE_IMAGE = "_ZNK12_GLOBAL__N_17Texture5imageEv"
TEXTURE_DELETE = "_ZN12_GLOBAL__N_17TextureD0Ev"
FALLBACK = 0x12345678


class Info(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in "width height orientation exif_offset exif_size ifd0_next_offset thumbnail_offset thumbnail_size eoi_end icc_bytes has_unique_id".split()] + [
        ("unique_id", C.c_uint8 * 32), ("preview_kind", C.c_uint32), ("header_bytes", C.c_uint32)]


def sha(data): return hashlib.sha256(data).hexdigest()


def jpeg(size, color, quality=85):
    stream = io.BytesIO()
    with Image.new("RGB", size, color) as im:
        im.save(stream, format="JPEG", quality=quality, subsampling=1)
    return stream.getvalue()


def marker(number, data): return b"\xff" + bytes([number]) + struct.pack(">H", len(data) + 2) + data


def metadata(orientation, uid):
    tiff = bytearray(4096)
    tiff[:2] = b"II"
    struct.pack_into("<HIH", tiff, 2, 42, 8, 2)
    struct.pack_into("<HHIH", tiff, 10, 0x112, 3, 1, orientation)
    struct.pack_into("<HHII", tiff, 22, 0x8769, 4, 1, 64)
    struct.pack_into("<H", tiff, 64, 1)
    struct.pack_into("<HHII", tiff, 66, 0xA420, 2, 33, 128)
    tiff[128:161] = uid + b"\0"
    return bytes(tiff)


def build_container():
    OUT.mkdir(parents=True, exist_ok=True)
    compiler = ROOT / ".research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe"
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(OUT / "zig-global-cache"), ZIG_LOCAL_CACHE_DIR=str(OUT / "zig-local-cache"))
    subprocess.run([str(compiler), "cc", "-O2", "-shared", str(HERE / "native/jpeg_container.c"), "-o", str(OUT / "container.dll")], cwd=ROOT, env=env, check=True)
    dll = C.CDLL(str(OUT / "container.dll"))
    dll.xj_inspect.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(Info)]
    dll.xj_embed_preview.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
    return dll


def fixture(dll, color=(65, 110, 160), orientation=1, uid=b"112233445566778899aabbccddeeff00", bad_preview=False):
    raw = metadata(orientation, uid).ljust(128 * 1024, b"\0")
    main = jpeg((8176, 6128), color)
    main = main[:2] + marker(0xE1, b"Exif\0\0" + raw[:4096]) + main[2:]
    preview = jpeg((1108, 830), color)
    if bad_preview:
        preview = bytearray(preview)
        preview[preview.index(b"\xff\xdb") + 4] = 0xff
        preview = bytes(preview)
    count = C.c_uint32()
    assert dll.xj_embed_preview(main, len(main), preview, len(preview), None, 0, C.byref(count)) == 6
    output = C.create_string_buffer(count.value)
    assert dll.xj_embed_preview(main, len(main), preview, len(preview), output, len(output), C.byref(count)) == 0
    data = output.raw[:count.value]
    info = Info()
    assert dll.xj_inspect(data, len(data), C.byref(info)) == 0
    record = {"version": 3, "closed": True, "jpegPath": "/artificial/a.jpg", "rawPath": "/artificial/a.raw",
              "bytes": len(data), "prefixBytes": info.header_bytes, "orientation": orientation,
              "rawHash": sha(raw), "uidHash": sha(uid), "prefixHash": sha(data[:info.header_bytes]), "jpegHash": sha(data)}
    return {"files": {record["jpegPath"]: data, record["rawPath"]: raw}, "record": record, "preview": preview}


class ProviderMachine(ArmMachine):
    def __init__(self):
        self.files = {}
        self.record = None
        self.reads = []
        self.fallback_calls = []
        self.file_failure = None
        self.registered = []
        self.gpu_images = []
        self.decodes = 0
        self.clock_seconds = 1
        self.clock_step = 0
        self.record_accepted = False
        super().__init__(module="provider", qt_gui=True, force_neon=True)
        self.errno = self.allocate(4, True)
        self.bind("_ZN15QGuiApplication13primaryScreenEv", lambda: self.ret(0))
        self.bind("_ZN3X1D8readFileERK7QStringyiPb", self.read_file)
        self.bind("_ZN3X1D10loadRecordERK7QStringP11QJsonObject", self.load_record)
        self.bind("_ZNK12QQuickWindow22createTextureFromImageERK6QImage6QFlagsINS_19CreateTextureOptionEE", self.gpu_create)
        self.bind("_ZNK12QQuickWindow22createTextureFromImageERK6QImage", self.gpu_create)
        decoder = self.symbols["tjDecompress2"]
        self.uc.hook_add(UC_HOOK_CODE, self.observe_decode, begin=decoder, end=decoder)
        self.fallback_entry = self.callback("original-provider-request", self.fallback)
        self.add_entry = self.callback("original-add-provider", self.add_provider)
        self.original = self.allocate(8, True)
        self.original_vtable = self.allocate(32, True)
        self.put(self.original, self.original_vtable)
        self.put(self.original_vtable + 4, self.callback("original-provider-delete", lambda: self.ret()))
        self.put(self.original_vtable + 8, self.callback("original-provider-type", lambda: self.ret(2)))
        self.put(self.original_vtable + 24, self.fallback_entry)
        name = self.qstring("imagestore")
        self.call(ADD, [1, name, self.original], stop=0x26e80)
        self.drop_string(name)
        assert len(self.registered) == 1 and self.registered[0] != self.original
        self.provider = self.registered[0]

    def observe_decode(self, uc, at, size, context): self.decodes += 1

    def shim(self, uc, at, size, context):
        name = self.entries[at]
        if name == "dlsym" and self.cstring(self.arg(1)) == ADD:
            self.ret(self.add_entry)
        elif name in ("_ZN21QQmlImageProviderBaseC2Ev", "_ZN21QQmlImageProviderBaseD2Ev"):
            self.ret(self.arg(0))
        elif name == "clock_gettime":
            self.clock_seconds += self.clock_step
            self.put(self.arg(1), self.clock_seconds)
            self.put(self.arg(1) + 4, 0)
            self.ret()
        elif name == "sysconf":
            assert self.arg(0) == 149, ("未声明 sysconf", self.arg(0))
            self.ret(200809)
        elif name == "__errno_location":
            self.ret(self.errno)
        elif name == "strncmp":
            a = bytes(self.uc.mem_read(self.arg(0), self.arg(2))).split(b"\0", 1)[0]
            b = bytes(self.uc.mem_read(self.arg(1), self.arg(2))).split(b"\0", 1)[0]
            self.ret((a > b) - (a < b))
        elif name == "strcmp":
            a, b = self.cstring(self.arg(0)), self.cstring(self.arg(1))
            self.ret((a > b) - (a < b))
        elif name == "realloc":
            old, count = self.arg(0), self.arg(1)
            new = self.allocate(count)
            if old:
                self.uc.mem_write(new, bytes(self.uc.mem_read(old, min(count, self.live[old][0]))))
                self.free(old)
            self.ret(new)
        elif name in ("__aeabi_uldivmod", "__aeabi_ldivmod"):
            dividend = self.arg(0) | self.arg(1) << 32
            divisor = self.arg(2) | self.arg(3) << 32
            if name == "__aeabi_ldivmod":
                dividend = C.c_int64(dividend).value
                divisor = C.c_int64(divisor).value
            quotient = abs(dividend) // abs(divisor) * (-1 if (dividend < 0) != (divisor < 0) else 1)
            remainder = dividend - quotient * divisor
            self.ret(quotient)
            for register, value in zip(REGS[1:], [quotient >> 32, remainder, remainder >> 32]):
                self.uc.reg_write(register, value & 0xffffffff)
        else:
            super().shim(uc, at, size, context)

    def add_provider(self):
        self.registered.append(self.arg(2))
        self.ret()

    def fallback(self):
        self.fallback_calls.append((self.string(self.arg(1)), self.arg(2), self.arg(3)))
        self.ret(FALLBACK)

    def drop_string(self, obj):
        # QString/QByteArray 的析构是 inline：共享数据引用由固定 Qt 入口处理。
        d = self.word(obj)
        count = self.word(d)
        if count != 0xffffffff:
            assert count > 0
            self.put(d, count - 1)
            if count == 1:
                self.call("_ZN10QArrayData10deallocateEPS_jj", [d, 1, 4])
        self.free(obj)

    def json_object(self, value):
        source = self.byte_array(json.dumps(value, separators=(",", ":")).encode())
        document = self.allocate(4, True)
        obj = self.allocate(8, True)
        self.call("_ZN13QJsonDocument8fromJsonERK10QByteArrayP15QJsonParseError", [document, source, 0])
        self.call("_ZNK13QJsonDocument6objectEv", [obj, document])
        self.call("_ZN13QJsonDocumentD1Ev", [document])
        self.free(document)
        self.drop_string(source)
        return obj

    def select(self, value):
        if self.record:
            self.call("_ZN11QJsonObjectD1Ev", [self.record])
            self.free(self.record)
        self.files = dict(value["files"])
        self.record = self.json_object(value["record"])
        self.record_accepted = bool(self.call("_ZN3X1D11recordValidERK11QJsonObject", [self.record]))
        return self.record_accepted

    def load_record(self):
        # 只替换 QFile/mount 边界；调用者可测试实际 recordValid 后再提供记录。
        if self.record and self.record_accepted:
            dst = self.arg(1)
            self.ret(1)
            # copy 共享两字布局，依据 Qt 5.5.1 QJsonObject copy 构造/析构契约。
            d = self.word(self.record)
            if d: self.put(d, self.word(d) + 1)
            self.uc.mem_write(dst, bytes(self.uc.mem_read(self.record, 8)))
        else:
            self.ret(0)

    def read_file(self):
        dst, path = self.arg(0), self.string(self.arg(1))
        offset = self.arg(2) | self.arg(3) << 32
        count, ok = self.arg(4), self.arg(5)
        self.reads.append((path, offset, count))
        data = self.files.get(path)
        failed = data is None or (self.file_failure and self.file_failure(path, offset, count))
        payload = b"" if failed else data[offset:offset + count]
        self.uc.mem_write(ok, bytes([not failed]))
        # 新 QByteArray 使用真实 QArrayData 分配布局，交给真实析构释放。
        d = self.allocate(16 + len(payload) + 1)
        self.uc.mem_write(d, struct.pack("<4I", 1, len(payload), len(payload) + 1, 16) + payload + b"\0")
        self.put(dst, d)
        self.ret(dst)

    def request(self, kind="preview", source="/artificial/a.raw"):
        id_obj = self.qstring(kind + source)
        size = self.allocate(8, True)
        wanted = self.allocate(8, True)
        answer = self.call(REQUEST, [self.provider, id_obj, size, wanted], budget=4_000_000_000)
        dimensions = struct.unpack("<2i", self.uc.mem_read(size, 8))
        self.drop_string(id_obj)
        self.free(size)
        self.free(wanted)
        return answer, dimensions

    def image_copy(self, texture):
        image = self.allocate(64, True)
        self.call(TEXTURE_IMAGE, [image, texture])
        return image

    def drop_image(self, image):
        self.call("_ZN6QImageD1Ev", [image])
        self.free(image)

    def pixel_pointer(self, image):
        return self.call("_ZNK6QImage9constBitsEv", [image])

    def gpu_create(self):
        self.gpu_images.append(self.arg(1))
        self.ret(0x34567890)

    def assert_fallback(self, kind="preview", source="/artificial/a.raw"):
        calls, current, releases = len(self.fallback_calls), self.current, self.permit_releases
        answer, _ = self.request(kind, source)
        assert answer == FALLBACK and len(self.fallback_calls) == calls + 1
        assert self.fallback_calls[-1][0] == kind + source
        assert self.current == current, ("失败路径分配未全部归还", current, self.current)
        return self.permit_releases - releases


def run():
    dll = build_container()
    good = fixture(dll)
    m = ProviderMachine()
    cases = []

    def done(name, **facts):
        cases.append({"case": name, **facts})
        print(name, flush=True)

    assert m.select(good)
    texture, size = m.request()
    assert texture not in (0, FALLBACK) and size == (1108, 830)
    im = m.image_copy(texture)
    data = m.pixel_pointer(im)
    with Image.open(io.BytesIO(good["preview"])) as decoded:
        expected = decoded.convert("RGBA").getpixel((0, 0))
    assert tuple(m.uc.mem_read(data, 4)) == (expected[2], expected[1], expected[0], 255)
    assert len(m.reads) == 3 and m.decodes == 1
    done("real-arm-preview-codec-and-qimage", dimensions=size, sourceReads=3, previewQuality=85)

    second, size = m.request("thumb")
    im2 = m.image_copy(second)
    assert size == (1108, 830) and m.pixel_pointer(im2) == data and m.decodes == 1
    assert len(m.reads) == 6
    m.drop_image(im2)
    m.call(TEXTURE_DELETE, [second])
    done("verified-cache-hit-shares-pixels-and-rechecks-three-reads")

    jpeg_path, raw_path = good["record"]["jpegPath"], good["record"]["rawPath"]
    m.files[raw_path] = m.files[raw_path][:-1] + b"\1"
    m.assert_fallback()
    m.files = dict(good["files"])
    m.files[jpeg_path] = m.files[jpeg_path][:-2]
    m.assert_fallback()
    m.files = dict(good["files"])
    modified = bytearray(m.files[jpeg_path]); modified[250] ^= 1
    m.files[jpeg_path] = bytes(modified)
    m.assert_fallback()
    m.files = dict(good["files"])
    m.file_failure = lambda path, offset, count: path == jpeg_path
    m.assert_fallback()
    m.file_failure = None
    done("cache-hit-rejects-source-change-missing-tail-changed-header-and-read-error", fallbacks=4)

    for field, value in [("version", 2), ("closed", False), ("bytes", -1), ("bytes", 128 * 1024 * 1024 + 1),
                         ("prefixBytes", 0), ("prefixBytes", 4 * 1024 * 1024 + 1), ("prefixBytes", good["record"]["bytes"]),
                         ("jpegPath", "relative.jpg"), ("jpegPath", "/a/../b.jpg"), ("jpegPath", "/a\\b.jpg"),
                         ("prefixHash", "A" * 64), ("jpegHash", "0" * 63), ("uidHash", 100), ("rawHash", "g" * 64)]:
        invalid = {"record": dict(good["record"], **{field: value}), "files": good["files"]}
        assert not m.select(invalid), (field, value)
        m.assert_fallback()
    done("real-qt-record-validator-rejects-malformed-records", variants=14)

    assert m.select(good)
    m.assert_fallback("unknown")
    m.record_accepted = False
    m.assert_fallback()
    m.record_accepted = True
    done("unsupported-request-and-no-record-use-original")

    changed = fixture(dll, color=(210, 35, 80), uid=b"ffeeddccbbaa99887766554433221100")
    assert m.select(changed)
    newer, _ = m.request()
    new_im = m.image_copy(newer)
    newer_data = m.pixel_pointer(new_im)
    assert newer_data != data and m.decodes == 2
    assert bytes(m.uc.mem_read(data, 4)) != bytes(m.uc.mem_read(newer_data, 4))
    m.call(TEXTURE_DELETE, [texture])
    assert data in m.live  # im 与缓存仍持有同一张旧图。
    m.drop_image(im)
    m.drop_image(new_im)
    m.call(TEXTURE_DELETE, [newer])
    done("same-path-new-capture-decodes-new-image-and-old-reference-remains-valid")

    broken = fixture(dll, bad_preview=True)
    assert m.select(broken)
    before = m.calls.get("longjmp", 0)
    m.assert_fallback()
    assert m.calls.get("longjmp", 0) > before
    done("structurally-valid-preview-invalid-dqt-rejected-by-original-codec")

    oriented = fixture(dll, orientation=6)
    assert m.select(oriented)
    scratch = m.call("xj_orient_scratch_bytes", [1108, 830, 6])
    m.fail_alloc_size = scratch
    m.assert_fallback()
    m.fail_alloc_size = 0
    third, size = m.request()
    assert size == (830, 1108)
    assert data not in m.live  # 两条缓存预算引发淘汰，旧图最后引用已释放。
    m.call(TEXTURE_DELETE, [third])
    done("orientation-scratch-failure-and-successful-cache-eviction", scratchBytes=scratch)

    assert m.select(good)
    m.permits = 0
    reads = len(m.reads)
    m.assert_fallback("fullsize")
    assert len(m.reads) == reads + 1  # 只做源身份检查，不读取 JPEG 或等待旧工厂。
    m.permits = 1
    done("full-buffer-busy-falls-back-once-before-jpeg-read")

    m.fail_alloc_size = 8176 * 6128 * 4
    assert m.assert_fallback("fullsize") == 1
    m.fail_alloc_size = 0
    assert m.permits == 1
    done("full-pixel-allocation-failure-releases-permit")

    payload = bytearray(good["files"][jpeg_path]); payload[-20] ^= 1
    m.files[jpeg_path] = bytes(payload)
    assert m.assert_fallback("fullsize") == 1
    m.files = dict(good["files"])
    m.file_failure = lambda path, offset, count: path == jpeg_path and offset == good["record"]["prefixBytes"]
    assert m.assert_fallback("fullsize") == 1
    m.file_failure = None
    done("full-hash-mismatch-and-chunk-read-error-release-permit")

    # 一个 Full 实际执行原固件 ARM 熵解码；模拟执行耗时不作为性能结论。
    print("running-real-arm-full-8176x6128", flush=True)
    full, size = m.request("fullsize", source=jpeg_path)
    assert full not in (0, FALLBACK) and size == (8176, 6128) and m.permits == 0
    full_im, render_copy = m.image_copy(full), m.image_copy(full)
    full_data = m.pixel_pointer(full_im)
    assert m.pixel_pointer(render_copy) == full_data
    assert m.live[full_data][0] == 8176 * 6128 * 4
    for index in [0, 8176 * 3064 + 4088, 8176 * 6128 - 1]:
        assert tuple(m.uc.mem_read(full_data + index * 4, 4)) == (expected[2], expected[1], expected[0], 255)
    create = "_ZNK12_GLOBAL__N_17Texture13createTextureEP12QQuickWindow"
    assert m.call(create, [full, 0]) == 0
    assert m.call(create, [full, 1]) == 0x34567890
    assert m.call(create, [full, 1]) == 0x34567890 and len(m.gpu_images) == 2
    m.assert_fallback("fullsize")
    m.call(TEXTURE_DELETE, [full])
    assert full_data in m.live and m.permits == 0
    m.drop_image(full_im)
    assert full_data in m.live and m.permits == 0
    m.drop_image(render_copy)
    assert full_data not in m.live and m.permits == 1
    done("real-arm-full-decode-and-last-qimage-reference-releases-single-permit", dimensions=size,
         cpuPixelBytes=8176 * 6128 * 4, textureFactoryRecreations=2, actualGpuUpload=False)

    m.call("_ZN12_GLOBAL__N_18ProviderD0Ev", [m.provider])
    assert not [p for p, (n, _) in m.live.items() if n >= 1108 * 830 * 4]
    done("provider-destruction-releases-preview-cache")
    report = {"status": "passed", "firmwareSource": "X1D-50c 1.25.0", "cameraAccess": False,
              "realArm": ["candidate provider/runtime/container/display", "Qt 5.5.1 JSON/QImage/refcount", "original TurboJPEG including Full 8176x6128"],
              "boundariesReplaced": ["record file/mount read", "Storage File replies", "libc allocation/time", "QSemaphore", "QObject factory base and primaryScreen", "window createTextureFromImage"],
              "codecSimd": "原 TurboJPEG 的 JSIMD_FORCENEON=1；Unicorn 执行其实际 ARM NEON 指令；不是实机能力探测",
              "notValidated": ["Linux/DBus/event loop", "real Qt reader cancellation scheduling", "GPU upload/limit/channel conversion", "camera latency/memory pressure"],
              "cases": cases, "caseGroups": len(cases), "originalFallbackCalls": len(m.fallback_calls),
              "realDecoderCalls": m.decodes, "fullPermitAcquires": m.permit_acquires, "fullPermitReleases": m.permit_releases,
              "moduleHashes": m.module_hashes,
              "sourceHashes": {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in
                               [Path(__file__), HERE / "CodeTests/arm_machine.py", HERE / "native/replay_provider.cpp", HERE / "native/replay_runtime.cpp"]}}
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "caseGroups": len(cases), "originalFallbackCalls": len(m.fallback_calls)}, ensure_ascii=False), flush=True)


if __name__ == "__main__": run()
