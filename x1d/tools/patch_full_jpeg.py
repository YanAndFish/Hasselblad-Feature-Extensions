"""仅为官方 1.25.0 的 Wedge/X1D 生成 Full JPEG 配置候选，不操作相机。"""
from __future__ import annotations

import hashlib
import json
import struct

from binary import ArmElf, ROOT
from patch_jpeg_failure import branch

SOURCE_SHA = "0d24d3d3787bab08ab2c0b4f4c0f3d72831d2216eddc770a60b6742174ce4be1"
OUTPUT = ROOT / "x1d/artifacts/full-jpeg-v1"


def build(source: bytes | None = None) -> tuple[bytes, dict]:
    original = ArmElf.load("usr/bin/configstore") if source is None else ArmElf(source)
    if hashlib.sha256(original.data).hexdigest() != SOURCE_SHA:
        raise ValueError("不是已绑定的第一代 X1D 1.25.0 configstore 基线")
    # 原构造函数已经读取 Version::productID；2 的绑定见 SOURCE_AND_FLASH_SCOPE.md。
    # 重排同一段无调用尾部，共用原 epilogue；不新增栈帧，不改 ELF/异常表布局。
    at = 0x23F18
    values = [
        0xE3500002,                              # cmp r0, #2
        0x0584042C,                              # streq r0, [r4, #jpg_size]
        0x05840430,                              # streq r0, [r4, #jpg_size_minval]
        0x05840434,                              # streq r0, [r4, #jpg_size_maxval]
        0x03A03003,                              # moveq r3, #3，原 Wedge 值
        branch(0x23F2C, 0x23F3C, condition=0),
        0xE1500006,                              # cmp r0, r6，其他板型原判断
        0x03A03009,                              # moveq r3, #9
        branch(0x23F38, 0x23F40, condition=1),
        0xE58434C8,                              # str r3, [r4, #0x4c8]
        0xE1A00004,                              # mov r0, r4
        0xE28DD014,                              # add sp, sp, #0x14
        0xE8BD8FF0,                              # pop {r4-r11, pc}
    ]
    after = struct.pack("<13I", *values)
    before = original.read(at, len(after))
    offset = original.offset(at, len(after))
    candidate = bytearray(original.data)
    candidate[offset:offset + len(after)] = after
    result = bytes(candidate)
    if len(result) != len(original.data):
        raise ValueError("ELF 大小变化")
    report = {
        "schemaVersion": 1, "model": "X1D-50c (first generation)", "firmware": "1.25.0",
        "sourceSha256": SOURCE_SHA, "candidateSha256": hashlib.sha256(result).hexdigest(),
        "bytes": len(result), "address": f"0x{at:x}", "offset": offset,
        "before": before.hex(), "after": after.hex(),
        "productId": 2, "jpgSize": 2, "jpgSizeMin": 2, "jpgSizeMax": 2,
        "status": "离线组件候选；Full 选源参数已修改，实际 Full 编码、预览封装和回放尚未联调",
        "cameraAccess": False, "cimCreated": False,
        "requires": ["配合 JPEG 失败传播候选", "实际 Full 输入与颜色验证", "文件内嵌预览",
                     "异步写入完成登记", "统一 JPEG 回放", "正常部署入口与实机验证"],
    }
    return result, report


def run() -> None:
    candidate, report = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "configstore.elf").write_bytes(candidate)
    (OUTPUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("已生成仅对 Wedge/X1D 生效的 Full 配置候选；原包未修改，未生成 CIM。")


if __name__ == "__main__":
    run()
