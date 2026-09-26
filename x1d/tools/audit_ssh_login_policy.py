"""只核对固定原包的 SSH 配置、编译选项和失败上限；不读取认证材料。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

from binary import ROOT, ArmElf

SAFE_INPUTS = {
    "usr/sbin/sshd", "etc/ssh/sshd_config", "etc/ssh/sshd_config_readonly",
    "lib/systemd/system/sshd.socket", "lib/systemd/system/sshd@.service",
    "lib/systemd/system/sshdgenkeys.service",
}
SSHD_SHA = "2cee4f80cd24136366f943b25ec9305b27e0aa0a59fa37c594900cf71c338211"


def run():
    assert Path.cwd().resolve() == ROOT.resolve()
    path = ROOT / "x1d/recovery-review/20260910-usb-sd/inspect_payloads.py"
    spec = importlib.util.spec_from_file_location("x1d_ssh_policy_safe_inputs", path)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    names = []

    class SafeSelection(set):
        def __contains__(self, name):
            # 仅枚举有关模块/配置的文件名；绝不提取账户数据库或密钥文件。
            if (name.startswith(("etc/pam.d/", "etc/security/", "lib/security/", "usr/lib/security/"))
                    or re.search(r"(sshd|pam[_-]|fail2ban|faillock|tally|denyhosts)", name, re.I)):
                names.append(name)
            return super().__contains__(name)

    reader.WANTED = SafeSelection(SAFE_INPUTS)
    found = reader.inputs()
    data = found["usr/sbin/sshd"]
    assert len(data) == 707044 and hashlib.sha256(data).hexdigest() == SSHD_SHA
    ssh = ArmElf(data)
    needed = [t.needed for t in ssh.elf.get_section_by_name(".dynamic").iter_tags() if t.entry.d_tag == "DT_NEEDED"]
    assert not any("pam" in n.lower() for n in needed)
    assert not any(s.name.startswith("pam_") for s in ssh.symbols)
    version = b"OpenSSH_7.1p2\0"
    assert ssh.read(0x7cf98, len(version)) == version
    evidence = []

    def check(address, mnemonic, operands):
        i = ssh.instructions(address, 4)[0]
        assert (i.mnemonic, i.op_str) == (mnemonic, operands), hex(address)
        evidence.append({"address": hex(address), "bytes": bytes(i.bytes).hex(),
                         "mnemonic": mnemonic, "operands": operands})

    for row in [
        (0xcf68, "add", "r4, r7, #0x2000"),
        (0xcfe8, "ldr", "r3, [r4, #0xd20]"),
        (0xcfec, "cmn", "r3, #1"),
        (0xcff0, "moveq", "r3, #6"),
        (0xcff4, "streq", "r3, [r4, #0xd20]"),
        (0xd99c, "b", "#0xe36c"),
        (0xe36c, "add", "r7, r7, #0x2d00"),
        (0xe370, "add", "r7, r7, #0x20"),
        (0xda40, "b", "#0xe01c"),
        (0xe030, "bl", "#0x45104"),
        (0x15db8, "str", "r0, [r5, #0x14]"),
        (0x15dbc, "add", "r3, r7, #0x2000"),
        (0x15dc0, "ldr", "r3, [r3, #0xd20]"),
        (0x15dc4, "cmp", "r3, r0"),
        (0x15dc8, "ble", "#0x15fd4"),
        (0x15fd8, "bl", "#0x14640"),
        (0x146ac, "bl", "#0x4509c"),
        (0x146b8, "bl", "#0x4bd10"),
    ]:
        check(*row)
    assert (ssh.word(0xba8b8), ssh.word(0xba8bc), ssh.word(0xba8c0)) == (0x7e678, 93, 1)
    assert ssh.read(0x7e678, 7) == b"usepam\0"
    assert (ssh.word(0xbabdc), ssh.word(0xbabe0), ssh.word(0xbabe4)) == (0x7fd54, 52, 3)
    assert ssh.read(0x7fd54, 13) == b"maxauthtries\0"
    unsupported = (0xe02c + 8 + ssh.word(0xe70c)) & 0xffffffff
    message = b"%s line %d: Unsupported option %s\0"
    assert ssh.read(unsupported, len(message)) == message
    assert (0x146b4 + 8 + ssh.word(0x146e8)) & 0xffffffff == 0x80d28
    message = b"Too many authentication failures\0"
    assert ssh.read(0x80d28, len(message)) == message
    config = found["etc/ssh/sshd_config"].decode()
    assert "#MaxAuthTries 6" in config and "#UsePAM no" in config
    active = []
    for line in config.splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            active.append(value)
    assert not any(x.lower().startswith(("maxauthtries ", "usepam ", "include ", "match ")) for x in active)
    service = found["lib/systemd/system/sshd@.service"].decode()
    assert "ExecStart=-/usr/sbin/sshd -i" in service
    socket = found["lib/systemd/system/sshd.socket"].decode()
    assert "ListenStream=22" in socket and "Accept=yes" in socket
    assert not any(re.search(r"(pam[_-]|fail2ban|faillock|tally|denyhosts)", x, re.I) for x in names)
    report = {
        "firmware": "官方 X1D-50c 1.25.0；实机版本未知",
        "cameraRequestsSent": 0, "firmwareExecuted": False, "credentialsRead": False,
        "sources": {name: hashlib.sha256(value).hexdigest() for name, value in found.items()},
        "sshdVersionString": "OpenSSH_7.1p2", "sshdNeededLibraries": needed,
        "authenticationRelatedFileNameMatches": names,
        "explicitConfiguration": {"startup": "/usr/sbin/sshd -i", "socketPort": 22,
                                  "MaxAuthTriesExplicitlySet": False, "UsePAMExplicitlySet": False},
        "compiledFindings": {"maxAuthTriesDefault": 6, "optionsFieldOffset": "0x2d20",
                             "UsePAMKeyword": "Unsupported opcode 93",
                             "failureLimitBehavior": "当前连接认证失败计数达到上限后进入断开路径"},
        "instructionChecks": evidence,
        "upstreamCrossReference": [
            "https://github.com/openssh/openssh-portable/blob/V_7_1_P2/servconf.c",
            "https://github.com/openssh/openssh-portable/blob/V_7_1_P2/servconf.h",
            "https://github.com/openssh/openssh-portable/blob/V_7_1_P2/auth2.c"],
        "limits": ["没有证据证明未知实机使用相同版本、配置或账户策略",
                   "未发现相关 PAM/封禁组件文件名，不等于穷尽所有厂家定制认证副作用",
                   "失败上限涵盖认证尝试，不能换算为剩余可输错密码次数",
                   "未读取账户、口令散列、SSH 主机/用户密钥，未执行或模拟失败登录"]}
    output = ROOT / "x1d/research/validation/ssh-login-policy-static.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SSH 策略离线核查通过：{len(found)} 份非认证输入、{len(evidence)} 条指令；设备请求与认证材料读取均为 0。")


if __name__ == "__main__":
    run()
