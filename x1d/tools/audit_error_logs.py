"""核对错误 1000 与错误页日志导出的固定静态路径；不执行相机代码。"""
from __future__ import annotations
import hashlib
import json
from binary import ArmElf, CACHE, ROOT, qml_files


def run():
    input_manifest = json.loads((ROOT / "x1d/research/error-input-manifest.json").read_text(encoding="utf-8"))
    for item in input_manifest["files"]:
        assert hashlib.sha256((CACHE / "error-inputs" / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    sm = ArmElf((CACHE / "error-inputs/usr/bin/system-manager").read_bytes())
    gui = ArmElf.load("usr/bin/victory-gui")
    apps = ArmElf.load("usr/lib/libappscommon.so.1.0.0")
    assert hashlib.sha256(gui.data).hexdigest() == "d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b"
    assert hashlib.sha256(apps.data).hexdigest() == "2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263"
    modules = {"system-manager": sm, "victory-gui": gui, "libappscommon": apps}
    qml = qml_files(gui)
    popup = qml["/components/popups/PopoverError.qml"]
    button = popup[popup.index("id: saveLogsButton"):popup.index("\n        Item {", popup.index("id: saveLogsButton"))]
    assert "System.collectLogs()" in button and "System.collecting_logs !== 0" in button
    assert "Upgrader" not in button and "errorCode" not in button
    evidence = []
    for module, address, target in [
        ("victory-gui", 0x8E858, 0x5A500), ("victory-gui", 0x5A500, 0x25AF4),
        ("libappscommon", 0x4AD60988, 0x4AD50DF0),
        ("libappscommon", 0x4AD6099C, 0x4AD510CC),
        ("system-manager", 0x37354, 0x1B6FC),
        ("system-manager", 0x1B71C, 0x215C4),
        ("system-manager", 0x21638, 0x32B94),
        ("system-manager", 0x32BE8, 0x199A8),
        ("system-manager", 0x3450C, 0x338F0),
        ("system-manager", 0x3400C, 0x33130),
        ("system-manager", 0x33210, 0x19A8C),
        ("system-manager", 0x338C4, 0x332B8),
        ("system-manager", 0x33348, 0x199FC),
        ("system-manager", 0x3344C, 0x19474),
        ("system-manager", 0x33030, 0x32BFC),
        ("system-manager", 0x32CA8, 0x3A134),
        ("system-manager", 0x32D34, 0x3A178),
        ("system-manager", 0x22CC4, 0x215AC),
        ("system-manager", 0x22E74, 0x215AC),
        ("system-manager", 0x22DD0, 0x19FC0),
        ("system-manager", 0x23014, 0x19FC0),
        ("system-manager", 0x38494, 0x1F5C4),
        ("system-manager", 0x1F684, 0x19B94),
        ("system-manager", 0x1EAF8, 0x19A68),
        ("system-manager", 0x1EB0C, 0x37D5C),
    ]:
        elf = modules[module]
        instruction = elf.instructions(address, 4)[0]
        assert instruction.mnemonic in ("b", "bl") and int(instruction.op_str[1:], 0) == target, hex(address)
        evidence.append({"module": module, "address": hex(address), "target": hex(target), "symbol": elf.name(target)})
    assert gui.name(0x25AF4) == "_ZN18SystemManagerProxy11collectLogsEv"
    assert sm.word(0x1F668) == 0xE3A01FFA
    enums = apps.meta_object("_ZN6Errors16staticMetaObjectE")["enums"][0]["values"]
    assert {x["name"] for x in enums if x["value"] == 1000} == {"ErrorGeneral", "ErrorFirstNonAckable"}
    strings = []
    for at, expected in [
        (0x4AD60978 + apps.word(0x4AD60A18), "collectLogs"),
        (0x33328 + sm.word(0x33718), "WriteFile"),
        (0x331FC + sm.word(0x332B4), "hbl-collect-logs.sh"),
        (0x33960 + sm.word(0x34318) + 0x34, "current_volume_image_raw"),
        (0x33B64 + sm.word(0x34320), "%1/%2-log.hbl"),
        (0x33B70 + sm.word(0x34324), "yyyyMMdd-hhmmsszzz"),
        (0x22CFC + sm.word(0x22E58), "errorCode"),
        (0x22F4C + sm.word(0x230AC), "fileName"),
        (0x3C3B8, "/tmp/logs.zip"),
    ]:
        elf = apps if at > 0x40000000 else sm
        assert elf.read(at, len(expected) + 1) == expected.encode() + b"\0", hex(at)
        strings.append({"address": hex(at), "value": expected})
    scripts = {}
    for name in ("hbl-collect-logs.sh", "hbl-save-error-logs.sh"):
        data = (CACHE / "error-inputs/usr/bin" / name).read_bytes()
        scripts[name] = {"sha256": hashlib.sha256(data).hexdigest(), "lines": len(data.splitlines())}
    collect = (CACHE / "error-inputs/usr/bin/hbl-collect-logs.sh").read_text()
    assert 'zip -e --password $1 $2 ${FILENAME}' in collect
    assert 'MULTIPLE=512' in collect and 'configstore.sql' in collect
    assert collect.count("org.freedesktop.DBus.Properties.GetAll") == 13
    report = {
        "kind": "static-error-and-save-logs-audit", "firmware": "X1D-50c 1.25.0",
        "inputManifest": "x1d/research/error-input-manifest.json",
        "cameraCommandsSent": 0, "firmwareExecuted": False, "realLogRead": False,
        "calls": evidence, "safeStrings": strings, "scripts": scripts,
        "result": "错误页日志请求独立于节点重试；错误状态没有额外拒绝条件，但依赖存储服务及当前RAW目标卷写入。",
        "filenamePattern": "yyyyMMdd-hhmmsszzz-log.hbl", "destination": "当前RAW保存目标卷根目录",
        "format": "密码保护ZIP包装，内含hbl-logs.zip，末尾补零至512字节整数倍；不保存口令材料。",
        "completion": "成功与失败均清collecting_logs；错误页不接收结果码，所以忙框关闭不能单独证明已写卡。",
        "limitations": ["当前实机版本与代码一致性未知", "无固定最小空闲容量检查，日志大小随历史记录变化",
                        "没有实机导出或当前日志文件", "没有承诺日志保护层的正式读取方法已打通",
                        "未逐个穷举所有daemon属性getter副作用；实际包含状态查询和FARM卡写入"]}
    target = ROOT / "x1d/research/validation/error-save-logs-static.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"错误1000/保存日志静态核查通过：{len(evidence)}条调用、{len(strings)}项非敏感字符串；未访问相机。")


if __name__ == "__main__":
    run()
