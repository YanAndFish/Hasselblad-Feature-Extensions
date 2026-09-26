"""获授权后执行一次固定 X1D FX3 链路状态读取。默认无设备访问。"""
from __future__ import annotations

import argparse
import ctypes as c
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import time
import uuid

from usb_diagnostic_contract import PACKET_SIZES, build_fx3_link_query, parse_fx3_link_reply

ROOT = Path(__file__).resolve().parents[2]
INTERFACE_GUID = "CC135687-5267-4313-B0C7-C344609D6EF0"
TIMEOUT_MS = 2000
U8, U16, U32, BOOL, HANDLE = c.c_ubyte, c.c_uint16, c.c_uint32, c.c_int, c.c_void_p


class GUID(c.Structure):
    _fields_ = [("bytes", U8 * 16)]


class InterfaceData(c.Structure):
    _fields_ = [("size", U32), ("guid", GUID), ("flags", U32), ("reserved", HANDLE)]


class UsbInterface(c.Structure):
    _pack_ = 1
    _fields_ = [(name, U8) for name in ("length", "kind", "number", "alternate", "endpoints", "class_id", "subclass", "protocol", "string_index")]


class PipeInfo(c.Structure):
    _fields_ = [("type", U32), ("id", U8), ("packet_size", U16), ("interval", U8)]


class UsbFailure(Exception):
    def __init__(self, code, win32=0):
        super().__init__(code)
        self.code, self.win32 = code, win32


def is_x1d_interface_path(path):
    return (path.lower().startswith(r"\\?\usb#vid_2756&pid_0002#")
            and path.lower().endswith("#{" + INTERFACE_GUID.lower() + "}"))


def validate_interface(info):
    pipes = info["pipes"]
    if (info["alternate"] != 0 or info["class"] != 255 or info["subclass"] != 0
            or info["protocol"] != 0 or len(pipes) != 4
            or sorted(p["id"] for p in pipes) != [1, 2, 129, 130]
            or any(p["type"] != 2 for p in pipes)):
        raise UsbFailure("USB_INTERFACE_MISMATCH")
    sizes = {p["maximumPacketSize"] for p in pipes}
    if len(sizes) != 1 or next(iter(sizes)) not in PACKET_SIZES:
        raise UsbFailure("USB_PACKET_SIZE_MISMATCH")
    size = next(iter(sizes))
    if info["number"] != (2 if size == 64 else 0):
        raise UsbFailure("USB_INTERFACE_NUMBER_MISMATCH")
    return size


def attempt_once(transport):
    result = {"observedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
              "target": "用户本轮指定的第一代 X1D，VID 2756 / PID 0002",
              "firmwareVersion": None, "stage": "open", "ok": False,
              "applicationRequestsSubmitted": 0, "writeCompleted": False,
              "readCalls": 0, "replyMatched": False, "replyBytes": 0,
              "pipeTimeoutMs": TIMEOUT_MS, "rawReplySaved": False,
              "knownCameraSideEffect": "原厂状态 handler 生成 usbif_trace_event，目标 iMX；不保证实际已送达或持久化。",
              "initialization": "CreateFile + WinUsb_Initialize 读取描述符并初始化主机接口策略；查询当前接口/端点；仅设置主机传输时限。"}
    started = time.monotonic()
    try:
        info = transport.open()
        result["interface"] = info
        result["stage"] = "validate-interface"
        packet_size = validate_interface(info)
        result["packetSize"] = packet_size
        result["controlOut"], result["controlIn"] = "0x02", "0x82"
        result["stage"] = "host-timeout-policy"
        transport.prepare()
        result["stage"] = "write-query"
        result["applicationRequestsSubmitted"] = 1
        transferred = transport.write_query(packet_size)
        result["writeReportedBytes"] = transferred
        if transferred != packet_size:
            raise UsbFailure("USB_SHORT_WRITE")
        result["writeCompleted"] = True
        result["stage"] = "read-reply"
        result["readCalls"] = 1
        packet = transport.read_reply(packet_size)
        result["replyBytes"] = len(packet)
        result["stage"] = "validate-reply"
        result["value"] = asdict(parse_fx3_link_reply(packet, packet_size))
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


class NativeWinUsb:
    def __init__(self):
        assert c.sizeof(HANDLE) == 8 and c.sizeof(InterfaceData) == 32
        assert c.sizeof(UsbInterface) == 9 and c.sizeof(PipeInfo) == 12
        self.file, self.usb = None, HANDLE()
        self.opened = self.initialized = self.sent = self.read = False
        self.prepared = False
        self.packet_size = None
        self.enum_closed = True
        base = Path("C:/Windows/System32")
        self.setup = c.WinDLL(str(base / "setupapi.dll"), use_last_error=True)
        self.kernel = c.WinDLL(str(base / "kernel32.dll"), use_last_error=True)
        self.winusb = c.WinDLL(str(base / "winusb.dll"), use_last_error=True)
        bindings = [
            (self.setup, "SetupDiGetClassDevsW", HANDLE, [c.POINTER(GUID), c.c_wchar_p, HANDLE, U32]),
            (self.setup, "SetupDiEnumDeviceInterfaces", BOOL, [HANDLE, HANDLE, c.POINTER(GUID), U32, c.POINTER(InterfaceData)]),
            (self.setup, "SetupDiGetDeviceInterfaceDetailW", BOOL, [HANDLE, c.POINTER(InterfaceData), HANDLE, U32, c.POINTER(U32), HANDLE]),
            (self.setup, "SetupDiDestroyDeviceInfoList", BOOL, [HANDLE]),
            (self.kernel, "CreateFileW", HANDLE, [c.c_wchar_p, U32, U32, HANDLE, U32, U32, HANDLE]),
            (self.kernel, "CloseHandle", BOOL, [HANDLE]),
            (self.winusb, "WinUsb_Initialize", BOOL, [HANDLE, c.POINTER(HANDLE)]),
            (self.winusb, "WinUsb_Free", BOOL, [HANDLE]),
            (self.winusb, "WinUsb_GetCurrentAlternateSetting", BOOL, [HANDLE, c.POINTER(U8)]),
            (self.winusb, "WinUsb_QueryInterfaceSettings", BOOL, [HANDLE, U8, c.POINTER(UsbInterface)]),
            (self.winusb, "WinUsb_QueryPipe", BOOL, [HANDLE, U8, U8, c.POINTER(PipeInfo)]),
            (self.winusb, "WinUsb_GetPipePolicy", BOOL, [HANDLE, U8, U32, c.POINTER(U32), HANDLE]),
            (self.winusb, "WinUsb_SetPipePolicy", BOOL, [HANDLE, U8, U32, U32, HANDLE]),
            (self.winusb, "WinUsb_WritePipe", BOOL, [HANDLE, U8, HANDLE, U32, c.POINTER(U32), HANDLE]),
            (self.winusb, "WinUsb_ReadPipe", BOOL, [HANDLE, U8, HANDLE, U32, c.POINTER(U32), HANDLE]),
        ]
        for library, name, result, arguments in bindings:
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments

    @staticmethod
    def check(ok, code):
        if not ok:
            raise UsbFailure(code, c.get_last_error())

    def _enumerate(self):
        guid = GUID.from_buffer_copy(uuid.UUID(INTERFACE_GUID).bytes_le)
        devices = self.setup.SetupDiGetClassDevsW(c.byref(guid), None, None, 0x12)
        if devices == c.c_void_p(-1).value:
            raise UsbFailure("USB_ENUMERATE", c.get_last_error())
        paths = []
        try:
            for index in range(128):
                item = InterfaceData()
                item.size = c.sizeof(item)
                if not self.setup.SetupDiEnumDeviceInterfaces(devices, None, c.byref(guid), index, c.byref(item)):
                    error = c.get_last_error()
                    if error == 259:
                        return paths
                    raise UsbFailure("USB_ENUMERATE", error)
                needed = U32()
                self.setup.SetupDiGetDeviceInterfaceDetailW(devices, c.byref(item), None, 0, c.byref(needed), None)
                if needed.value < 8 or needed.value > 4096:
                    raise UsbFailure("USB_ENUMERATE_LENGTH")
                buffer = c.create_string_buffer(needed.value)
                U32.from_buffer(buffer).value = 8
                self.check(self.setup.SetupDiGetDeviceInterfaceDetailW(devices, c.byref(item), buffer, needed, c.byref(needed), None), "USB_ENUMERATE")
                path = c.wstring_at(c.addressof(buffer) + 4, (needed.value - 4) // 2).split("\0", 1)[0]
                if is_x1d_interface_path(path):
                    paths.append(path)
            raise UsbFailure("USB_ENUMERATE_LIMIT")
        finally:
            self.enum_closed = bool(self.setup.SetupDiDestroyDeviceInfoList(devices))

    def open(self):
        paths = self._enumerate()
        if not self.enum_closed:
            raise UsbFailure("USB_ENUMERATE_CLOSE")
        if len(paths) != 1:
            raise UsbFailure("USB_NOT_PRESENT" if not paths else "USB_AMBIGUOUS")
        # 独占句柄。设备路径只留在内存，不写入异常、结果或日志。
        self.file = self.kernel.CreateFileW(paths[0], 0xc0000000, 0, None, 3, 0x40000080, None)
        if self.file == c.c_void_p(-1).value:
            self.file = None
            raise UsbFailure("USB_OPEN", c.get_last_error())
        self.opened = True
        self.check(self.winusb.WinUsb_Initialize(self.file, c.byref(self.usb)), "USB_INITIALIZE")
        self.initialized = True
        alternate = U8()
        self.check(self.winusb.WinUsb_GetCurrentAlternateSetting(self.usb, c.byref(alternate)), "USB_ALTERNATE")
        if alternate.value != 0:
            raise UsbFailure("USB_ALTERNATE_MISMATCH")
        interface = UsbInterface()
        self.check(self.winusb.WinUsb_QueryInterfaceSettings(self.usb, alternate, c.byref(interface)), "USB_INTERFACE")
        if interface.length != 9 or interface.kind != 4 or interface.endpoints != 4:
            raise UsbFailure("USB_INTERFACE_MISMATCH")
        info = {"number": interface.number, "alternate": interface.alternate, "class": interface.class_id,
                "subclass": interface.subclass, "protocol": interface.protocol, "pipes": []}
        for index in range(4):
            pipe = PipeInfo()
            self.check(self.winusb.WinUsb_QueryPipe(self.usb, alternate, index, c.byref(pipe)), "USB_PIPE")
            info["pipes"].append({"id": pipe.id, "type": pipe.type, "maximumPacketSize": pipe.packet_size})
        self.packet_size = validate_interface(info)
        return info

    def prepare(self):
        if self.packet_size not in PACKET_SIZES:
            raise UsbFailure("USB_NOT_VALIDATED")
        # 不启用自动清除 stall、恢复时复位端点或额外零长包；只读取这些主机策略。
        for pipe, policy in ((0x82, 2), (0x82, 9), (2, 9), (2, 1)):
            length, value = U32(1), U8()
            self.check(self.winusb.WinUsb_GetPipePolicy(self.usb, pipe, policy, c.byref(length), c.byref(value)), "USB_POLICY_READ")
            if length.value != 1 or value.value != 0:
                raise UsbFailure("USB_POLICY_UNREVIEWED")
        timeout = U32(TIMEOUT_MS)
        for pipe in (2, 0x82):
            self.check(self.winusb.WinUsb_SetPipePolicy(self.usb, pipe, 3, 4, c.byref(timeout)), "USB_TIMEOUT_POLICY")
        self.prepared = True

    def write_query(self, size):
        if not self.prepared or self.sent or size != self.packet_size:
            raise UsbFailure("USB_REQUEST_DENIED")
        packet = build_fx3_link_query(size)
        buffer = c.create_string_buffer(packet, size)
        count = U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buffer, size, c.byref(count), None), "USB_WRITE")
        return count.value

    def read_reply(self, size):
        if not self.sent or self.read or size != self.packet_size:
            raise UsbFailure("USB_READ_DENIED")
        self.read = True
        buffer, count = c.create_string_buffer(size), U32()
        try:
            self.check(self.winusb.WinUsb_ReadPipe(self.usb, 0x82, buffer, size, c.byref(count), None), "USB_READ")
            if count.value > size:
                raise UsbFailure("USB_REPLY_LENGTH")
            return buffer.raw[:count.value]
        finally:
            c.memset(buffer, 0, size)

    def close(self):
        result = {"enumerationClosed": self.enum_closed, "winUsbFreed": True, "deviceHandleClosed": True}
        if self.usb.value:
            result["winUsbFreed"] = bool(self.winusb.WinUsb_Free(self.usb))
            self.usb = HANDLE()
        if self.file:
            result["deviceHandleClosed"] = bool(self.kernel.CloseHandle(self.file))
            self.file = None
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-authorized-once", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.run_authorized_once or args.report is None:
        parser.error("需要本轮明确授权及唯一结果文件；没有打开设备")
    if Path.cwd().resolve() != ROOT:
        parser.error("必须在当前 Hasselblad local 工作区运行")
    destination = args.report.resolve()
    destination.relative_to((ROOT / "x1d/research/validation/hardware").resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 同一证据文件仅允许一次调用；失败也保留，防止用同一批次自动重试。
    with destination.open("x", encoding="utf-8") as output:
        result = attempt_once(NativeWinUsb())
        result["sourceFilesSha256"] = {}
        import hashlib
        for filename in ("read_usb_link_once.py", "usb_diagnostic_contract.py"):
            result["sourceFilesSha256"][filename] = hashlib.sha256((Path(__file__).parent / filename).read_bytes()).hexdigest()
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
