"""固定1.25.0原包的板级描述和USB/SD依赖核对；不执行固件。"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0,str(ROOT / "x1d/tools"))
from binary import BASELINE, ArmElf
from recovery_binary import Uboot, fdt_nodes

manifest = json.loads((ROOT / "x1d/research/baseline-manifest.json").read_text(encoding="utf-8"))
catalog = {entry["path"]:entry["sha256"] for entry in manifest["files"]}
checked = {}


def read(path):
    data = (BASELINE / path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == catalog[path]
    checked[path] = digest
    return data


def prop(value):
    if value and value.endswith(b"\0") and all(c == 0 or 32 <= c < 127 for c in value):
        return value.rstrip(b"\0").decode("ascii").split("\0")
    return [hex(w) for w in struct.unpack(">" + str(len(value)//4) + "I", value)] if len(value)%4 == 0 else value.hex()


dtb = fdt_nodes(read("boot/devicetree-zImage-imx6q-hbl-wedge.dtb"))
selected = {}
for path,values in dtb.items():
    if ("/usdhc@" in path or "/usb@" in path or "/ecspi@" in path and "/m25p80@" in path
            or "/weim@" in path or path in ("", "/chosen", "/regulators/regulator@0")):
        selected[path] = {key:prop(value) for key,value in values.items() if key not in ("linux,phandle","phandle")}

prefix = "/soc/aips-bus@02100000/"
for address in ("02190000","02194000","02198000"):
    assert dtb[prefix + "usdhc@" + address]["status"] == b"disabled\0"
emmc = dtb[prefix + "usdhc@0219c000"]
assert emmc["status"] == b"okay\0" and emmc["bus-width"] == struct.pack(">I",8)
assert "non-removable" in emmc
usb = dtb[prefix + "usb@02184000"]
assert usb["status"] == b"okay\0" and "dr_mode" not in usb
spi = "/soc/aips-bus@02000000/spba-bus@02000000/ecspi@02008000/m25p80@0/"
assert dtb[spi + "mtd0@00000000"]["label"] == b"u-boot\0"
assert dtb[spi + "mtd@0007C000"]["label"] == b"env\0"
assert dtb[spi + "mtd@0007E000"]["label"] == b"env-redundant\0"
fwenv = read("etc/fw_env.config").decode()
env_partitions = [line for line in fwenv.splitlines() if line.startswith("/dev/")]
assert [line.split()[0] for line in env_partitions] == ["/dev/mtd1","/dev/mtd2"]

u = Uboot()
env = {}
for key in ("bootcmd","bootdelay","preboot","emmcboot","usbboot","usbupdate"):
    at = u.data.index((key + "=").encode())
    env[key] = u.data[at:u.data.index(0,at)].decode().split("=",1)[1]
assert env["bootdelay"] == "0" and env["preboot"] == ""
assert "run emmcboot" in env["bootcmd"] and "usb" not in env["bootcmd"]
assert "root=/dev/mmcblk3p${rootpart}" in env["emmcboot"]
assert "fatload usb 0" in env["usbboot"] and "loader.hbl" in env["usbboot"]
assert "fatload usb 0" in env["usbupdate"] and "hblupdate.img" in env["usbupdate"]
assert u.word(0x17802498) == 0x178387a4
assert u.word(0x178387a4) == 0x0219c000
assert u.word(0x1780249c) == 0x0219c000
commands = u.commands()
names = {entry["name"] for entry in commands}
assert {"bmode","usb","usbboot","fatload","source"} <= names
assert not ({"fastboot","dfu","ums","sdp"} & names)

storage = ArmElf(read("usr/bin/storage-daemon"))
calls = []
for at,target,name in [(0x2d91c,0x1b234,"_ZN9FarmProxy11RequestFileERK7QStringyi9hblm_sink"),
                       (0x2df3c,0x1a5f8,"_ZN9FarmProxy8OpenFileERK7QString11hblm_source9hblm_sinkyi19hblm_file_open_mode"),
                       (0x38724,0x1adfc,"_ZN9FarmProxy9CloseFileERK7QStringi")]:
    instruction = storage.instructions(at,4)[0]
    assert instruction.mnemonic == "bl" and int(instruction.op_str[1:],0) == target
    assert storage.name(target) == name
    calls.append({"address":hex(at),"target":hex(target),"symbol":name})
farm_unit = read("lib/systemd/system/msg2dbus-farm.service").decode()
assert "msg2dbus" in farm_unit
read("usr/lib/libappscommon.so.1.0.0")

report = {
    "firmware":"X1D-50c 1.25.0","cameraFirmwareKnown":False,"cameraRequests":0,
    "firmwareExecuted":False,"inputHashes":checked,"selectedDeviceTreeNodes":selected,
    "linuxBootloaderEnvironmentDevices":env_partitions,
    "packageUboot":{"sha256":hashlib.sha256(u.data).hexdigest(),"environment":env,
                    "mmcConfigAddress":"0x178387a4","mmcControllerBase":"0x0219c000",
                    "mmcInitInstructions":u.disassembly(0x1780243c,0x60),
                    "commandCount":len(commands),"relevantCommands":sorted(names & {"bmode","usb","usbboot","fatload","source"}),
                    "absentCommands":["fastboot","dfu","ums","sdp"],
                    "bmodeTableStatus":"modes[2]位于BSS；本轮未闭环有效注册，不能给bmode参数操作建议。",
                    "installedBootloaderKnown":False},
    "farmStorageCalls":calls,
    "farmBridgeExecLines":[line for line in farm_unit.splitlines() if line.startswith("ExecStart=")],
    "limitations":["Linux DTB和包内U-Boot不是ROM熔丝或物理布线的实测",
                   "SD0/SD1的正常应用路径依赖FARM，仍缺直接连SoC ROM的板级证据",
                   "USB dual role驱动与GPIO节点不确定机身外露插座的线路或mux上电状态"]
}
(HERE / "board-evidence.json").write_text(json.dumps(report,ensure_ascii=False,indent=2) + "\n",encoding="utf-8")
print(f"板级静态核对通过：{len(checked)}个输入哈希、eMMC和SPI NOR分区、U-Boot MMC配置、3条FARM文件调用；硬件请求0。")
