"""固定 4.2.0 调试 getter、编码及正常能力范围的离线证据；不访问设备。"""
import contextlib
import io
import json
import re
import struct

from inspect_phocus import Binary, HASHES, ROOT
from inspect_phocus_pc import PCBinary, SHA256 as PC_SHA256


def run():
    binary = Binary()
    pc = PCBinary()
    checks = []

    def verify(label, actual, expected):
        if actual != expected:
            raise ValueError("静态证据不符：" + label)
        checks.append({"label": label, "verified": True, "value": actual})

    def instruction(address, mnemonic, operands):
        items = list(binary.cs.disasm(binary.read(address, 4), address))
        actual = [items[0].mnemonic, items[0].op_str] if len(items) == 1 else []
        verify(hex(address), actual, [mnemonic, operands])

    definitions = {
        25: ("flash_recharge_delay", 0x9278c, 0x3f8, 0x117c70, "i<十进制整数>"),
        87: ("flash_ev_adj / 12.0", 0x92908, 0x3e8, 0x117c40, "f<double 的十六进制位模式>"),
        88: ("eshutter_current", 0x928e8, 0x310, 0x117970, "i0 / i1"),
        61: ("attached_lens != 0", 0x91cc8, 0x1d8, 0x1174f0, "i0 / i1"),
    }
    for parameter, (_, case, offset, getter, _) in definitions.items():
        verify("ID " + str(parameter) + " 读取跳表", hex(0x91128 + struct.unpack("<H", binary.read(0x195538 + (parameter - 2) * 2, 2))[0] * 4), hex(case))
        verify("ID " + str(parameter) + " CameraProxyDbus 虚表", hex(struct.unpack("<Q", binary.read(0x219788 + 16 + offset, 8))[0]), hex(getter))

    for values in [
        (0x92794, "ldr", "x8, [x8, #0x3f8]"),
        (0x9340c, "mov", "w10, #2"),
        (0x92910, "ldr", "x8, [x8, #0x3e8]"),
        (0x92918, "fmov", "d0, #12.00000000"),
        (0x92920, "fdiv", "d0, d1, d0"),
        (0x93d08, "mov", "w10, #3"),
        (0x93d18, "stur", "d0, [x29, #-0xe0]"),
        (0x928f0, "ldr", "x8, [x8, #0x310]"),
        (0x92c04, "and", "w10, w0, #1"),
        (0x91cd0, "ldr", "x8, [x8, #0x1d8]"),
        (0x91cdc, "tst", "w0, #0xff"),
        (0x91ce4, "cset", "w10, ne"),
        (0x117c90, "ldr", "w0, [x19, #0xa8]"),
        (0x117c60, "ldr", "w0, [x19, #0xa4]"),
        (0x117990, "ldrb", "w0, [x19, #0x76]"),
        (0x117510, "ldrb", "w0, [x19, #0x12]"),
        (0x1440fc, "cbz", "w9, #0x14411c"),
        (0x144160, "bl", "#0x3d090"),
        (0x95750, "ldr", "x3, [x8, x26, lsl #3]"),
        (0xa46f4, "bl", "#0x7c7c8"),
        (0xa4700, "bl", "#0x69918"),
        (0x98400, "ldr", "x8, [x9, #0x400]"),
        (0x98bc4, "ldr", "x8, [x8, #0x3f0]"),
        (0x98b74, "ldr", "x8, [x8, #0x318]"),
    ]:
        instruction(*values)
    for address, expected in [(0x1824bb, b"f"), (0x1824d3, b"%llx"), (0x1824b7, b"i"), (0x1824d0, b"%d")]:
        verify(hex(address) + " 格式字面", binary.read(address, len(expected) + 1).rstrip(b"\0").decode(), expected.decode())
    verify("type3 前缀跳表", hex(0x9555c + binary.read(0x195686 + 3, 1)[0] * 4), "0x955d8")
    verify("type3 数值跳表", hex(0x956b4 + binary.read(0x19568c + 3, 1)[0] * 4), "0x9573c")

    data = binary.read(0x1a68a8, 7324)
    strings = binary.read(0x1a1010, 22680)

    def string(index):
        offset, size = struct.unpack_from("<II", strings, index * 8)
        return strings[offset:offset + size].decode("ascii")

    header = struct.unpack_from("<14I", data)
    verify("Qt 枚举布局", list(header[8:10]), [72, 14])
    enums = {}
    for index in range(header[8]):
        name, _, _, count, offset = struct.unpack_from("<5I", data, (header[9] + index * 5) * 4)
        enums[string(name)] = [{"name": string(k), "id": value} for k, value in [struct.unpack_from("<II", data, (offset + n * 2) * 4) for n in range(count)]]
    actions = enums["eCameraAction"]
    verify("已核实拍摄 action", actions[1], {"name": "kTakePictureCameraAction", "id": 1})
    verify("action 枚举数", len(actions), 15)
    # 这是已查明名称范围，不作“所有接口都不可能”的证明。
    exports = [{"address": hex(a), "name": n} for a, n in pc.names.items() if "@" not in n and "flash" in n.lower()]
    routes = sorted(set(x.decode() for x in re.findall(rb"/v1/[a-zA-Z0-9_./<>-]+", binary.data)))

    result = {
        "source": "official-binaries-static", "firmware": "4.2.0", "hardwareRequests": 0,
        "phocusSha256": HASHES["phocus"], "pcVersion": "4.1.1", "pcSha256": PC_SHA256,
        "checks": checks, "passed": True,
        "getters": [{"id": i, "meaning": v[0], "case": hex(v[1]), "getter": hex(v[3]), "wire": v[4]} for i, v in definitions.items()],
        "actions": actions, "httpRouteLiterals": routes, "pcFlashNamedExports": exports,
        "scopeNote": "名称与枚举只限定本次核查范围；未见独立引闪或事件日志入口，不等于证明其他正常接口不存在。",
    }
    (ROOT / "research/debug-parameter-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        print("第一代 X2D 100C 官方 4.2.0 /bin/phocus；只读反汇编；SHA256=" + HASHES["phocus"])
        for address, size in [(0x9278c, 20), (0x92908, 32), (0x928e8, 16), (0x91cc8, 48), (0x93d04, 40),
                              (0x117c40, 96), (0x117970, 48), (0x1174f0, 48), (0x1440e0, 136),
                              (0x955d8, 36), (0x9573c, 40), (0x983cc, 76), (0x98b30, 192), (0xa46e4, 36)]:
            print("\nRANGE", hex(address))
            for ins in binary.cs.disasm(binary.read(address, size), address):
                comment = binary.names.get(ins.operands[0].imm, "") if ins.mnemonic in ("bl", "b") else ""
                print(f"{ins.address:08x}  {ins.mnemonic:8} {ins.op_str:36} {comment}")
    (ROOT / "research/x2d-4.2.0-debug-getters.asm.txt").write_text(out.getvalue(), encoding="utf-8")
    print(json.dumps({"passed": True, "checks": len(checks), "hardwareRequests": 0}, ensure_ascii=False))


if __name__ == "__main__":
    run()
