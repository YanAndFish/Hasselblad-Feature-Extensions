"""复核固定 X2D 4.2.0 ELF 的电子快门同步分支；只读文件，不执行或修改固件。"""
import hashlib
import json
import struct

from inspect_phocus import Binary, HASHES, ROOT


FUNCTION_GROUPS = {
    "x2d-4.2.0-Camx_StartExpo.asm.txt": [
        ("Camx_StartExpo", 0xA3B90, 3328),
    ],
    "x2d-4.2.0-Fsync-Xsync.asm.txt": [
        ("Camx_FlashEnable", 0xA63D8, 248),
        ("FsyncCtrl_SetupAndEnable", 0xA7340, 708),
        ("FsyncCtrl_TriggerXsync", 0xA76B8, 172),
    ],
}
CONTEXT_RANGES = [
    ("Camx_PreStartExpo: 字段初始化和非默认模式断言", 0xA2758, 0xA2830),
    ("Camx_PreStartExpo: 镜头类型结果及状态字节初始化", 0xA28C0, 0xA28FC),
    ("Camx_PreStartExpo: 非 HBL 镜头判定", 0xA2A00, 0xA2A18),
    ("Camx_PreStartExpo: 错误路径清除镜头状态字节", 0xA2C70, 0xA2CF0),
    ("Camx_PreStartExpo: UserEShutter 断言", 0xA2B08, 0xA2B34),
    ("Camx_SetSensorMode: 参数保存", 0xA6B60, 0xA6B94),
    ("Camx_SetSensorMode: 退出/进入模式时写入 +0x1ac", 0xA6D60, 0xA6DC8),
    ("Camx_Init: 默认模式 -1", 0xA6F08, 0xA6F54),
    ("FsyncCtrl_Init: XSYNX_MUX 缺失路径", 0xA7124, 0xA71AC),
]
EXPECTED_INSTRUCTIONS = {
    0xA4244: ("mov", "w25, #3"),
    0xA42A8: ("mov", "w1, w25"),
    0xA43A4: ("ldrb", "w9, [x19, #0x69]"),
    0xA43AC: ("mov", "w25, wzr"),
    0xA43D8: ("cset", "w25, eq"),
    0xA43F4: ("mov", "w25, wzr"),
    0xA44D0: ("cbz", "w25, #0xa4850"),
    0xA44D8: ("bl", "#0xa76b8"),
    0xA4554: ("cbz", "w25, #0xa4560"),
    0xA455C: ("bl", "#0xa76b8"),
    0xA76D0: ("bl", "#0xe2be0"),
    0xA76D4: ("mov", "w0, #0x3e8"),
    0xA76D8: ("bl", "#0x1b08e8"),
    0xA76E0: ("bl", "#0xe2be0"),
}
EXPECTED_STRINGS = {
    0x1D8D55: "!Expo->LensLongExposure",
    0x1D8D98: "Expo->UserSettings.user_shutter_mode != DCAM_USER_SHUTTER_MODE_ELECTRONIC",
    0x1D8E7E: "[rcam]: [%s][%s:%d]Lens version info --> Not HBL-lens, lens disconnected",
    0x1D8F1F: "!Expo->UserEShutter",
    0x1D93F3: "Expo->UserEShutter",
    0x1DA4DC: "[rcam]: [%s][%s:%d]Cannot find gpio XSYNX_MUX in table",
}


def listing(binary, title, start, size):
    lines = ["", f"# {title} {start:#x} size={size}"]
    for ins in binary.cs.disasm(binary.read(start, size), start):
        note = ""
        if ins.mnemonic in ("bl", "b") and ins.operands[0].type == 2:
            note = binary.names.get(ins.operands[0].imm, "")
        lines.append(f"{ins.address:08x}  {ins.mnemonic:8} {ins.op_str:38} {note}".rstrip())
    return lines


def main():
    binary = Binary("librcam.so")
    for address, expected in EXPECTED_INSTRUCTIONS.items():
        ins = next(binary.cs.disasm(binary.read(address, 4), address))
        if (ins.mnemonic, ins.op_str) != expected:
            raise ValueError(f"指令不匹配: {address:#x}")
    for address, expected in EXPECTED_STRINGS.items():
        if binary.read(address, len(expected) + 1) != expected.encode("ascii") + b"\0":
            raise ValueError(f"证据字符串不匹配: {address:#x}")
    table_address = 0x209A4C
    targets = [table_address + n for n in struct.unpack("<4i", binary.read(table_address, 16))]
    if targets != [0xA7424, 0xA7420, 0xA74F8, 0xA7560]:
        raise ValueError("同步模式跳表不匹配")
    header = [
        "# 第一代 X2D 100C 官方固件 4.2.0 — 原始离线反汇编摘录",
        "# binary .research-cache/system-librcam.so",
        "# SHA-256 " + HASHES["librcam.so"],
        "# ELF 虚拟地址；非实机运行轨迹；没有生成或应用 patch",
        "# 复现: py -3.11 tools/trace_eshutter.py",
    ]
    outputs = {}
    for filename, entries in FUNCTION_GROUPS.items():
        lines = header[:]
        for name, address, size in entries:
            symbol = next(s for s in binary.symbols if s.name == name)
            if (symbol["st_value"], symbol["st_size"]) != (address, size):
                raise ValueError(f"符号范围不匹配: {name}")
            lines += listing(binary, name, address, size)
        outputs[filename] = lines
    context = header[:]
    for name, start, end in CONTEXT_RANGES:
        context += listing(binary, name, start, end - start)
    context += ["", "# 已逐字节校验的断言/日志文本；没有转储其他常量"]
    context += [f"{address:08x}  {value}" for address, value in EXPECTED_STRINGS.items()]
    context += ["", "# FsyncCtrl_SetupAndEnable 模式跳表，基址 0x209a4c"]
    context += [f"mode {i} -> {target:#x}" for i, target in enumerate(targets)]
    outputs["x2d-4.2.0-eshutter-context.asm.txt"] = context
    manifest = {"firmware": "X2D 100C 4.2.0", "binary_sha256": HASHES["librcam.so"], "instruction_checks": len(EXPECTED_INSTRUCTIONS), "string_checks": len(EXPECTED_STRINGS), "mode_targets": [hex(a) for a in targets], "artifacts": []}
    for filename, lines in outputs.items():
        content = ("\n".join(lines) + "\n").encode("utf-8")
        (ROOT / "research" / filename).write_bytes(content)
        manifest["artifacts"].append({"file": filename, "sha256": hashlib.sha256(content).hexdigest()})
    (ROOT / "research/eshutter-evidence-checks.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
