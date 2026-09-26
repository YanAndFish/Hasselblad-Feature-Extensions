"""固定 X1D 1.25.0 的正常 USB 诊断链静态审计；不执行固件或访问设备。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct

from binary import ArmElf, BASELINE, CACHE, ROOT, Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

FX3_PATH = "lib/firmware/hbl/fx3/fx3_wedge-v0.0-14268-e0ef6ae.bin"
FX3_SHA = "19236566d65ad6881fda0ee554944374188217fbcb514f0eb8c0cae1416b5a05"
INPUTS = {
    "phocus": (BASELINE / "usr/bin/phocus-daemon", "5c17bad12039c649e8b5c8ad1070763d1fc90d40f25d21f8a45bf506041db378"),
    "bridge": (CACHE / "usb-diagnostic-inputs/usr/bin/msg2dbus", "988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1"),
    "tunnel": (CACHE / "usb-diagnostic-inputs/usr/lib/libAppsMessaging.so", "8a6a45428fcaa17e570e0aad217ee7220716501bcaf4cddef106af5137d6f7d1"),
    "apps": (BASELINE / "usr/lib/libappscommon.so.1.0.0", "2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263"),
}


class Fx3Image:
    def __init__(self):
        # 只复用已经审核的固定 CIM 读取与 CY 分段校验；不运行独立报告或 FARM 重组。
        source = ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py"
        spec = importlib.util.spec_from_file_location("x1d_fx3_static_input", source)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        reader.WANTED = {FX3_PATH}
        self.data = reader.inputs()[FX3_PATH]
        assert hashlib.sha256(self.data).hexdigest() == FX3_SHA
        self.sections, self.entry = reader.fx3_image(self.data)
        self.decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)

    def read(self, address, size):
        for _, start, data in self.sections:
            if start <= address and address + size <= start + len(data):
                return data[address-start:address-start+size]
        raise ValueError("固定 FX3 输入的地址越界")

    def word(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def instructions(self, address, size):
        return list(self.decoder.disasm(self.read(address, size), address))


def run():
    assert Path.cwd().resolve() == ROOT.resolve(), "必须在当前 Hasselblad local 工作区运行"
    modules, files = {}, []
    for name, (path, expected) in INPUTS.items():
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name
        modules[name] = ArmElf(data)
        files.append({"name": name, "path": path.relative_to(ROOT).as_posix(), "sha256": expected})
    modules["fx3"] = fx = Fx3Image()
    files.append({"name": "fx3", "pathInCimRootfs": FX3_PATH, "sha256": FX3_SHA, "savedOrExecuted": False})
    evidence = []

    def check(module, address, mnemonic, operands):
        item = modules[module].instructions(address, 4)[0]
        assert (item.mnemonic, item.op_str) == (mnemonic, operands), (module, hex(address))
        evidence.append({"module": module, "address": hex(address), "bytes": bytes(item.bytes).hex(),
                         "mnemonic": mnemonic, "operands": operands})

    for module, address, target in [
        ("fx3", 0x4000431c, 0x40008b10), ("fx3", 0x40004358, 0x40008b10),
        ("fx3", 0x40003f90, 0x4000517c), ("fx3", 0x40005190, 0x4001c758),
        ("fx3", 0x40005418, 0x400051c0), ("fx3", 0x40005444, 0x40007870),
        ("fx3", 0x40005558, 0x40004ffc), ("fx3", 0x4000557c, 0x40005290),
        ("fx3", 0x400055ec, 0x40005230), ("fx3", 0x4000524c, 0x400044a8),
        ("fx3", 0x4000450c, 0x40003300), ("fx3", 0x4000452c, 0x4000a188),
        ("fx3", 0x40005024, 0x40010a54), ("fx3", 0x4000535c, 0x40005230),
        ("bridge", 0x225cc, 0x191e8), ("bridge", 0x22408, 0x18bb8),
        ("bridge", 0x22664, 0x2177c), ("bridge", 0x56ea8, 0x279c4),
        ("bridge", 0x279e4, 0x21a9c), ("bridge", 0x27a0c, 0x4da04),
        ("phocus", 0x47eec, 0x50e34), ("phocus", 0x47ef4, 0x51030),
        ("phocus", 0x484c0, 0x55964), ("phocus", 0x46204, 0x18654),
        ("phocus", 0x4620c, 0x18360), ("phocus", 0x46214, 0x17c4c),
        ("phocus", 0x66b50, 0x17eb0), ("phocus", 0x66b98, 0x787e8),
    ]:
        check(module, address, "bl", f"#{target:#x}")
    for module, address, mnemonic, operands in [
        ("fx3", 0x40003f68, "cmp", "r1, #8"),
        ("fx3", 0x40005408, "ldrb", "r3, [r4, #3]"),
        ("fx3", 0x4000540c, "cmp", "r3, #9"),
        ("fx3", 0x400054f8, "beq", "#0x4000553c"),
        ("fx3", 0x4000553c, "ldrb", "r3, [r0, #2]"),
        ("fx3", 0x40005544, "strb", "r3, [sp, #0xf]"),
        ("fx3", 0x4000554c, "strb", "r2, [sp, #0xe]"),
        ("fx3", 0x40005550, "strh", "r3, [r4, #-0x84]!"),
        ("fx3", 0x40004ffc, "mov", "r3, #0"),
        ("fx3", 0x40005014, "mov", "r3, #1"),
        ("fx3", 0x40005028, "cmp", "r0, #3"),
        ("fx3", 0x40005030, "orreq", "r3, r3, #2"),
        ("fx3", 0x40010a58, "ldrb", "r0, [r3, #9]"),
        ("fx3", 0x400052e8, "mov", "r3, #9"),
        ("fx3", 0x400052f0, "mov", "r3, #5"),
        ("fx3", 0x400040d4, "mov", "r2, #0x40"),
        ("fx3", 0x400040e4, "mov", "r2, #0x200"),
        ("fx3", 0x40004104, "mov", "r2, #0x400"),
        ("fx3", 0x40004504, "ldrh", "r2, [r4]"),
        ("fx3", 0x40004520, "ldrh", "r1, [r4]"),
        ("bridge", 0x219d0, "ldrh", "r0, [r0]"),
        ("bridge", 0x21a80, "ldrb", "r0, [r0, #2]"),
        ("bridge", 0x21a54, "ldrb", "r0, [r0, #3]"),
        ("bridge", 0x279e0, "movw", "r1, #0x478"),
        ("bridge", 0x279ec, "movw", "r3, #0x1388"),
        ("phocus", 0x47208, "b", "#0x18114"),
        ("phocus", 0x47f0c, "b", "#0x4847c"),
        ("phocus", 0x55a40, "sub", "r3, r4, #2"),
        ("phocus", 0x55a54, "cmp", "r3, #0x47"),
        ("phocus", 0x66b94, "strb", "r1, [r0, #0x471]"),
    ]:
        check(module, address, mnemonic, operands)

    constants = {
        0x4000443c: 0x40003f68, 0x40004474: 0x402,
        0x40004480: 0x3f01, 0x40004484: 0x302,
        0x40004488: 0x400359c4, 0x40004548: 0x400359c4,
        0x40004418: 0x40032948, 0x40004554: 0x40032948,
        0x40005668: 0x471, 0x4000567c: 0x472, 0x40005374: 0x47a,
        0x400053dc: 0x40018160,
    }
    for address, value in constants.items():
        assert fx.word(address) == value, hex(address)

    tunnel = modules["tunnel"]
    signals = []
    for ident, name, size in [
        (3, "hostd_tx_event", 256), (4, "hostd_rx_event", 256),
        (908, "farm_report_error_event", 3), (909, "suc_report_error_event", 3),
        (1137, "usbif_get_usb_linkstatus_req", 1), (1138, "usbif_get_usb_linkstatus_resp", 4),
        (1144, "suc_module_program_GetCbUpgradeStatus_req", 1),
        (1145, "suc_module_program_GetCbUpgradeStatus_resp", 1),
        (1146, "usbif_trace_event", 266),
    ]:
        at = tunnel.word(0x4ae16034 + ident * 4)
        assert tunnel.read(at, len(name) + 1) == name.encode() + b"\0"
        assert tunnel.word(0x4adf8234 + ident * 4) == size
        assert fx.word(0x40018160 + ident * 4) == size
        signals.append({"id": ident, "name": name, "bodyBytes": size,
                        "scope": "机内消息标识；只有 FX3 链路状态项进入离线读取白名单"})
    for ident, name in ((3, "suc"), (5, "iMX"), (8, "usbhost"), (9, "fx3")):
        at = tunnel.word(0x4ae1600c + ident * 4)
        assert tunnel.read(at, len(name) + 1) == name.encode() + b"\0"
    meta = modules["bridge"].meta_object("_ZN10SucHandler16staticMetaObjectE")
    assert meta["methods"][22]["name"] == "module_program_GetCbUpgradeStatus"
    assert modules["bridge"].name(0x191e8) == "_ZN3Bus13phocusServiceEv"
    assert modules["phocus"].name(0x18114) == "_ZN21apps_messaging_tunnel13receive_asyncEPh"
    assert modules["phocus"].name(0x17eb0).startswith("_ZN18SystemManagerProxy15setTetheredMode")
    assert modules["phocus"].read(0x48a38 + 8 + modules["phocus"].word(0x48e78), 29) == b"Not implemented (deprecated?)"

    configs = []
    for address, total, packet_size in ((0x40017ce0, 46, 64), (0x40030540, 46, 512), (0x400304e0, 70, 1024)):
        data = fx.read(address, total)
        assert data[:2] == b"\x09\x02" and struct.unpack_from("<H", data, 2)[0] == total
        pos, endpoints = 0, []
        while pos < total:
            length, kind = data[pos:pos+2]
            assert length >= 2 and pos + length <= total
            if kind == 5:
                endpoint, attributes, maximum = struct.unpack_from("<BBH", data, pos + 2)
                assert attributes == 2 and maximum == packet_size
                endpoints.append(endpoint)
            pos += length
        assert sorted(endpoints) == [1, 2, 0x81, 0x82]
        configs.append({"address": hex(address), "maximumPacketBytes": packet_size, "endpoints": endpoints})
    services = {}
    for name, expected in (("msg2dbus-suc", "/dev/ttymxc1 -b 460800 --role suc"),
                           ("msg2dbus-farm", "/dev/ttymxc2 -b 921600 --role farm")):
        path = BASELINE / f"lib/systemd/system/{name}.service"
        data = path.read_bytes()
        assert expected in data.decode()
        services[name] = {"sha256": hashlib.sha256(data).hexdigest(), "uartArguments": expected}
    report = {
        "firmware": "X1D-50c 1.25.0", "kind": "static-normal-usb-diagnostic-path",
        "files": files, "cameraCommandsSent": 0, "firmwareExecuted": False,
        "checks": evidence, "fixedFx3Words": {hex(k): hex(v) for k, v in constants.items()},
        "usbConfigurations": configs, "signals": signals, "services": services,
        "statusRead": {"controlOut": "0x02", "controlIn": "0x82", "packetSizes": [64, 512, 1024],
                       "semanticRequestHex": "71 04 08 09 00", "semanticReplyHeaderHex": "72 04 09 08",
                       "replyStatusOffset": 4, "knownStatusValues": [0, 1, 3],
                       "sideEffect": "原厂 handler 生成 usbif_trace_event，目标 iMX；并非完全不影响机内消息和日志。"},
        "limits": ["静态审计不读取实机版本或状态，实测由独立硬件记录说明", "本脚本只做离线核对，不调用独立单次 USB 工具",
                   "FX3 链路状态不诊断错误 1000，也不恢复相机", "GetCbUpgradeStatus 的外部目标处理与副作用尚未闭环",
                   "错误事件存在不等于已找到电脑端历史错误队列或日志下载入口",
                   "未证明 FX3 消息传输层到 SUC/FARM/Linux 的全部板级运行连接"]}
    target = ROOT / "x1d/research/validation/usb-diagnostic-path-static.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"正常 USB 诊断链静态核对通过：{len(files)} 个程序哈希、{len(evidence)} 条指令、{len(constants)} 个常量、{len(signals)} 个消息定义、3 份配置描述符；相机请求 0。")


if __name__ == "__main__":
    run()
