"""复核固定原包的恢复入口、错误页和服务证据；不访问相机或网络。"""
from __future__ import annotations
import hashlib
import json
from binary import ArmElf, BASELINE, CACHE, ROOT, qml_files
from recovery_binary import Uboot, fdt_nodes


def run():
    manifest = json.loads((ROOT / "x1d/research/baseline-manifest.json").read_text(encoding="utf-8"))
    extra = json.loads((ROOT / "x1d/research/error-input-manifest.json").read_text(encoding="utf-8"))
    hashes = {x["path"]: x["sha256"] for x in manifest["files"]}
    extra_hashes = {x["path"]: x["sha256"] for x in extra["files"]}
    checked = {}

    def read(path, supplemental=False):
        base, catalog = (CACHE / "error-inputs", extra_hashes) if supplemental else (BASELINE, hashes)
        data = (base / path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest == catalog[path], path
        checked[path] = digest
        return data

    gui = ArmElf(read("usr/bin/victory-gui"))
    cfg = ArmElf(read("usr/bin/configstore"))
    upgrade = ArmElf(read("usr/bin/upgrade-daemon"))
    mobile = ArmElf(read("usr/bin/phocus-mobile-server", True))
    qml = qml_files(gui)
    fragments = {
        "/settings/ConfirmDefaultSettings.qml": ["configstore.resetDefaultSettings(configstore.resetProfiles)"],
        "/settings/SettingsGeneric.qml": ['case "defaultSettings":', 'case "checkForUpdate":',
                                          'case "fwUpdateRetry":', "onRightSelected: Upgrader.upgradeNodes()"],
        "/components/popups/UpgradeCheck.qml": ["Upgrader.startSearch()", "Upgrader.startUpgrade(listView.model[confirmDialog.currentUpgradeIndex].uuid)",
                                                "when: suc.usb_vbus_present"],
        "/common/TouchWindow.qml": ["!ErrorControl.isAckable", 'name: "error"',
                                    "target: main_screen; show: false", "config: IdleDetect.FilterNone", "prodinfo.isNewH6DisplayQml()"],
        "/components/popups/PopoverError.qml": ["property bool showButtons: true", "System.collectLogs()",
                                                "System.collecting_logs !== 0", "visible: active", "active: false",
                                                "onClicked: Upgrader.upgradeNodes()"],
    }
    for name in ("MenuItemSpecifications.js", "MenuItemSpecificationsWedge.js", "MenuItemSpecificationsA6D.js", "MenuItemSpecificationsCFV.js"):
        fragments["/settings/scripts/" + name] = ['name: "defaultSettings"', 'name: "checkForUpdate"', 'name: "fwUpdateRetry"']
    qml_evidence = []
    for path, checks in fragments.items():
        for fragment in checks:
            lines = [i for i, line in enumerate(qml[path].splitlines(), 1) if fragment in line]
            assert lines, (path, fragment)
            qml_evidence.append({"resource": path, "fragment": fragment, "lines": lines})

    calls = []
    for module, label, at, target in [
        (gui, "gui", 0x83EEC, 0x850AC), (gui, "gui", 0x850B4, 0x4A13C),
        (gui, "gui", 0x4A194, 0x25824), (gui, "gui", 0x4A1E4, 0x25038),
        (cfg, "configstore", 0x2D624, 0x2D698), (cfg, "configstore", 0x2D6A0, 0x23560),
        (cfg, "configstore", 0x23564, 0x1D564), (cfg, "configstore", 0x1D6D8, 0x14CD4),
        (gui, "gui", 0x65E24, 0x25998), (mobile, "mobile", 0x20920, 0x19600),
        (upgrade, "upgrade", 0x3D2D0, 0x3B988),
    ]:
        instruction = module.instructions(at, 4)[0]
        assert instruction.mnemonic in ("b", "bl") and int(instruction.op_str[1:], 0) == target
        calls.append({"module": label, "address": hex(at), "target": hex(target), "symbol": module.name(target)})
    assert gui.meta_object("_ZN16ConfigStoreProxy16staticMetaObjectE")["methods"][286]["name"] == "resetDefaultSettings"
    assert cfg.meta_object("_ZN10ConfigCtrl16staticMetaObjectE")["methods"][6]["name"] == "resetDefaultSettings"
    assert gui.read(0x4A17C + gui.word(0x4A248), 21) == b"resetDefaultSettings\0"
    words = {0x652B8: 0xE584601C, 0x65DB4: 0xE594301C, 0x65DB8: 0xE3530000, 0x65DBC: 0x0A000015}
    for at, expected in words.items():
        assert gui.word(at) == expected, hex(at)
    assert upgrade.word(0x3D1BC) == 0xE3530003  # 继续升级需要 System.StateUpgrade

    units = {}
    unit_checks = {
        "sshd.socket": ["ListenStream=22", "Accept=yes"],
        "sshd@.service": ["Wants=sshdgenkeys.service", "ExecStart=-/usr/sbin/sshd -i"],
        "sshdgenkeys.service": ["ConditionFileNotEmpty=|!", "ssh-keygen"],
        "verylate.timer": ["OnStartupSec=10", "Unit=verylate.target"],
        "phocus-mobile-server.service": ["ExecStart=/usr/bin/phocus-mobile-server -p 50001"],
        "usb-modules.service": ["Description=USB modules for debug", "ExecStart=/sbin/modprobe ci_hdrc_imx"],
        "rescue.service": ["After=sysinit.target", "/sbin/sulogin", "StandardInput=tty-force"],
    }
    for name, checks in unit_checks.items():
        data = read("lib/systemd/system/" + name).decode()
        assert all(x in data for x in checks), name
        units[name] = checks
    links = {x["path"]: x["target"] for x in extra["systemdLinks"]}
    for name in ("sshd.socket", "phocus-mobile-server.service", "usb-modules.service"):
        assert "etc/systemd/system/verylate.target.wants/" + name in links
    assert "etc/systemd/system/timers.target.wants/verylate.timer" in links
    networks = {name: read("etc/systemd/network/" + name).decode() for name in ("bridge.network", "usb.network")}
    nodes_script = read("usr/bin/program_nodes.sh").decode()
    assert "FW_DIR=/lib/firmware/hbl" in nodes_script and "BLOB_PREFIX=$2" in nodes_script
    assert all(s in nodes_script for s in ("H6D_MS_MODEL", "fx3_wedge.bin", "fx3_victory.bin", "bootimage_even-wedge.bin"))
    fx3 = read("usr/bin/program_fx3.sh", True).decode()
    assert 'EEPROM="/sys/bus/i2c/devices/2-0050/eeprom"' in fx3 and "dd if=$1 of=$EEPROM" in fx3

    uboot = Uboot()
    commands = uboot.commands()
    assert len(commands) == 78 and len({x["name"] for x in commands}) == 78
    names = {x["name"] for x in commands}
    assert {"bmode", "usb", "usbboot", "fatload", "source"} <= names
    assert not ({"fastboot", "dfu", "ums", "sdp"} & names)
    assert next(x for x in commands if x["name"] == "bmode")["handler"] == 0x1780187C
    env = {}
    for key in ("bootcmd", "bootdelay", "preboot", "usbboot", "usbupdate"):
        start = uboot.data.index(key.encode() + b"=")
        env[key] = uboot.data[start:uboot.data.index(0, start)].decode().split("=", 1)[1]
    assert env["bootdelay"] == "0" and not env["preboot"]
    assert "run emmcboot" in env["bootcmd"] and "usb" not in env["bootcmd"]
    assert "fatload usb 0" in env["usbboot"] and "loader.hbl" in env["usbboot"]
    assert "fatload usb 0" in env["usbupdate"] and "hblupdate.img" in env["usbupdate"]
    for at, target in [(0x178047E0, 0x178120E0), (0x178047F0, 0x17812098),
                       (0x1780190C, 0x17800910), (0x17801934, 0x178021C4)]:
        instruction = next(uboot.decoder.disasm(uboot.read(at, 4), at))
        assert instruction.mnemonic == "bl" and int(instruction.op_str[1:], 0) == target
        calls.append({"module": "package-uboot", "address": hex(at), "target": hex(target)})
    dtb_path = "boot/devicetree-zImage-imx6q-hbl-wedge.dtb"
    dtb = fdt_nodes(read(dtb_path))
    usb_path = "/soc/aips-bus@02100000/usb@02184000"
    assert dtb[usb_path]["status"] == b"okay\0" and "dr_mode" not in dtb[usb_path]
    console = dtb["/chosen"]["stdout-path"].rstrip(b"\0").decode()
    assert console.endswith("serial@02020000")
    report = {
        "kind": "static-recovery-ui-network-audit", "firmware": "X1D-50c 1.25.0",
        "cameraFirmwareKnown": False, "cameraCommandsSent": 0, "portProbes": 0,
        "firmwareExecuted": False, "inputHashes": checked, "qml": qml_evidence, "calls": calls,
        "units": units, "networkConfigurationIsNotObservedCameraAddress": networks,
        "packageUboot": {"sha256": hashlib.sha256(uboot.data).hexdigest(), "commandCount": 78,
                         "relevantCommands": sorted(names & {"bmode", "usb", "usbboot", "fatload", "source"}),
                         "absentCommandTableEntries": ["fastboot", "dfu", "ums", "sdp"],
                         "defaultPath": "eMMC；usbboot/usbupdate是独立USB存储加载变量，未被默认bootcmd调用",
                         "consoleInputCheck": "零延时仍检查tstc/getc；未证明机身按键或外部USB连接可进入此控制台",
                         "installedBootloaderKnown": False},
        "linuxDtb": {"stdout": console, "usbNode": usb_path, "usbStatus": "okay", "drModePresent": False},
        "conclusion": "设置重置、控制器重试、卡上整包升级为独立调用；存在共享机型分支，尚无故障机可用的强制重装入口。",
        "limitations": ["H6D 1.21.0/1.21.2未做原包逐字节对比", "共享代码不等于跨机型固件可用",
                        "静态监听配置不证明当前相机端口开放", "bmode参数表初始化及板级ROM入口未闭环",
                        "未读取真实日志、事件或当前升级阶段；不能确定错误1000根因"]}
    path = ROOT / "x1d/research/validation/recovery-entries-static.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"恢复/UI/网络静态核查通过：{len(calls)}条调用、78项固定命令、{len(checked)}个原包输入；无相机命令。")


if __name__ == "__main__":
    run()
