"""经授权后只执行一次固定 X1D FARM RAM 模式诊断；默认不打开设备。"""
from __future__ import annotations

import argparse
import ctypes as c
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time

from read_usb_link_once import NativeWinUsb, UsbFailure, U32, ROOT, TIMEOUT_MS, validate_interface
from farm_ram_contract import build_farm_ram_query, parse_farm_ram_reply

# 复用已经实测的 WinUSB 主机接口层；原单项工具与旧证据保持原样。
FROZEN_HOST_FILES = {
    "read_usb_link_once.py": "8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3",
    "usb_diagnostic_contract.py": "80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84",
}


class FarmRamWinUsb(NativeWinUsb):
    def write_query(self, size):
        if not self.prepared or self.sent or size != self.packet_size:
            raise UsbFailure("USB_REQUEST_DENIED")
        packet = build_farm_ram_query(size)
        buffer, count = c.create_string_buffer(packet, size), U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buffer, size, c.byref(count), None), "USB_WRITE")
        return count.value


def attempt_once(transport):
    result = {
        "observedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": "用户本轮指定的第一代 X1D，VID 2756 / PID 0002",
        "firmwareVersion": None, "request": "farm_get_ram_only_mode_req (557)",
        "stage": "open", "ok": False, "writeCompleted": False, "replyMatched": False,
        "replyBytes": 0, "rawReplySaved": False, "pipeTimeoutMs": TIMEOUT_MS,
        "initialization": "沿用已核 WinUSB 接口初始化；仅设置主机传输时限。",
        "knownCameraSideEffects": ["现有 USB/UART/RTOS 队列及可能的诊断记录",
                                   "原厂 SUC 转发时操作 IMX IRQ Timer 通信信号",
                                   "原厂回复可能等待 SUC 链路；主机超时不会撤销机内排队"],
        "interpretationLimit": "仅判断 FARM 是否报告 RAM 模式已生效；0 包括中间状态；不代表存储可用或错误 1000 已恢复。",
    }
    started = time.monotonic()
    try:
        info = transport.open()
        result["interface"] = info
        result["stage"] = "validate-interface"
        size = validate_interface(info)
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
        result["stage"] = "read-reply"
        packet = transport.read_reply(size)
        result["replyBytes"] = len(packet)
        result["stage"] = "validate-reply"
        result["value"] = asdict(parse_farm_ram_reply(packet, size))
        result["replyMatched"] = True
        result["ok"], result["stage"] = True, "complete"
    except UsbFailure as error:
        result["error"], result["win32"] = error.code, error.win32
    except ValueError:
        result["error"] = "USB_REPLY_UNREVIEWED"
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
        result["elapsedMs"] = round((time.monotonic() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-authorized-once", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.run_authorized_once or args.report is None:
        parser.error("需要本轮既有诊断授权及唯一结果文件；没有打开设备")
    if Path.cwd().resolve() != ROOT:
        parser.error("必须在当前 Hasselblad local 工作区运行")
    source_hashes = {}
    for name in (*FROZEN_HOST_FILES, "read_farm_ram_once.py", "farm_ram_contract.py"):
        source_hashes[name] = hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
    for name, expected in FROZEN_HOST_FILES.items():
        if source_hashes[name] != expected:
            parser.error("复用主机接口层发生变化，需要重新核对；没有打开设备")
    destination = args.report.resolve()
    destination.relative_to((ROOT / "x1d/research/validation/hardware").resolve())
    if not destination.parent.is_dir():
        parser.error("结果目录不存在；没有打开设备")
    # 独占创建：无论失败还是成功，都不覆盖本轮记录或自动再次发送。
    with destination.open("x", encoding="utf-8") as output:
        result = attempt_once(FarmRamWinUsb())
        result["sourceFilesSha256"] = source_hashes
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
