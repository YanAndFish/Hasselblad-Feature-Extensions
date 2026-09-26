"""补测实际 provider 的 ICC 路由、超时、codec 错误及原 NEON 指令选择。"""
from __future__ import annotations
import ctypes as C
import io
import json
from pathlib import Path
from PIL import Image, ImageCms
from arm_machine import ArmElf, HERE, X1D, TURBO, UC_HOOK_CODE
from run_provider import ProviderMachine, Info, TEXTURE_DELETE, build_container, fixture, jpeg, metadata, marker, sha

OUT = HERE / "artifacts/provider-edges"


class EdgeMachine(ProviderMachine):
    def __init__(self):
        self.timeout_on_tail = False
        super().__init__()

    def read_file(self):
        count = self.arg(4)
        super().read_file()
        if self.timeout_on_tail and count == 2: self.clock_step = 16


def with_profile(dll, profile):
    uid = b"00112233445566778899aabbccddeeff"
    raw = metadata(6, uid).ljust(128 * 1024, b"\0")
    main = jpeg((8176, 6128), (65, 110, 160))
    main = main[:2] + marker(0xe1, b"Exif\0\0" + raw[:4096]) + marker(0xe2, b"ICC_PROFILE\0\1\1" + profile) + main[2:]
    preview = jpeg((1108, 830), (65, 110, 160))
    count = C.c_uint32()
    assert dll.xj_embed_preview(main, len(main), preview, len(preview), None, 0, C.byref(count)) == 6
    output = C.create_string_buffer(count.value)
    assert dll.xj_embed_preview(main, len(main), preview, len(preview), output, len(output), C.byref(count)) == 0
    data = output.raw[:count.value]
    info = Info()
    assert dll.xj_inspect(data, len(data), C.byref(info)) == 0
    record = {"version": 3, "closed": True, "jpegPath": "/artificial/a.jpg", "rawPath": "/artificial/a.raw",
              "bytes": len(data), "prefixBytes": info.header_bytes, "orientation": 6,
              "rawHash": sha(raw), "uidHash": sha(uid), "prefixHash": sha(data[:info.header_bytes]), "jpegHash": sha(data)}
    return {"files": {record["jpegPath"]: data, record["rawPath"]: raw}, "record": record, "preview": preview}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    dll = build_container()
    profile = ArmElf.load("usr/bin/jpeg-daemon").read(0x27700, 560)
    assert sha(profile) == "304f569a83c1e5eddaddac54e99ed03339333db013738bb499ab64f049887e28"
    adobe = with_profile(dll, profile)
    m = EdgeMachine()
    cases = []
    observed = []
    hooks = []
    turbo = next(elf for elf, _, name in m.modules if name == "TurboJPEG")
    section = turbo.elf.get_section_by_name(".text")
    neon = [i for i in turbo.instructions(section["sh_addr"], section["sh_size"]) if i.mnemonic.startswith("vld1")]

    def seen_neon(uc, address, size, context):
        observed.append(address - TURBO)
        for hook in hooks: uc.hook_del(hook)

    for instruction in neon:
        address = TURBO + instruction.address
        hooks.append(m.uc.hook_add(UC_HOOK_CODE, seen_neon, begin=address, end=address))
    assert m.select(adobe)
    texture, size = m.request()
    assert size == (830, 1108)
    image = m.image_copy(texture)
    pixel = bytes(m.uc.mem_read(m.pixel_pointer(image), 4))
    with Image.open(io.BytesIO(adobe["preview"])) as decoded:
        source = Image.new("RGB", (1, 1), decoded.getpixel((0, 0)))
        expected = ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                            ImageCms.createProfile("sRGB"), renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC).getpixel((0, 0))
        assert max(abs(a - b) for a, b in zip((pixel[2], pixel[1], pixel[0]), expected)) <= 2
    assert pixel[3] == 255 and observed
    m.drop_image(image)
    m.call(TEXTURE_DELETE, [texture])
    cases.append({"case": "actual-fixed-icc-and-orientation-six-route", "dimensions": size,
                  "oracle": "Pillow/LittleCMS relative colorimetric <=2 per channel", "observedNeonVld1": hex(observed[0])})
    print("fixed-icc-route-and-original-neon-instruction-observed", flush=True)

    unknown = bytearray(profile); unknown[80] ^= 1
    assert m.select(with_profile(dll, bytes(unknown)))
    decodes = m.decodes
    m.assert_fallback()
    assert m.decodes == decodes
    cases.append({"case": "unknown-icc-is-rejected-before-decoding"})

    good = fixture(dll)
    assert m.select(good)
    m.clock_step = 7
    m.assert_fallback()
    m.clock_step = 0
    cases.append({"case": "prefix-six-second-budget"})
    m.timeout_on_tail = True
    assert m.assert_fallback("fullsize") == 1 and m.permits == 1
    m.clock_step = 0
    m.timeout_on_tail = False
    cases.append({"case": "full-fifteen-second-budget-and-permit-release"})

    init = m.word(m.codec_table + 8)
    m.put(m.codec_table + 8, m.callback("injected-init-decompress-failure", lambda: m.ret(0)))
    m.assert_fallback()
    m.put(m.codec_table + 8, init)
    decode = m.word(m.codec_table + 36)
    m.put(m.codec_table + 36, m.callback("injected-decompress-failure", lambda: m.ret(-1)))
    m.assert_fallback()
    m.put(m.codec_table + 36, decode)
    cases.append({"case": "codec-init-and-post-allocation-decode-failure-cleanup"})
    m.call("_ZN12_GLOBAL__N_18ProviderD0Ev", [m.provider])
    report = {"status": "passed", "cameraAccess": False, "caseGroups": len(cases), "cases": cases,
              "notValidated": ["real deadlines/DBus latency", "GPU", "physical display calibration"],
              "moduleHashes": m.module_hashes,
              "sourceHashes": {p.relative_to(X1D.parent).as_posix(): sha(p.read_bytes()) for p in
                               [Path(__file__), HERE / "CodeTests/arm_machine.py", HERE / "CodeTests/run_provider.py"]}}
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "caseGroups": len(cases)}), flush=True)


if __name__ == "__main__": run()
