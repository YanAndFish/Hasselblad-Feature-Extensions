"""生成绑定官方 1.25.0 的离线 JPEG 错误处理候选；没有 CIM 打包/设备入口。"""
from __future__ import annotations

import hashlib
import json
import struct

from binary import ArmElf, ROOT

SOURCE_SHA = "ad4092c0a36344427d018af03c9ff8b5524c02627edadaab7217641ac3bf274a"
OUTPUT = ROOT / "x1d/artifacts/jpeg-failure-v1"


def branch(at: int, target: int, *, link: bool = False, condition: int = 14) -> int:
    delta = target - (at + 8)
    if at % 4 or target % 4 or not -(1 << 25) <= delta < 1 << 25:
        raise ValueError("ARM 分支超出编码范围")
    return (condition << 28) | (0x0B000000 if link else 0x0A000000) | ((delta >> 2) & 0xFFFFFF)


def build(source: bytes | None = None) -> tuple[bytes, dict]:
    original = ArmElf.load("usr/bin/jpeg-daemon") if source is None else ArmElf(source)
    if hashlib.sha256(original.data).hexdigest() != SOURCE_SHA:
        raise ValueError("不是已绑定的第一代 X1D 1.25.0 JPEG 基线")
    candidate = bytearray(original.data)
    edits = []

    def replace(at: int, content: bytes, purpose: str) -> None:
        offset = original.offset(at, len(content))
        before = original.read(at, len(content))
        for edit in edits:
            if max(offset, edit["offset"]) < min(offset + len(content), edit["offset"] + edit["bytes"]):
                raise ValueError("补丁区域重叠")
        candidate[offset:offset + len(content)] = content
        edits.append({"address": f"0x{at:x}", "offset": offset, "bytes": len(content),
                      "before": before.hex(), "after": content.hex(), "purpose": purpose})

    def words(at: int, values: list[int], purpose: str) -> None:
        replace(at, struct.pack("<" + "I" * len(values), *values), purpose)

    # 两个错误出口都在保留 r0 返回码时返回；成功与跨尾复制不变。
    words(0x234FC, [branch(0x234FC, 0x2350C, condition=1)], "Get 失败直接返回非零状态")
    # 原错误日志区在两个错误出口重定向后空出。新增适配均不建立 C++ 栈帧：
    # Qt 调用仍保持原调用者返回位置；SWReset 是 C 接口，调用前后恢复八字节栈。
    words(0x2354C, [
        branch(0x2354C, 0x2350C),                         # Update 失败返回
        0xE3500000,                                      # CHECK_BUSY: cmp r0, #0
        branch(0x23554, 0x1556C, condition=0),            # 成功尾调原 IsBusy
        branch(0x23558, 0x2355C),
        0xE92D4001,                                      # RESET: push {r0, lr}
        0xE5940040,                                      # ldr r0, [r4, #64]
        0xE3A01000,                                      # mov r1, #0
        branch(0x23568, 0x15E84, link=True),              # SWReset(handle, 0)
        0xE8BD4002,                                      # pop {r1, lr}，原错误码
        branch(0x23570, 0x2628C),                         # 原失败通知/清理
        0xE1A01000,                                      # FINAL_FAIL: mov r1, r0
        branch(0x23578, 0x2628C),                         # 已取 OutputInfo，不再 reset
        0xE1A0100B,                                      # GET_INFO: mov r1, fp
        0xE5940040,                                      # ldr r0, [r4, #64]
        branch(0x23584, 0x15B6C),                         # 尾调原 GetOutputInfo
        0xE1A00004,                                      # EMIT: mov r0, r4
        0xE1A01005,                                      # mov r1, r5
        branch(0x23590, 0x26D8C),                         # 尾调原 encodeFinished
        0xE5912000,                                      # CONVERT_GUARD: ldr r2, [r1]
        0xE5922004,                                      # ldr r2, [r2, #4]
        0xE3520000,                                      # cmp r2, #0
        0xD12FFF1E,                                      # bxle lr：空结果不写文件
        0xE5903008,                                      # 搬入原 ConvertCall 首指令
        branch(0x235A8, 0x1E084),                         # 返回原函数序言
    ], "原错误日志区域内的返回值检查、清理和空结果保护")
    words(0x258A8, [branch(0x258A8, 0x23550, link=True)], "忙循环取出失败终止；原首轮 IsBusy 仍正常执行")
    words(0x258D0, [0xE3500000, branch(0x258D4, 0x2355C, condition=1),
                    branch(0x258D8, 0x2357C, link=True)], "GetOutputInfo 前检查末段取出状态")
    words(0x25904, [0xE3500000, branch(0x25908, 0x23574, condition=1),
                    branch(0x2590C, 0x23588, link=True)], "完成通知前检查最终取出状态")
    words(0x1E080, [branch(0x1E080, 0x23594)], "ConvertCall 空结果直接返回；Encoder 仍负责结束与推进队列")
    prefix = b"VPU output transfer failed:  "
    if original.read(0x27E98, len(prefix)) != b"vpu_EncGetOutputInfo failed: ":
        raise ValueError("错误消息基线变化")
    replace(0x27E98, prefix, "共用错误消息覆盖取出与 OutputInfo 失败，避免错误归因")
    result = bytes(candidate)
    if len(result) != len(original.data):
        raise ValueError("ELF 大小变化")
    report = {
        "schemaVersion": 1, "model": "X1D-50c (first generation)", "firmware": "1.25.0",
        "sourceSha256": SOURCE_SHA, "candidateSha256": hashlib.sha256(result).hexdigest(),
        "bytes": len(result), "patches": edits,
        "status": "仅离线组件候选，尚不可宣称机身可安装或已修复回放卡顿",
        "cameraAccess": False, "cimCreated": False,
        "remaining": ["VPU 故障后实机资源恢复", "存储完成确认", "Full 替换 Quarter",
                      "内嵌预览及统一回放来源", "实际部署入口", "性能测量"],
    }
    return result, report


def run() -> None:
    candidate, report = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "jpeg-daemon.elf").write_bytes(candidate)
    (OUTPUT / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"离线 JPEG 组件候选已生成：{len(report['patches'])} 处区域，原 ELF 大小与基线保持；未生成 CIM。")


if __name__ == "__main__":
    run()
