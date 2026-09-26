"""在固定 WLTEST/probe10 基线上添加预先准备的单次发射入口，不访问硬件。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "build"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parents[2] / ".research-cache/x1d-1.25.0/python"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
BASE = 0x180000
BASE_SHA = "e5eb76a8b333e402b213843e2e93ff771615adcbc05ca7113d04ef0951555159"
PROBE10_SHA = "84301b234aef69a09f525b726dcf252e48d8b37d43529900eab34181e02163af"
FAST = 0x216800
CACHED = 0x216A00
STATE = 0x2147E0
HEAP = 0x216B00


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def branch(src, dst, link=False):
    delta = dst - (src + 4)
    if delta & 1 or not -(1 << 24) <= delta < 1 << 24:
        raise ValueError("Thumb 跳转越界")
    sign = (delta >> 24) & 1
    j1 = 1 ^ ((delta >> 23) & 1) ^ sign
    j2 = 1 ^ ((delta >> 22) & 1) ^ sign
    a = 0xF000 | sign << 10 | ((delta >> 12) & 0x3FF)
    b = (0xD000 if link else 0x9000) | j1 << 13 | j2 << 11 | ((delta >> 1) & 0x7FF)
    return struct.pack("<HH", a, b)


def mov16(reg, value, top=False):
    a = (0xF2C0 if top else 0xF240) | ((value >> 12) & 15) | ((value >> 11) & 1) << 10
    b = ((value >> 8) & 7) << 12 | reg << 8 | (value & 255)
    return struct.pack("<HH", a, b)


def cached_hash():
    """只有本模块保持 MAC 占用且预先校验完成时，才返回已有校验值。"""
    code = bytearray(mov16(2, STATE & 0xFFFF) + mov16(2, STATE >> 16, True))
    failures = []
    for offset in (16, 0, 8):
        code += struct.pack("<HH", 0x6800 | (offset // 4) << 6 | 2 << 3, 0x2801)
        failures.append(len(code))
        code += b"\0\0"
    code += struct.pack("<HH", 0x6850, 0x4770)  # hash; return
    failure = len(code)
    code += struct.pack("<HH", 0x2000, 0x4770)
    for offset in failures:
        delta = failure - (offset + 4)
        code[offset:offset + 2] = struct.pack("<H", 0xD100 | (delta // 2 & 255))
    return bytes(code)


def build():
    baseline = (OUT / "vendor-wltest.bin").read_bytes()
    if len(baseline) != 606750 or sha(baseline) != BASE_SHA:
        raise RuntimeError("官方 WLTEST 基线不匹配")
    original = bytearray(baseline)
    inputs = json.loads((HERE / "probe10-inputs.json").read_text(encoding="utf-8"))
    for patch in inputs["patches"]:
        offset = patch["offset"]
        block = (HERE / patch["file"]).read_bytes()
        if sha(block) != patch["sha256"]:
            raise RuntimeError("probe10 输入块校验失败")
        original[offset:offset + len(block)] = block
    if sha(original) != PROBE10_SHA:
        raise RuntimeError("probe10 重建校验失败")

    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    source = 0x216100
    function = bytes(original[source - BASE:source - BASE + 370])
    fast = bytearray(function)
    rewritten_calls = []
    kept_ready = []
    for ins in decoder.disasm(function, source):
        offset = ins.address - source
        if ins.mnemonic == "bl":
            target = int(ins.op_str.lstrip("#"), 0)
            if target == 0x214A00:
                target = CACHED
            fast[offset:offset + 4] = branch(FAST + offset, target, True)
            rewritten_calls.append([offset, target])
        if offset < 0xF0 and ins.mnemonic == "str.w" and ins.op_str in ("r0, [r2]", "r0, [r2, #8]"):
            # 预先校验的波形在 MAC 持续占用期间只读复用；原 selector 30 仍是一次性路径。
            fast[offset:offset + 4] = b"\x00\xbf" * 2
            kept_ready.append(offset)
    if len(kept_ready) != 2 or not any(target == CACHED for _, target in rewritten_calls):
        raise RuntimeError("不能定位原发射函数的就绪消费和校验调用")

    code = bytearray(original)
    cache = cached_hash()
    code.extend(b"\0" * (CACHED + len(cache) - BASE - len(code)))
    code[FAST - BASE:FAST - BASE + len(fast)] = fast
    code[CACHED - BASE:CACHED - BASE + len(cache)] = cache
    code[0x214404 - BASE:0x214408 - BASE] = mov16(0, 0x584E)
    # selector 40: 固定普通 D 组波形，不允许切到全零或其它模式。
    entry = 0x2146A8
    dispatch = struct.pack("<HHH", 0x2928, 0xD102, 0x2100) + branch(entry + 6, FAST)
    dispatch += branch(entry + len(dispatch), 0x1C620E)
    code[entry - BASE:entry - BASE + len(dispatch)] = dispatch
    code[0x1E1838 - BASE:0x1E183C - BASE] = struct.pack("<I", HEAP)

    # 独立反汇编核对所有被重定位的调用目标。
    decoded = {i.address: i for i in decoder.disasm(bytes(fast), FAST)}
    for offset, target in rewritten_calls:
        ins = decoded[FAST + offset]
        if ins.mnemonic != "bl" or int(ins.op_str.lstrip("#"), 0) != target:
            raise RuntimeError("快速入口调用重定位失败")
    dispatch_ins = list(decoder.disasm(dispatch, entry))
    if dispatch_ins[1].op_str != "#0x2146b2" or dispatch_ins[3].op_str != "#0x216800":
        raise RuntimeError("新选择器分发校验失败")
    if code[0x216100 - BASE:0x216100 - BASE + 370] != function:
        raise RuntimeError("原发射路径被意外改变")
    if CACHED + len(cache) >= HEAP:
        raise RuntimeError("新增代码越过堆边界")

    output = bytes(code)
    (OUT / "prepared-wltest.bin").write_bytes(output)
    delta = OUT / "delta"
    delta.mkdir(exist_ok=True)
    blocks = [(307100, 307104), (399416, 399420), (606750, len(output))]
    for index, (start, end) in enumerate(blocks):
        (delta / (str(index) + ".bin")).write_bytes(output[start:end])
    manifest = {"baselineSha256": BASE_SHA, "probe10Sha256": PROBE10_SHA,
                "preparedSha256": sha(output), "marker": "584e", "fastSelector": 40,
                "length": len(output), "cachedRoutine": CACHED, "fastRoutine": FAST,
                "heapStart": HEAP, "relocatedCalls": rewritten_calls,
                "readyStoresReplaced": kept_ready, "deltaRanges": blocks,
                "hardwareRequests": 0, "hardwareTimingVerified": False,
                "requirement": "设置时完成生成和完整校验；就绪期间保持 MAC 占用；关闭或退出时 release 清除资格。"}
    (OUT / "prepared-firmware.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
