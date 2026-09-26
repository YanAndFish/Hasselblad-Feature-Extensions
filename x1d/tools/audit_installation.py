"""复核固定原包的安装链证据；不运行升级器，不产生修改固件。"""
from __future__ import annotations

import hashlib
import json
import re
import struct

from binary import ArmElf, BASELINE, CACHE, ROOT
from prepare_baseline import SHA256


def run() -> None:
    package = CACHE / "X1D_v1_25_0.cim"
    if hashlib.sha256(package.read_bytes()).hexdigest() != SHA256:
        raise ValueError("原包不同")
    upgrade = ArmElf.load("usr/bin/upgrade-daemon")
    upgrade_sha = hashlib.sha256(upgrade.data).hexdigest()
    if upgrade_sha != "aa62f9e03208d2306c0890fc9d5d9c522569359922a659060da270da381c8d0c":
        raise ValueError("升级器不同")
    anchors = []
    # 地址与调用目标来自原 ARM 指令；这不是执行或安装测试。
    for at, target, purpose in [
        (0x3A8A8, 0x29248, "升级入口读取 CIM"),
        (0x29728, 0x28448, "文件读取进入头解析"),
        (0x28550, 0x2B954, "读取公开头"),
        (0x28CC0, 0x2FCEC, "读取私有头"),
        (0x30A40, 0x2D6AC, "format 3 私有头内容校验"),
        (0x2D6F8, 0x352DC, "内容摘要辅助函数"),
        (0x2D814, 0x1A30C, "私有头摘要比较"),
        (0x3ADC8, 0x342C8, "逐项解包"),
        (0x34A08, 0x352DC, "解包后文件摘要"),
        (0x34A44, 0x1A30C, "文件摘要比较"),
        (0x3AE9C, 0x40BEC, "解包后准备升级"),
        (0x3A154, 0x1A030, "准备完成后启动脚本进程"),
    ]:
        calls = list(upgrade.direct_calls(at, 4))
        if len(calls) != 1 or calls[0][1] != target:
            raise ValueError(f"调用证据变化：{at:#x}")
        anchors.append({"address": f"0x{at:x}", "target": f"0x{target:x}", "purpose": purpose})
    if upgrade.word(0x35324) != 0xE3A01001:
        raise ValueError("摘要算法参数不同")
    # 仅枚举接口名，不读取或输出任何凭据/密钥常量。
    imports = sorted({s.name for s in upgrade.symbols if s["st_shndx"] == "SHN_UNDEF"})
    aes = [name for name in imports if name.startswith("AES_")]
    signature_imports = [name for name in imports if re.search(r"RSA_verify|DSA_verify|ECDSA_verify|EVP_.*Verify|PKCS7_verify|CMS_verify", name)]
    boot = (BASELINE / "uboot.bin").read_bytes()
    if hashlib.sha256(boot).hexdigest() != "bad3ab600873fa78adb7cc06190ff092052ff11b20f012da9c18cf22cddba8d3":
        raise ValueError("包内 U-Boot 不同")
    if boot[:4] != bytes.fromhex("d1002040"):
        raise ValueError("IVT 头不同")
    boot_match = re.search(rb"bootcmd=[ -~]+\x00", boot)
    if boot_match is None:
        raise ValueError("包内启动命令缺失")
    boot_command = boot_match.group()[:-1].decode("ascii")
    script = (BASELINE / "hbl-upgrade").read_text()
    nodes = (BASELINE / "usr/bin/program_nodes.sh").read_text()
    post = (BASELINE / "usr/bin/hbl-post-upgrade").read_text()
    required = {
        "hbl-upgrade": (script, ["do_mkfs", "bzcat ${ROOTFS}", "program_nodes.sh", "fw_setenv upgrade 1", "since we don't upgrade u-boot"]),
        "program_nodes.sh": (nodes, ["update_farm ${TOOL_PREFIX}", "update_spc ${TOOL_PREFIX}", "update_fx3 ${TOOL_PREFIX}", "update_suc ${TOOL_PREFIX}"]),
        "hbl-post-upgrade": (post, ["fw_setenv current_bootpart ${new_bootpart}"]),
    }
    script_anchors = []
    for name, (content, fragments) in required.items():
        for fragment in fragments:
            lines = [number for number, line in enumerate(content.splitlines(), 1) if fragment in line]
            if not lines:
                raise ValueError("脚本证据缺失")
            script_anchors.append({"file": name, "fragment": fragment, "lines": lines})
    report = {
        "schemaVersion": 1, "model": "X1D-50c (first generation)", "firmware": "1.25.0",
        "packageSha256": SHA256, "upgradeDaemonSha256": upgrade_sha,
        "method": "固定原始字节、调用位置及脚本文本复核；未执行 ARM 升级程序",
        "cameraAccess": False, "modifiedPackageCreated": False,
        "anchors": anchors, "scriptAnchors": script_anchors,
        "aesImports": aes, "signatureVerificationImportsFound": signature_imports,
        "signatureSearchLimit": "未见相关导入不证明所有路径或实机启动链都没有签名认证",
        "bundledUbootCsfPointer": struct.unpack_from("<I", boot, 24)[0],
        "bundledUbootBootCommand": boot_command,
        "bootImageLimit": "升级脚本不写入包内 U-Boot；不能用它代替实机引导器或 fuse 状态",
        "installationVerified": False, "recoveryVerifiedOnCamera": False,
    }
    target = ROOT / "x1d/research/installation-evidence.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"安装链证据复核通过：{len(anchors)} 处调用、{len(script_anchors)} 处脚本依据；未执行升级、未连接相机。")


if __name__ == "__main__":
    run()
