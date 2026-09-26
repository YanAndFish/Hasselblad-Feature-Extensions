"""实际 ARM 写入适配层的准备/单次提交检查；原写入与 DBus watcher 是替身。"""
from __future__ import annotations
import ctypes as C
import io
import json
from pathlib import Path
from PIL import Image

from arm_machine import ArmMachine, HERE, X1D
from run_provider import ProviderMachine, Info, jpeg, metadata, marker, sha, build_container

OUT = HERE / "artifacts/adapter-tests"
IMAGE = "_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile"
WRITE = "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString"


class AdapterMachine(ProviderMachine):
    def __init__(self, raw):
        self.files = {"/artificial/a.raw": raw}
        self.file_failure = None
        self.reads = []
        self.clock_seconds, self.clock_step = 1, 0
        ArmMachine.__init__(self, force_neon=True)
        self.errno = self.allocate(4, True)
        self.hash_seed = self.allocate(4, True)
        self.uc.mem_write(self.hash_seed, b"0\0")
        self.bind("_ZN3X1D8readFileERK7QStringyiPb", self.read_file)
        self.bind("_ZN7QObject11deleteLaterEv", self.defer_watcher)
        self.proxy = self.allocate(32, True)
        self.raw = self.qstring("/artificial/a.raw")
        self.target = self.qstring("/artificial/a.jpg")

    def defer_watcher(self):
        self.deferred.append(self.arg(0))
        self.ret()

    def shim(self, uc, at, size, context):
        name = self.entries[at]
        if name == "getenv" and self.cstring(self.arg(0)) == "QT_HASH_SEED":
            self.ret(self.hash_seed)
        elif name == "_ZN10QDBusErrorC1ENS_9ErrorTypeERK7QString":
            error, code, message = self.arg(0), self.arg(1), self.word(self.arg(2))
            if self.word(message) != 0xffffffff: self.put(message, self.word(message) + 1)
            self.put(error, code)
            self.put(error + 4, message)
            self.put(error + 8, self.symbols["_ZN10QArrayData11shared_nullE"])
            self.put(error + 12, 0)
            self.ret(error)
        else:
            super().shim(uc, at, size, context)

    def associate(self, resolution=2):
        self.call(IMAGE, [self.proxy, self.raw, resolution, 0], stop=0x178c8)

    def submit(self, payload, caller=0x1e2e0):
        obj = self.byte_array(payload)
        answer = self.call(WRITE, [self.proxy, obj, 0, 0, self.target], stop=caller, budget=4_000_000_000)
        self.drop_string(obj)
        return answer


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    dll = build_container()
    tiff = metadata(1, b"112233445566778899aabbccddeeff00")
    raw = tiff.ljust(128 * 1024, b"\0")
    main = jpeg((8176, 6128), (65, 110, 160))
    source = main[:2] + marker(0xe1, b"Exif\0\0" + tiff) + main[2:]
    m = AdapterMachine(raw)
    cases = []

    def done(name, **facts):
        cases.append({"case": name, **facts})
        print(name, flush=True)

    m.submit(b"unrelated-client-bytes", caller=0x12340)
    assert len(m.writes) == 1 and m.writes[-1][1] == b"unrelated-client-bytes"
    done("unrelated-callsite-is-forwarded-once")

    m.associate(resolution=1)
    m.submit(b"other-resolution-bytes")
    assert len(m.writes) == 2 and m.writes[-1][1] == b"other-resolution-bytes"
    done("non-full-request-preserves-original-client-behavior")

    broken = bytearray(source); broken[broken.index(b"\xff\xdb") + 4] = 0xff
    before = len(m.writes)
    m.associate()
    watcher = m.submit(bytes(broken))
    assert len(m.writes) == before and watcher in m.failed_watchers and watcher in m.deferred
    assert m.calls.get("longjmp", 0) > 0
    done("invalid-main-dqt-is-never-written-and-failure-watcher-is-deferred")

    m.associate()
    m.fail_alloc_size = 2044 * 1532 * 3
    watcher = m.submit(source)
    m.fail_alloc_size = 0
    assert len(m.writes) == before and watcher in m.failed_watchers
    done("main-decode-buffer-allocation-failure-is-never-written")

    print("running-real-arm-optional-preview-failure", flush=True)
    m.associate()
    m.fail_alloc_size = 1108 * 830 * 3
    m.submit(source)
    m.fail_alloc_size = 0
    assert len(m.writes) == before + 1 and m.writes[-1][1] == source
    done("optional-preview-allocation-failure-writes-validated-original-once")

    print("running-real-arm-enhanced-write", flush=True)
    m.associate()
    m.submit(source)
    assert len(m.writes) == before + 2
    target, enhanced = m.writes[-1]
    info = Info()
    assert target == "/artificial/a.jpg" and dll.xj_inspect(enhanced, len(enhanced), C.byref(info)) == 0
    assert (info.width, info.height, info.preview_kind) == (8176, 6128, 1)
    needed = C.c_uint32()
    dll.xj_extract_preview.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32)]
    assert dll.xj_extract_preview(enhanced, info.header_bytes, None, 0, C.byref(needed)) == 6
    preview = C.create_string_buffer(needed.value)
    assert dll.xj_extract_preview(enhanced, info.header_bytes, preview, len(preview), C.byref(needed)) == 0
    with Image.open(io.BytesIO(preview.raw)) as decoded:
        decoded.load()
        assert decoded.size == (1108, 830)
        with Image.open(io.BytesIO(jpeg((1108, 830), (65, 110, 160), 85))) as reference:
            assert decoded.quantization == reference.quantization
    source_info = Info()
    assert dll.xj_inspect(source, len(source), C.byref(source_info)) == 0
    assert enhanced[info.header_bytes:] == source[source_info.header_bytes:]
    assert not [n for n, _ in m.live.values() if n >= 1108 * 830 * 3]
    done("original-arm-codec-builds-q85-preview-and-commits-one-complete-container", previewBytes=needed.value,
         mainEntropyUnchanged=True, watcherReplyAndRecordPublicationTested=False)

    report = {"status": "passed", "firmwareSource": "X1D-50c 1.25.0", "cameraAccess": False,
              "cases": cases, "caseGroups": len(cases), "realArm": ["candidate jpeg_adapter/runtime/container/preview", "Qt Core strings/JSON/hash", "original TurboJPEG decoding/encoding"],
              "boundariesReplaced": ["libc and synchronization", "Storage image/write/read", "QObject/DBus failure watcher"],
              "notValidated": ["actual write/close reply", "QSaveFile record publication", "signals and event loop", "camera capture/latency"],
              "codecSimd": "JSIMD_FORCENEON=1 through bounded getenv replacement",
              "moduleHashes": m.module_hashes,
              "sourceHashes": {p.relative_to(X1D.parent).as_posix(): sha(p.read_bytes()) for p in
                               [Path(__file__), HERE / "CodeTests/arm_machine.py", HERE / "CodeTests/run_provider.py", HERE / "native/jpeg_adapter.cpp"]}}
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "caseGroups": len(cases)}, ensure_ascii=False), flush=True)


if __name__ == "__main__": run()
