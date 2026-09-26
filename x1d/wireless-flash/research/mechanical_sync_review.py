"""固定官方 FARM/SUC 的机械快门候选点离线复核；无设备接口。"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
SUC_SHA = "6bce5b264f431250be952dcfcaefee45a435a6355ebc22b45c9e824c165725a7"


def run(farm, suc):
    assert Path.cwd().resolve() == HERE.parents[1]
    assert hashlib.sha256(farm.data).hexdigest() == FARM_SHA
    assert hashlib.sha256(suc.data).hexdigest() == SUC_SHA
    checks = []
    for source, address, target in (
        (farm, 0x1c5240, 0x213fcc),
        (farm, 0x1c52a0, 0x1c3810),
        (farm, 0x1c52e4, 0x1c4dc8),
        (suc, 0x08005286, 0x0800eeb4),
        (suc, 0x08005596, 0x08009554),
        (suc, 0x080055a8, 0x08008738),
        (suc, 0x080055d8, 0x08009554),
        (suc, 0x080055ea, 0x08008738),
        (suc, 0x080055fa, 0x08009554),
        (suc, 0x08005616, 0x08008738),
        (suc, 0x08009676, 0x080086ac),
        (suc, 0x08005222, 0x0800edb4),
        (suc, 0x0800522c, 0x0800edb4),
    ):
        instruction = source.instructions(address, 4)[0]
        assert instruction.mnemonic == "bl" and int(instruction.op_str[1:], 16) == target
        checks.append({"at": hex(address), "calls": hex(target), "bytes": instruction.bytes.hex()})
    regions = {
        "farm_flush_and_notification": (farm, 0x1c5218, 0xec),
        "suc_mechanical_commands": (suc, 0x0800557c, 0xa6),
        "suc_lens_command_encoding": (suc, 0x08009654, 0x2a),
        "suc_lens_ack_validation": (suc, 0x08008e18, 0x22),
        "suc_farm_packet_send": (suc, 0x0800edb4, 0x30),
    }
    report = {
        "sourceVersion": "X1D 1.25.0",
        "farmSha256": FARM_SHA, "sucSha256": SUC_SHA,
        "checks": checks,
        "regions": {name: [{"at": hex(i.address), "instruction": i.mnemonic + " " + i.op_str}
                            for i in source.instructions(address, length)]
                    for name, (source, address, length) in regions.items()},
        "candidateGroups": [
            "拍摄流程开始通知：已存在，但不是物理曝光开始",
            "FARM 冲洗启动及回复：参考点，需要严格限定拍摄调用",
            "镜头命令提交：常规命令 3，长曝光路径分别使用命令 4 和 5",
            "镜头命令等待返回：须区分完成、失败及超时，不能直接命名后帘",
            "SUC 发往 FARM 的曝光配置消息：须区分同流程两次调用",
        ],
        "unresolved": ["实际闪光同步信号的来源与各点的时间关系",
                       "镜头回复是否可从现有 Linux 通道观察",
                       "同次机械曝光标识、取消和超时规则",
                       "多个候选点的安全事件导出与原厂流程保持"],
        "hardwareRequests": 0, "installed": False, "physicalTimingVerified": False,
    }
    output = HERE / "build/mechanical-sync-review.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"callChecks": len(checks), "candidateGroups": 5, "hardwareRequests": 0, "installed": False}))
    return report
