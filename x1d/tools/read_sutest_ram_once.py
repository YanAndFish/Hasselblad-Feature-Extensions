"""按既有授权执行一次固定 Properties.Get；默认不打开设备。"""
from __future__ import annotations

import argparse
import ctypes as c
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import time

from read_usb_link_once import NativeWinUsb, UsbFailure, U32, validate_interface
from sutest_ram_contract import ROOT, PACKET_SIZE, COMMAND, build_query, parse_reply, is_late_farm_reply

READ_BUDGET_MS = 6000
MAX_READ_CALLS = 2  # 至多一帧既有 FARM 查询的迟到回复，再加本次匹配回复。
FROZEN_HOST_FILES = {
    "read_usb_link_once.py": "8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3",
    "usb_diagnostic_contract.py": "80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84",
}


class SutestRamWinUsb(NativeWinUsb):
    def __init__(self, token):
        self.token = token
        self.request = build_query(token)  # 在打开设备前验证来源与固定封装。
        super().__init__()
        self.read = 0

    def write_query(self, size):
        if not self.prepared or self.sent or size != self.packet_size or size != PACKET_SIZE:
            raise UsbFailure("USB_REQUEST_DENIED")
        if self.request != build_query(self.token):
            raise UsbFailure("USB_REQUEST_CHANGED")
        buffer, count = c.create_string_buffer(self.request, size), U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buffer, size, c.byref(count), None), "USB_WRITE")
        return count.value

    def read_reply(self, size, timeout_ms):
        if (not self.sent or self.read >= MAX_READ_CALLS or size != PACKET_SIZE
                or size != self.packet_size or not 1 <= timeout_ms <= READ_BUDGET_MS):
            raise UsbFailure("USB_READ_DENIED")
        timeout = U32(timeout_ms)
        self.check(self.winusb.WinUsb_SetPipePolicy(self.usb, 0x82, 3, 4, c.byref(timeout)), "USB_TIMEOUT_POLICY")
        self.read += 1
        buffer, count = c.create_string_buffer(size), U32()
        try:
            self.check(self.winusb.WinUsb_ReadPipe(self.usb, 0x82, buffer, size, c.byref(count), None), "USB_READ")
            if count.value > size:
                raise UsbFailure("USB_REPLY_LENGTH")
            return buffer.raw[:count.value]
        finally:
            c.memset(buffer, 0, size)


def attempt_once(transport, token, clock=time.monotonic):
    result = {
        "observedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": "用户指定的第一代 X1D，VID 2756 / PID 0002",
        "firmwareVersion": None, "stage": "open", "ok": False,
        "applicationRequestsSubmitted": 0, "writeCompleted": False,
        "readCalls": 0, "replyMatched": False, "replyBytes": 0,
        "lateFarmRepliesDiscarded": 0, "maxReadCalls": MAX_READ_CALLS,
        "writeTimeoutMs": 2000, "readBudgetMs": READ_BUDGET_MS,
        "busMethodTimeoutMs": 2000, "command": COMMAND, "correlationToken": token,
        "rawReplySaved": False,
        "knownCameraSideEffects": ["正常 USB/UART/D-Bus 通信及原有日志",
            "若 sutest 尚未运行，原厂 D-Bus 激活可能执行 modprobe i2c-dev 并启动 sutest-daemon",
            "启动一个 /bin/sh -c 固定命令；exec 替换为 busctl；注册临时系统 D-Bus 客户端",
            "禁止自动启动 FARM、禁止交互授权；查询只读取 Linux 已有缓存"],
        "limits": ["2 秒仅为 D-Bus 方法调用时限，不是整个相机进程生命周期保证",
            "主机超时不取消机内命令、排队或可能的迟到回复", "缓存没有已验证的新鲜度，0 不证明 Demo 关闭"],
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
            result["stage"] = "validate-reply"
            if is_late_farm_reply(packet) and result["lateFarmRepliesDiscarded"] == 0:
                result["lateFarmRepliesDiscarded"] = 1
                continue
            result["value"] = asdict(parse_reply(packet, token))
            result["replyMatched"] = True
            result["ok"], result["stage"] = True, "complete"
            break
        else:
            raise UsbFailure("USB_NO_MATCHED_REPLY")
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
        result["elapsedMs"] = round((clock() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-authorized-once", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.run_authorized_once or args.report is None:
        parser.error("需要本次已有授权及唯一结果文件；没有打开设备")
    if Path.cwd().resolve() != ROOT:
        parser.error("必须在当前 Hasselblad local 工作区运行")
    names = (*FROZEN_HOST_FILES, "read_sutest_ram_once.py", "sutest_ram_contract.py")
    hashes = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() for name in names}
    if any(hashes[name] != expected for name, expected in FROZEN_HOST_FILES.items()):
        parser.error("既有主机接口层发生变化；没有打开设备")
    destination = args.report.resolve()
    destination.relative_to((ROOT / "x1d/research/validation/hardware").resolve())
    if not destination.parent.is_dir():
        parser.error("既有证据目录不存在；没有打开设备")
    token = secrets.randbelow(0xffffffff) + 1
    with destination.open("x", encoding="utf-8") as output:
        result = attempt_once(SutestRamWinUsb(token), token)
        result["sourceFilesSha256"] = hashes
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
