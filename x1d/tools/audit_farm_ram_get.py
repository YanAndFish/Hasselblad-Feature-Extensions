"""X1D 1.25.0 单项 FARM RAM 模式 getter 的离线证据核对。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from binary import ArmElf, ROOT
from audit_usb_diagnostic_path import Fx3Image, INPUTS, FX3_PATH, FX3_SHA
from farm_diagnostic_binary import FarmApplication, HASHES
from suc_diagnostic_binary import SucImage, SUC_PATH, SUC_SHA


def run():
    assert Path.cwd().resolve() == ROOT.resolve()
    farm, suc, fx = FarmApplication(), SucImage(), Fx3Image()
    path, expected = INPUTS["tunnel"]
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected
    tunnel = ArmElf(data)
    modules = {"farm": farm, "suc": suc, "fx3": fx}
    checks = []

    def check(module, address, mnemonic, operands):
        item = modules[module].instructions(address, 4)[0]
        assert (item.mnemonic, item.op_str) == (mnemonic, operands), (module, hex(address), item.op_str)
        checks.append({"module": module, "address": hex(address), "bytes": bytes(item.bytes).hex(),
                       "mnemonic": mnemonic, "operands": operands})

    for module, address, target in [
        ("fx3", 0x40005420, 0x40005828), ("fx3", 0x40005434, 0x40005378),
        ("fx3", 0x40005444, 0x40007870), ("fx3", 0x40005898, 0x40007530),
        ("fx3", 0x400078e8, 0x40007fbc), ("fx3", 0x4000524c, 0x400044a8),
        ("suc", 0x800fa12, 0x801aae4), ("suc", 0x800fa50, 0x801aae4),
        ("suc", 0x800f7aa, 0x800f644), ("suc", 0x800fd34, 0x800f7bc),
        ("suc", 0x800fd82, 0x800f53c), ("suc", 0x800fd8a, 0x800fbbc),
        ("suc", 0x800fd96, 0x801acd0), ("suc", 0x800fde2, 0x801acd0),
        ("suc", 0x800fc62, 0x8002480), ("suc", 0x800fc76, 0x8012e38),
        ("suc", 0x800f92a, 0x8012e04), ("suc", 0x801ad16, 0x801b080),
        ("farm", 0x1e9f28, 0x1e80d0), ("farm", 0x1e766c, 0x1e7400),
        ("farm", 0x1e768c, 0x1e71dc), ("farm", 0x1e263c, 0x1e7fac),
        ("farm", 0x1e26c0, 0x186500), ("farm", 0x1e2284, 0x1e1c0c),
        ("farm", 0x1e1c2c, 0x1e0a50), ("farm", 0x1e1c30, 0x1e2c0c),
        ("farm", 0x1e1c54, 0x1e80d0), ("farm", 0x1e7780, 0x1ea49c),
        ("farm", 0x1ea508, 0x186500), ("farm", 0x1e9c50, 0x186b70),
        ("farm", 0x1e9e44, 0x1e8aa0), ("farm", 0x1e9e68, 0x23cda0),
        ("farm", 0x23ce74, 0x239c04),
    ]:
        check(module, address, "bl", f"#{target:#x}")
    for row in [
        ("fx3", 0x40005408, "ldrb", "r3, [r4, #3]"),
        ("fx3", 0x4000540c, "cmp", "r3, #9"),
        ("fx3", 0x400078ac, "cmp", "r4, #2"),
        ("fx3", 0x4000523c, "cmp", "r3, #8"),
        ("suc", 0x800fd38, "ldrb", "r2, [r4, #3]"),
        ("suc", 0x800fd88, "movs", "r0, #2"),
        ("suc", 0x800fc5e, "movs", "r1, #2"),
        ("suc", 0x800fc72, "movw", "r0, #0x30a"),
        ("suc", 0x8012e62, "str", "r3, [r2, #0x14]"),
        ("suc", 0x8012e2e, "str", "r3, [r2, #0x10]"),
        ("suc", 0x801acf4, "cmp", "r3, #2"),
        ("farm", 0x1e2140, "movw", "r2, #0x22d"),
        ("farm", 0x1e2148, "beq", "#0x1e227c"),
        ("farm", 0x1e2634, "movw", "r1, #0x2678"),
        ("farm", 0x1e2638, "movt", "r1, #0x1e"),
        ("farm", 0x1e7274, "blx", "r3"),
        ("farm", 0x1e1c28, "movw", "r2, #0x22e"),
        ("farm", 0x1e1c38, "cmp", "r3, #1"),
        ("farm", 0x1e1c3c, "moveq", "r3, #1"),
        ("farm", 0x1e1c40, "movne", "r3, #0"),
        ("farm", 0x1e1c48, "strb", "r3, [fp, #-8]"),
        ("farm", 0x1e0ab4, "mov", "r2, #1"),
        ("farm", 0x1e0ab8, "strb", "r2, [r3, #2]"),
        ("farm", 0x1e0ac0, "ldrb", "r2, [r3, #2]"),
        ("farm", 0x1e0ac8, "strb", "r2, [r3, #3]"),
        ("farm", 0x1e2c14, "movw", "r3, #0x3918"),
        ("farm", 0x1e2c18, "movt", "r3, #0x6c"),
        ("farm", 0x1e2c1c, "ldrb", "r3, [r3]"),
        ("farm", 0x1e2c3c, "mov", "r3, #0"),
        ("farm", 0x1e2c44, "mov", "r3, #1"),
        ("farm", 0x1e2c4c, "mov", "r3, #2"),
        ("farm", 0x1e2c54, "mov", "r3, #0"),
        ("farm", 0x1e9e18, "movw", "r3, #0xac90"),
        ("farm", 0x1e9e30, "bne", "#0x1e9d1c"),
        ("farm", 0x23ce10, "cmp", "r3, #2"),
    ]:
        check(*row)

    signals = []
    for ident, name in ((557, "farm_get_ram_only_mode_req"), (558, "farm_get_ram_only_mode_resp")):
        addr = tunnel.word(0x4ae16034 + ident * 4)
        assert tunnel.read(addr, len(name) + 1) == name.encode() + b"\0"
        sizes = [tunnel.word(0x4adf8234 + ident * 4), fx.word(0x40018160 + ident * 4),
                 suc.word(0x802c03c + ident * 4), farm.word(0x29d938 + ident * 4)]
        assert sizes == [1, 1, 1, 1]
        signals.append({"id": ident, "name": name, "bodyBytesInAllFourTables": 1})
    for ident, name in ((1, "farm"), (3, "suc"), (8, "usbhost"), (9, "fx3")):
        addr = tunnel.word(0x4ae1600c + ident * 4)
        assert tunnel.read(addr, len(name) + 1) == name.encode() + b"\0"
    registered = struct.unpack("<17H", farm.read(0x27c500, 34))
    assert registered[12] == 557 and registered[13] == 559
    assert struct.unpack("<4I", farm.read(0x1e2c2c, 16)) == (0x1e2c3c, 0x1e2c4c, 0x1e2c44, 0x1e2c4c)
    assert farm.word(0x250d1c + 6 * 4) == 0x1e9ef4
    assert fx.word(0x400180f0 + 7 * 4) == 0x40005230
    assert suc.word(0x8026b90 + 36 + 7 * 4) == 0x800f7a1
    assert suc.word(0x8026b90 + 72 + 7 * 4) == 0x800f7a1
    assert suc.read(0x800fd44, 9) == bytes.fromhex("1a 05 5c 05 05 6e 6e 48 48")
    assert suc.word(0x800fc84) == 0x800f925
    addr = suc.word(0x800fc88)
    assert suc.read(addr, 14) == b"IMX IRQ Timer\0"
    source_name = b"../src/msgrouter/suc_agent.c\0"
    assert farm.read(0x250b6c, len(source_name)) == source_name
    report = {
        "firmware": "官方 X1D-50c 1.25.0；不代表实机版本",
        "kind": "static-farm-ram-get-roundtrip", "cameraCommandsSent": 0, "firmwareExecuted": False,
        "sources": {"farmBootPair": HASHES, "farmApplicationSha256": farm.sha256,
                    SUC_PATH: SUC_SHA, FX3_PATH: FX3_SHA, "libAppsMessaging.so": expected},
        "checks": checks, "messages": signals,
        "requestSemanticHex": "2d 02 08 01 00", "replyHeaderHex": "2e 02 01 08",
        "route": ["usbhost=8", "FX3 正常控制 OUT 0x02", "SUC 路由", "FARM=1 getter",
                  "FARM suc_agent", "SUC dst=8", "FX3 正常控制 IN 0x82"],
        "replyInterpretation": {"1": "FARM getter 返回 RAM 模式已生效", "0": "未报告已生效；包括原厂中间状态，不表示恢复正常"},
        "sideEffects": ["主机描述符/策略初始化及原有 USB、UART、RTOS 队列通信",
                        "SUC 转发到 FARM 时重置已有 IMX IRQ Timer，并拉低该通信输出；计时回调拉高",
                        "原有日志与错误记录可能发生；没有核对实际落盘",
                        "FARM 回复线程可能等待既有 SUC 连接就绪；主机超时不取消机内排队"],
        "limits": ["静态路由不证明当前故障机三控制器均运行或固件版本匹配",
                   "本读取不切换 RAM 模式、不清除错误、不恢复设置、不启动 Phocus 会话",
                   "没有错误根因、照片、存储枚举或恢复成功结论；设置消息 559 不纳入白名单"]}
    target = ROOT / "x1d/research/validation/farm-ram-get-static.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FARM RAM getter 往返静态核对通过：{len(checks)} 条指令、4 份消息大小表、注册/回调/路由/返回值常量；相机请求 0。")


if __name__ == "__main__":
    run()
