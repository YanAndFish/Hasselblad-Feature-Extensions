"""固定官方 1.25.0 的 sutest 单项 RAM 缓存查询证据；不访问硬件。"""
import hashlib
import json
from pathlib import Path

from binary import ArmElf, CACHE, ROOT
from audit_usb_diagnostic_path import INPUTS, Fx3Image, FX3_SHA
from suc_diagnostic_binary import SucImage, SUC_SHA
from sutest_ram_contract import COMMAND, UPSTREAM_SHA, build_query


def run():
    assert Path.cwd().resolve() == ROOT
    sources = {
        "sutest": (CACHE / "sutest-inputs/usr/bin/sutest-daemon", "382f6d2c41dd2dbe0425eff0e2906206cbc5f466d26c686f39e09832ebc23f2f"),
        "busctl": (CACHE / "sutest-inputs/usr/bin/busctl", "a41540a68611ad05d54a3ecd416370554af97f33d0bf9a26594d506618dcc90f"),
        "bridge": INPUTS["bridge"], "tunnel": INPUTS["tunnel"], "apps": INPUTS["apps"],
    }
    modules = {}
    for name, (path, digest) in sources.items():
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        modules[name] = ArmElf(data)
    modules["suc"], modules["fx3"] = SucImage(), Fx3Image()
    checks = []
    rows = [
        ("fx3", 0x4000540c, "cmp", "r3, #9"),
        ("fx3", 0x40005444, "bl", "#0x40007870"),
        ("suc", 0x800fd38, "ldrb", "r2, [r4, #3]"),
        ("suc", 0x800fd5c, "bl", "#0x801acd0"),
        ("suc", 0x800fde2, "bl", "#0x801acd0"),
        ("bridge", 0x2219c, "cmp", "r0, #0xa"),
        ("bridge", 0x22278, "b", "#0x22510"),
        ("bridge", 0x22544, "cmp", "r0, #0xa"),
        ("bridge", 0x22550, "bl", "#0x18ba0"),
        ("bridge", 0x22408, "bl", "#0x18bb8"),
        ("sutest", 0x1d260, "ldrb", "r2, [r1], #1"),
        ("sutest", 0x1d264, "bl", "#0x1ce0c"),
        ("sutest", 0x1bdb8, "mov", "r5, #0x34"),
        ("sutest", 0x1bed0, "str", "r5, [sp, #0x3f0]"),
        ("sutest", 0x1bee4, "str", "r1, [sp, #0x400]"),
        ("sutest", 0x3c12c, "bl", "#0x4b428"),
        ("sutest", 0x59b34, "bl", "#0x1ad20"),
        ("sutest", 0x59048, "cmp", "r5, #0"),
        ("sutest", 0x59090, "bl", "#0x6b474"),
        ("sutest", 0x2463c, "ldr", "r3, [r4, #0x10]"),
        ("sutest", 0x2464c, "str", "r3, [sp, #0xc]"),
        ("sutest", 0x24654, "bl", "#0x24760"),
        ("sutest", 0x24674, "bl", "#0x66e64"),
        ("sutest", 0x1d31c, "bl", "#0x1a90c"),
        ("fx3", 0x4000524c, "bl", "#0x400044a8"),
        ("busctl", 0xa724, "beq", "#0xbacc"),
        ("busctl", 0xa73c, "beq", "#0xbcb4"),
        ("busctl", 0xbb70, "bl", "#0x1a320"),
        ("busctl", 0x1a348, "orr", "r3, r3, #2"),
        ("busctl", 0xbbb0, "bic", "r3, r3, #4"),
        ("busctl", 0xc4dc, "ldrd", "r2, r3, [r3]"),
        ("busctl", 0xc4e8, "bl", "#0x16208"),
        ("busctl", 0xbd64, "bl", "#0x25f8c"),
        ("bridge", 0x58c20, "ldr", "r3, [r0, #0x140]"),
        ("bridge", 0x346b4, "str", "r3, [r4, #0x140]"),
    ]
    for module, address, mnemonic, operands in rows:
        item = modules[module].instructions(address, 4)[0]
        assert (item.mnemonic, item.op_str) == (mnemonic, operands), (module, hex(address), item.mnemonic, item.op_str)
        checks.append({"module": module, "address": hex(address), "bytes": item.bytes.hex(),
                       "mnemonic": mnemonic, "operands": operands})
    su, bu, tunnel = modules["sutest"], modules["busctl"], modules["tunnel"]
    # command 52 的构造函数工厂指针：相邻表项 stride 20，+16 为 invoker。
    assert (0x1bee0 + 8 + su.word(0x1bec8 + 8 + (su.word(0x1bec8) & 0xfff))) & 0xffffffff == 0x3c10c
    assert (0xc4d8 + 8 + bu.word(0xc4d4 + 8 + (bu.word(0xc4d4) & 0xfff))) & 0xffffffff == 0x52208
    messages = []
    for ident, name in ((9, "testd_tx_event"), (10, "testd_rx_event")):
        assert tunnel.read(tunnel.word(0x4ae16034 + 4 * ident), len(name) + 1) == name.encode() + b"\0"
        sizes = [tunnel.word(0x4adf8234 + 4 * ident), modules["suc"].word(0x802c03c + 4 * ident),
                 modules["fx3"].word(0x40018160 + 4 * ident)]
        assert sizes == [256, 256, 256]
        messages.append({"id": ident, "name": name, "bodyBytes": 256})
    assert len(build_query(0x71408abc)) == 512
    report = {
        "firmware": "官方 X1D-50c 1.25.0；实机固件版本未知", "kind": "static-sutest-ram-cache-query",
        "cameraCommandsSent": 0, "firmwareExecuted": False, "command": COMMAND,
        "sourcesSha256": {**{name: digest for name, (_, digest) in sources.items()}, "suc": SUC_SHA, "fx3": FX3_SHA},
        "upstreamRevision": "87b39648a9625a0b74279b86a44f778e22e9c2c1", "upstreamToolSha256": UPSTREAM_SHA,
        "checks": checks, "messages": messages,
        "semantics": "仅 Properties.Get 读取 Linux FarmHandler RAM 缓存；0 是构造默认值之一，未证明新鲜度",
        "rejectedEarlierCandidate": "systemd 225 get-property 未应用 auto-start 和 timeout 参数，不执行",
        "hostBounds": {"writeCalls": 1, "writeTimeoutMs": 2000, "readCallsAtMost": 2, "readBudgetMs": 6000},
        "limits": ["指令与来源核对配合人工调用链审阅；不证明当前机版本或板间健康",
                   "sutest 原厂激活可能加载 i2c-dev 模块并启动服务；busctl 注册临时系统总线客户端",
                   "2 秒限制方法调用，不能声称限制全部进程生命周期；主机超时不取消机内工作"],
    }
    destination = ROOT / "x1d/research/validation/sutest-ram-cache-static.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"通过：{len(checks)} 个固定指令核对，三份消息表，工厂指针，199 字节命令；相机请求 0。")


if __name__ == "__main__":
    run()
