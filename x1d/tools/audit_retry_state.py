"""核对 1.25.0 检查更新、节点重试和日志保存的静态证据；没有设备入口。"""
from __future__ import annotations
import hashlib
import json
from binary import ArmElf, BASELINE, ROOT, qml_files


def run():
    hashes = {
        "usr/bin/victory-gui": "d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b",
        "usr/bin/upgrade-daemon": "aa62f9e03208d2306c0890fc9d5d9c522569359922a659060da270da381c8d0c",
        "usr/lib/libappscommon.so.1.0.0": "2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263",
    }
    modules = {p: ArmElf.load(p) for p in hashes}
    for path, expected in hashes.items():
        assert hashlib.sha256(modules[path].data).hexdigest() == expected, path
    gui, upgrade, apps = [modules[p] for p in hashes]
    qml = qml_files(gui)
    qml_checks = {
        "/settings/scripts/MenuItemSpecificationsWedge.js": ["name: \"fwUpdateRetry\"", '"Firmware Update Retry"', 'name: "saveLogData"'],
        "/settings/SettingsGeneric.qml": ['case "fwUpdateRetry":', "onRightSelected: Upgrader.upgradeNodes()", "System.collectLogs()", "System.collecting_logs !== 0"],
        "/components/popups/UpgradeCheck.qml": ["Upgrader.startSearch()", 'listView.count > 0 ? "list" : "no_upgrades"', 'qsTr("No updates available")', "Upgrader.startUpgrade(listView.model[confirmDialog.currentUpgradeIndex].uuid)", "when: suc.usb_vbus_present"],
        "/components/popups/PopoverError.qml": ["onClicked: Upgrader.upgradeNodes()", "System.collectLogs()"],
        "/common/TouchWindow.qml": ['state: Upgrader.isProcessing ? "updating"', '"showPercentage": Upgrader.upgradeType === Upgrader.TypeCameraFirmware'],
    }
    qml_evidence = []
    for path, fragments in qml_checks.items():
        for fragment in fragments:
            lines = [n for n, line in enumerate(qml[path].splitlines(), 1) if fragment in line]
            assert lines, (path, fragment)
            qml_evidence.append({"resource": path, "fragment": fragment, "lines": lines})
    calls = []
    for module, name, at, target in [
        (gui, "gui", 0x891FC, 0x53854),
        (gui, "gui", 0x53914, 0x25254),
        (apps, "apps", 0x4AD9A810, 0x4AD50DF0),
        (apps, "apps", 0x4AD9A840, 0x4AD510CC),
        (upgrade, "upgrade", 0x543E0, 0x1CC3C),
        (upgrade, "upgrade", 0x3C200, 0x35848),
        (upgrade, "upgrade", 0x3C2F0, 0x3B988),
        (upgrade, "upgrade", 0x3BB40, 0x35848),
        (upgrade, "upgrade", 0x3BE80, 0x40BEC),
        (upgrade, "upgrade", 0x39508, 0x197A8),
        (upgrade, "upgrade", 0x3702C, 0x1A030),
        (gui, "gui", 0x55420, 0x88EBC),
    ]:
        actual = list(module.direct_calls(at, 4))
        assert len(actual) == 1 and actual[0][1] == target, hex(at)
        calls.append({"module": name, "address": hex(at), "target": hex(target), "symbol": actual[0][2]})
    assert upgrade.word(0x1CC40) == 0xEA007D31  # DBus::UpdateNodes -> Engine
    assert apps.read(0x4AD9A800 + apps.word(0x4AD9A8F8), 11) == b"UpdateNodes"
    # 原对象关联：Engine + 0x3c 的 PreUpgrade，done 接节点重试完成槽。
    words = {
        0x38D40: 0xE288303C, 0x38D48: 0xE58D3030,
        0x39B60: 0x748, 0x731D4: 0x55738,
        0x39B7C: 0x5A4, 0x73030: 0x36DB8,
        0x394C4: 0xE59D7030, 0x39500: 0xE1A01007,
        0x3C1FC: 0xE5851064, 0x3BB50: 0xE5943064,
        0x3BB6C: 0xE3530001, 0x3BE7C: 0xE284003C,
    }
    for at, value in words.items():
        assert upgrade.word(at) == value, hex(at)
    arguments = []
    for pool, base, size, expected in [
        (0x37260, 0x36E7C, 2, "-t"), (0x37264, 0x36EA8, 7, "upgrade"),
        (0x37268, 0x36ECC, 25, "/usr/bin/program_nodes.sh"),
        (0x3726C, 0x36EF0, 1, "/"), (0x37270, 0x36F10, 1, "/"),
        (0x37274, 0x36F30, 1, "1"), (0x37278, 0x37018, 11, "systemd-cat")]:
        value = upgrade.read(base + upgrade.word(pool), size).decode("ascii")
        assert value == expected, (hex(pool), repr(value))
        arguments.append(value.rstrip("\0"))
    statuses = apps.meta_object("_ZN8CUpgrade16staticMetaObjectE")["enums"][0]["values"]
    processing = []
    for status in range(1, 22):
        address = 0x537F0 + (status - 1) * 4
        instruction = next(gui.decoder.disasm(gui.read(address, 4), address))
        assert instruction.mnemonic == "b"
        destination = int(instruction.op_str.removeprefix("#"), 16)
        assert destination in (0x53844, 0x5384C)
        if destination == 0x5384C:
            processing.append(next(s for s in statuses if s["value"] == status))
    assert [s["value"] for s in processing] == [1, 2, 3, 20, 21]
    script_path = "usr/bin/program_nodes.sh"
    script = (BASELINE / script_path).read_text()
    baseline = json.loads((ROOT / "x1d/research/baseline-manifest.json").read_text(encoding="utf-8"))
    expected = next(x["sha256"] for x in baseline["files"] if x["path"] == script_path)
    assert hashlib.sha256((BASELINE / script_path).read_bytes()).hexdigest() == expected
    script_fragments = ["FW_DIR=/lib/firmware/hbl", "BLOB_PREFIX=$2", "CONTINUE_ON_FAIL=$3", "update_farm ${TOOL_PREFIX} ${BLOB_PREFIX}", "update_fx3 ${TOOL_PREFIX} ${BLOB_PREFIX}", "update_suc ${TOOL_PREFIX} ${BLOB_PREFIX}", "journalctl -b -o short-precise > ${LOG_DIR}/upgrade.log"]
    script_evidence = []
    for fragment in script_fragments:
        lines = [n for n, line in enumerate(script.splitlines(), 1) if fragment in line]
        assert lines, fragment
        script_evidence.append({"fragment": fragment, "lines": lines})
    report = {"kind": "static-call-and-menu-audit", "firmware": "X1D-50c 1.25.0",
              "cameraFirmwareKnown": False, "cameraCommandsSent": 0,
              "inputHashes": hashes, "qml": qml_evidence, "calls": calls,
              "processingStates": processing, "retryProcessArguments": arguments,
              "nodesScriptSha256": expected, "nodesScript": script_evidence,
              "conclusion": "节点重试具备从当前系统固件文件重写控制器的路径，无需SD上的CIM；未证明本次实机执行到哪一阶段。",
              "limits": ["静态读取，不执行原升级程序或控制器程序", "Windows枚举不是控制器健康检查", "未取得相机日志、当前画面或实机固件版本"]}
    target = ROOT / "x1d/research/validation/firmware-retry-static.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("检查更新/节点重试/日志菜单的固定证据通过；无相机命令，未判定实际故障原因。")


if __name__ == "__main__": run()
