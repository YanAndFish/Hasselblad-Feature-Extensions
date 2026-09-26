"""仅在内存解包固定官方固件；输出 USB/SD 有关脱敏静态证据。"""
from __future__ import annotations

import bz2
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(ROOT / "x1d/tools"))
from prepare_baseline import CACHE, SIZE, SHA256, REFERENCE, fetch, reference_constants, sha
from binary import ArmElf, Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
from Crypto.Cipher import AES

WANTED = {
    "lib/firmware/hbl/fx3/fx3_wedge-v0.0-14268-e0ef6ae.bin",
    "lib/firmware/hbl/farm/bootimage_even-wedge-v1.25.0-13075-c9bb91d.bin",
    "lib/firmware/hbl/farm/bootimage_odd-wedge-v1.25.0-13075-c9bb91d.bin",
    "usr/bin/program_farm.sh",
    "usr/bin/msg2dbus",
    "lib/modules/3.14.28-1.0.0_ga+yocto+gf7d0ab5/kernel/drivers/usb/chipidea/ci_hdrc.ko",
}


def inputs():
    firmware = (CACHE / "X1D_v1_25_0.cim").read_bytes()
    assert len(firmware) == SIZE and sha(firmware) == SHA256
    constants = reference_constants(fetch(REFERENCE, 65536))
    match = re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})", firmware[:128])
    assert match is not None
    year, month, day, hour, minute, second = map(int, match.groups())
    initial = hashlib.md5(constants["IV_SALT"] + bytes([
        year // 100, year % 100, month, day, hour, minute, second]) + bytes(9)).digest()
    offset, size = 0x2600, 63123278
    payload = bytearray()
    for pos in range(0, size, 4096):
        count = min(4096, size - pos)
        block = firmware[offset + pos:offset + pos + ((count + 15) // 16) * 16]
        payload.extend(AES.new(constants["STATIC_KEY"], AES.MODE_CBC, initial).decrypt(block)[:count])
    assert sha(payload) == "8e9ef7f19411a355eeef7b44361d35635c80a248cc9753b0a8456cf1008583ca"
    found = {}
    with bz2.BZ2File(io.BytesIO(payload)) as expanded, tarfile.open(fileobj=expanded, mode="r|") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name in WANTED:
                assert member.isfile() and 0 < member.size < 5000000
                found[name] = archive.extractfile(member).read()
    assert set(found) == WANTED
    return found


def fx3_image(data):
    assert data[:2] == b"CY"
    position, sections, checksum = 4, [], 0
    while position + 8 <= len(data):
        size_words, address = struct.unpack_from("<II", data, position)
        position += 8
        if size_words == 0:
            expected = struct.unpack_from("<I", data, position)[0]
            assert checksum == expected and position + 4 == len(data)
            return sections, address
        size = size_words * 4
        assert size < 1000000 and position + size <= len(data)
        content = data[position:position + size]
        checksum = (checksum + sum(struct.unpack("<" + str(size_words) + "I", content))) & 0xffffffff
        sections.append((position, address, content))
        position += size
    raise ValueError("FX3 image incomplete")


def reconstruct_farm(found):
    even = next(b for n,b in found.items() if "/farm/bootimage_even" in n)
    odd = next(b for n,b in found.items() if "/farm/bootimage_odd" in n)
    assert len(even) == len(odd)
    spread = [sum(((i >> bit) & 1) << (2 * bit) for bit in range(8)) for i in range(256)]
    data = b"".join((spread[e] | (spread[o] << 1)).to_bytes(2, "big") for e,o in zip(even,odd))
    assert sha(data) == "96449fce1e2bd5d9f181e92d84704154f97f3a758a5adeac11b466cc023f82f5"
    assert struct.unpack_from("<II", data, 0x20) == (0xaa995566, 0x584c4e58)
    assert sum(struct.unpack_from("<11I", data, 0x20)) & 0xffffffff == 0xffffffff
    # 对整个结果反变换，防止只凭可读字符串认定重组正确。
    for i, (e,o) in enumerate(zip(even,odd)):
        word = int.from_bytes(data[2*i:2*i+2], "big")
        assert sum(((word >> (2*bit)) & 1) << bit for bit in range(8)) == e
        assert sum(((word >> (2*bit+1)) & 1) << bit for bit in range(8)) == o
    return data


def instructions(data, base, ranges):
    cs = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    result = []
    for address,size in ranges:
        offset = address - base
        assert 0 <= offset and offset + size <= len(data)
        result.extend({"address": hex(i.address), "bytes": bytes(i.bytes).hex(),
                       "mnemonic": i.mnemonic, "operands": i.op_str}
                      for i in cs.disasm(data[offset:offset+size],address))
    return result


def run():
    found = inputs()
    report = {"firmware": "X1D-50c 1.25.0", "cimSha256": SHA256,
              "cameraAccess": False, "firmwareExecuted": False, "files": []}
    for name, data in found.items():
        item = {"path": name, "sha256": sha(data), "bytes": len(data)}
        if "/fx3/" in name:
            sections, entry = fx3_image(data)
            item["sections"] = [{"fileOffset": hex(p), "loadAddress": hex(a), "bytes": len(b)} for p,a,b in sections]
            item["entry"] = hex(entry)
            item["imageChecksumVerified"] = True
            descriptors = []
            for pos, address, content in sections:
                for i in range(len(content) - 17):
                    if content[i:i+2] != b"\x12\x01":
                        continue
                    b = content[i:i+18]
                    usb, vid, pid, device = struct.unpack_from("<HxxxxHHH", b, 2)
                    if vid != 0x2756 or usb not in (0x200, 0x210, 0x300, 0x310):
                        continue
                    descriptors.append({"fileOffset": hex(pos+i), "address": hex(address+i),
                                        "bcdUSB": hex(usb), "idVendor": hex(vid), "idProduct": hex(pid),
                                        "bDeviceClass": b[4], "bDeviceSubClass": b[5], "bDeviceProtocol": b[6],
                                        "iManufacturer": b[14], "iProduct": b[15], "iSerialNumber": b[16],
                                        "serialStringRead": False})
            item["deviceDescriptors"] = descriptors
            assert len(descriptors) == 2 and {x["bcdUSB"] for x in descriptors} == {"0x210", "0x300"}
            code = next((p,a,b) for p,a,b in sections if a <= 0x40004a24 < a + len(b))
            p,a,b = code
            assert struct.unpack_from("<I",b,0x40004b3c-a)[0] == 0x40017de0
            assert struct.unpack_from("<I",b,0x40004b44-a)[0] == 0x40017c60
            item["descriptorRegistrationInstructions"] = instructions(b,a,[(0x40004a24,20),(0x40004a44,20)])
            item["registrationMeaning"] = "同一描述符注册函数收到类型1和7的描述符；地址分别指向USB3与USB2设备描述符。未读取USB序列号字符串。"
            item["selectedStrings"] = [{"fileOffset": hex(m.start()), "value": m.group().decode()}
                for m in re.finditer(rb"[ -~]{6,}", data)
                if re.fullmatch(rb"(?:CyU3P|GPIF|USB|FX3|[A-Za-z_]*Usb)[A-Za-z0-9_ ]{0,100}", m.group())]
        if name.endswith("/ci_hdrc.ko"):
            module = ArmElf(data)
            wanted = {"ci_hdrc_host_init", "ci_hdrc_gadget_init", "ci_otg_role", "of_usb_get_dr_mode"}
            item["roleSymbols"] = [{"name":s.name, "size":s["st_size"], "section":s["st_shndx"]}
                                   for s in module.symbols if s.name in wanted]
            assert {x["name"] for x in item["roleSymbols"]} == wanted
            item["meaning"] = "Linux模块同时含host/gadget实现；不能因为只看到host子目录就认定无device能力，更不能据此推断外露接线。"
        if name == "usr/bin/program_farm.sh":
            item["selectedLines"] = [{"line": i, "text": line} for i,line in enumerate(data.decode().splitlines(),1)
                if any(word in line for word in ("FARM", "farm", "eim", "qspi", "spi", "BOOT", "boot", "FPGA", "flashcp", "mtd3", "mtd4"))]
        report["files"].append(item)
    farm = reconstruct_farm(found)
    fsbl_offset,fsbl_size,fsbl_load = struct.unpack_from("<III",farm,0x30)
    assert (fsbl_offset,fsbl_size,fsbl_load) == (0x1700,0x1c014,0)
    fsbl = farm[fsbl_offset:fsbl_offset+fsbl_size]
    it_offset,pt_offset = struct.unpack_from("<II",farm,0x98)
    part_count = struct.unpack_from("<I",farm,it_offset+4)[0]
    assert part_count == 3
    partitions = []
    for index in range(part_count):
        at = pt_offset + index * 64
        words = struct.unpack_from("<16I",farm,at)
        assert sum(words) & 0xffffffff == 0xffffffff
        offset,size = words[5]*4,words[2]*4
        assert offset + size <= len(farm)
        partitions.append({"headerFileOffset":hex(at),"dataFileOffset":hex(offset),"bytes":size,
                           "loadAddress":hex(words[3]),"entryAddress":hex(words[4]),
                           "attributes":hex(words[6]),"headerChecksumVerified":True})
    boot_check = instructions(fsbl,0,[(0x10898,0x50),(0x5e4,0x24)])
    expected = {0x108a8:("and","r4, r0, #7"),0x108ac:("cmp","r4, #1"),
                0x108b0:("beq","#0x10b44"),0x108b4:("cmp","r4, #2"),
                0x108b8:("beq","#0x10be4"),0x108bc:("cmp","r4, #0"),
                0x108c0:("beq","#0x109d0"),0x108dc:("mov","r0, #0xa000"),
                0x604:("b","#0x604")}
    by_address = {int(x["address"],0):x for x in boot_check}
    for at,pair in expected.items():
        assert (by_address[at]["mnemonic"],by_address[at]["operands"]) == pair
    text_wanted = [b"Xilinx First Stage Boot Loader ", b"Boot mode is QSPI", b"Boot mode is NOR", b"Boot mode is JTAG",
                   b"ILLEGAL_BOOT_MODE", b"In FsblHookFallback function ", b"QSPI is in Dual Parallel connection",
                   b"satadriver_read_sectors", b"satadriver_write_sectors", b"satadriver_enable_sd_clk",
                   b"%sSD0 not mounted", b"%s%s(): SD1 not present in current product", b"farm_microsd_busy_event",
                   b"%sFailed to restore calibration data from SD card!",b"usbif_firmware_version_req"]
    selected = []
    for value in text_wanted:
        assert value in farm
        selected.append({"fileOffset":hex(farm.index(value)), "value":value.decode()})
    report["farmReconstruction"] = {
        "method":"将even字节各位放入16位字的偶数位、odd字节各位放入奇数位，按大端输出该16位字；仅在内存重组。",
        "bytes":len(farm),"sha256":sha(farm),"completeInverseVerified":True,
        "bootHeaderMagicVerified":True,"bootHeaderChecksumVerified":True,
        "partitionCount":part_count,"partitions":partitions,
        "fsblFileOffset":hex(fsbl_offset),"fsblLoadAddress":hex(fsbl_load),
        "fsblBootModeChecks":boot_check,"selectedStrings":selected,
        "fsblResult":"所查原包FSBL读取BOOT_MODE_REG低3位，只分派1(QSPI)、2(NOR)、0(JTAG)；5(SD)进入ILLEGAL_BOOT_MODE。Fallback hook日志之后为自分支。不是SD救援链；当前实机安装版本仍未知。",
        "sdStringLimit":"应用包含SD0/SD1、satadriver与单独microsd事件；字符串本身不确定卡槽的原理图接线或校准数据所在介质。"
    }
    destination = HERE / "payload-evidence.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"固定原包 {len(found)} 个输入、FX3 分段校验与两项设备描述符、FARM 启动头/3项分区头/整幅反变换、FSBL 分支校验通过。相机访问 0。")


if __name__ == "__main__":
    run()
