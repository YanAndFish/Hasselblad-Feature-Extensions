"""按已有授权执行一次系统MMC容量读取；默认无设备访问。"""
import argparse
import ctypes as c
from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import time

from read_usb_link_once import NativeWinUsb, UsbFailure, U32, validate_interface
from read_sutest_ram_once import SutestRamWinUsb, READ_BUDGET_MS, MAX_READ_CALLS, FROZEN_HOST_FILES
from sutest_ram_contract import ROOT, PACKET_SIZE, is_late_farm_reply
from sutest_capacity_contract import COMMAND, build_query, parse_envelope, parse_capacity

FROZEN_DEPENDENCIES = {
    **FROZEN_HOST_FILES,
    "sutest_error_log_contract.py": "3f405e08dcd2ae2a7536febba104aa494ce0a90b2338eb446ca8c68ee921d2cc",
    "read_sutest_ram_once.py": "f6b7f7606acba7ed292811fde6923fb7963188152a89ec24d363d2f366a297e1",
    "sutest_ram_contract.py": "65f92a335d3aa681aa2d3d8b56f39e655d026f97ef7af5a69b8ecc6482922abf",
}


class CapacityWinUsb(SutestRamWinUsb):
    def __init__(self, token):
        self.token, self.request = token, build_query(token)
        NativeWinUsb.__init__(self)
        self.read = 0

    def write_query(self, size):
        if (not self.prepared or self.sent or size != self.packet_size or size != PACKET_SIZE
                or self.request != build_query(self.token)):
            raise UsbFailure("USB_REQUEST_DENIED")
        buffer, count = c.create_string_buffer(self.request, size), U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buffer, size, c.byref(count), None), "USB_WRITE")
        return count.value


def attempt_once(transport, token, clock=time.monotonic):
    result = {
        "observedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": "用户指定的第一代 X1D，VID 2756 / PID 0002", "firmwareVersion": None,
        "stage": "open", "ok": False, "applicationRequestsSubmitted": 0,
        "writeCompleted": False, "readCalls": 0, "replyBytes": 0, "replyMatched": False,
        "lateFarmRepliesDiscarded": 0, "command": COMMAND, "correlationToken": token,
        "writeTimeoutMs": 2000, "readBudgetMs": READ_BUDGET_MS, "maxReadCalls": MAX_READ_CALLS,
        "cameraProcessHardDeadline": False, "rawReplySaved": False, "stderrSaved": False,
        "pipelineUpstreamSuccessVerified": False, "currentRealtimeStateVerified": False,
        "scope": "固定mmcblk3的MMC类型、可移动标志、主用户区扇区容量及唯一根设备参数",
        "knownCameraSideEffects": ["原厂 sutest/USB/UART/D-Bus 初始化及可能的诊断日志，参见上次实测说明",
            "若服务未运行，原厂激活可能加载 i2c-dev 并启动 sutest-daemon",
            "启动固定shell/cat/awk，只读固定sysfs属性与已缓存启动参数，返回严格字段；无块内容读取或节点探测"],
        "limits": ["最后awk的退出码不能证明cat成功；必须同时得到全部四项合法字段",
            "缺项、UNKNOWN、多root、错设备类型、截断或超时均未知，不枚举其他设备",
            "这是MMC主用户区可寻址总容量，不是空闲空间、CIM大小或其他控制器存储容量",
            "removable=0不独立证明物理内置；结合MMC类型、当前root参数和固定Wedge板型映射",
            "没有机内进程硬截止；主机超时不取消机内工作，不追加kill或重试"],
    }
    started = clock()
    try:
        result["interface"] = info = transport.open()
        result["stage"] = "validate-interface"
        size = validate_interface(info)
        if size != PACKET_SIZE:
            raise UsbFailure("USB_PACKET_SIZE_UNREVIEWED")
        result["packetSize"] = size
        result["controlOut"], result["controlIn"] = "0x02", "0x82"
        result["stage"] = "host-timeout-policy"
        transport.prepare()
        result["stage"] = "write-query"
        count = transport.write_query(size)
        result["writeReportedBytes"] = count
        if count != size:
            raise UsbFailure("USB_SHORT_WRITE")
        result["writeCompleted"] = True
        deadline = clock() + READ_BUDGET_MS / 1000
        for _ in range(MAX_READ_CALLS):
            result["stage"] = "read-reply"
            remaining = int((deadline - clock()) * 1000)
            if remaining <= 0:
                raise UsbFailure("USB_READ_BUDGET")
            packet = transport.read_reply(size, min(remaining, READ_BUDGET_MS))
            result["replyBytes"] += len(packet)
            result["stage"] = "validate-envelope"
            if is_late_farm_reply(packet) and result["lateFarmRepliesDiscarded"] == 0:
                result["lateFarmRepliesDiscarded"] = 1
                continue
            envelope = parse_envelope(packet, token)
            result["replyMatched"] = True
            result["sutestResult"] = envelope.result
            if envelope.result:
                raise UsbFailure("SUTEST_PROCESS_FAILED")
            result["stage"] = "validate-diagnostic-fields"
            result["capacity"] = parse_capacity(envelope.output_field)
            result["ok"], result["stage"] = True, "complete"
            break
        else:
            raise UsbFailure("USB_NO_MATCHED_REPLY")
    except UsbFailure as error:
        result["error"], result["win32"] = error.code, error.win32
    except ValueError:
        result["error"] = "DIAGNOSTIC_OUTPUT_UNKNOWN" if result["replyMatched"] else "USB_REPLY_UNREVIEWED"
    except Exception:
        result["error"] = "USB_INTERNAL"
    finally:
        result["applicationRequestsSubmitted"] = int(transport.sent)
        result["readCalls"] = int(transport.read)
        result["deviceHandleOpened"] = transport.opened
        result["winUsbInitialized"] = transport.initialized
        result["closure"] = transport.close()
        if not all(result["closure"].values()):
            result["ok"] = False
            result.setdefault("error", "USB_CLOSE")
        result["elapsedMs"] = round((clock() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-authorized-once", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.run_authorized_once or args.report is None or Path.cwd().resolve() != ROOT:
        parser.error("需要本次已有授权、唯一结果文件和当前Hasselblad工作区；没有打开设备")
    names = (*FROZEN_DEPENDENCIES, "read_sutest_capacity_once.py", "sutest_capacity_contract.py")
    hashes = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in names}
    if any(hashes[name] != expected for name, expected in FROZEN_DEPENDENCIES.items()):
        parser.error("已审阅依赖发生变化；没有打开设备")
    destination = args.report.resolve()
    destination.relative_to((ROOT / "x1d/research/validation/hardware").resolve())
    if not destination.parent.is_dir():
        parser.error("既有结果目录不存在；没有打开设备")
    token = secrets.randbelow(0xffffffff) + 1
    with destination.open("x", encoding="utf-8") as output:
        result = attempt_once(CapacityWinUsb(token), token)
        result["sourceFilesSha256"] = hashes
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
