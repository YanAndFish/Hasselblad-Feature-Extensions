"""本次临时安装使用的顺序会话；导入不访问设备，不触发拍摄或试闪。

命令由当前安装步骤明确提供；一次发送后有歧义即锁住本会话，不自动重发。
所有主机证据限定本模块 build，设备输出不包含设备路径/序列号/照片信息。
"""
import ctypes as c
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
assert Path.cwd().resolve() == ROOT
sys.path.insert(0, str(ROOT / "x1d/tools"))
sys.path.insert(0, str(ROOT / ".research-cache/x1d-1.25.0/python"))
from read_usb_link_once import NativeWinUsb, UsbFailure, U32, validate_interface
from sutest_ram_contract import _reviewed_helpers, REQUEST_HEADER, RESPONSE_HEADER


class CommandUsb(NativeWinUsb):
    def __init__(self, packet):
        self.packet = packet
        super().__init__()

    def write_query(self, size):
        if not self.prepared or self.sent or size != 512 or self.packet_size != 512:
            raise UsbFailure("USB_REQUEST_DENIED")
        buffer, count = c.create_string_buffer(self.packet, size), U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buffer, size, c.byref(count), None), "USB_WRITE")
        return count.value

    def read_with_timeout(self, timeout_ms):
        timeout = U32(timeout_ms)
        self.check(self.winusb.WinUsb_SetPipePolicy(self.usb, 0x82, 3, 4, c.byref(timeout)), "USB_TIMEOUT_POLICY")
        buffer, count = c.create_string_buffer(512), U32()
        try:
            self.check(self.winusb.WinUsb_ReadPipe(self.usb, 0x82, buffer, 512, c.byref(count), None), "USB_READ")
            return buffer.raw[:count.value]
        finally:
            c.memset(buffer, 0, 512)


class Session:
    def __init__(self, evidence_name="hardware-session.json"):
        self.failed = False
        self.entries = []
        if Path(evidence_name).name!=evidence_name or not evidence_name.endswith(".json"):
            raise ValueError("Invalid session evidence name")
        self.output = HERE / "build/mechanical-sync-candidate" / evidence_name
        if self.output.exists():
            raise RuntimeError("Do not overwrite an existing hardware session")
        for name, digest in (("read_usb_link_once.py", "8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3"),
                             ("usb_diagnostic_contract.py", "80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84")):
            if hashlib.sha256((ROOT / "x1d/tools" / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("USB transport source changed")

    def command(self, label, command, timeout_ms=30000):
        if self.failed or not 1 <= timeout_ms <= 45000:
            raise RuntimeError("Session stopped or invalid timeout")
        encoded = command.encode("ascii")
        if not 1 <= len(encoded) <= 231 or b"\0" in encoded or b"\n" in encoded:
            raise ValueError("Command outside reviewed framing bounds")
        make_request, crc16 = _reviewed_helpers()
        token = secrets.randbelow(0xFFFFFFFF) + 1
        packet = bytearray(make_request(command))
        if len(packet) != 257 or packet[:5] != REQUEST_HEADER:
            raise ValueError("Reviewed framing mismatch")
        struct.pack_into("<I", packet, 13, token)
        assert struct.unpack_from("<I", packet, 17)[0] == crc16(packet[21:257])
        packet = bytes(packet) + bytes(512 - len(packet))
        entry = {"label": label, "command": command, "at": datetime.now(timezone.utc).isoformat(),
                 "submitted": 0, "read_calls": 0, "matched": False, "closed": False}
        transport = CommandUsb(packet)
        result = None
        try:
            if validate_interface(transport.open()) != 512:
                raise RuntimeError("Unexpected USB packet size")
            transport.prepare()
            if transport.write_query(512) != 512:
                raise RuntimeError("Short USB write")
            deadline = time.monotonic() + timeout_ms / 1000
            for _ in range(2):
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining <= 0:
                    raise RuntimeError("Reply deadline")
                raw = transport.read_with_timeout(remaining)
                entry["read_calls"] += 1
                if len(raw) != 512 or raw[:5] != RESPONSE_HEADER:
                    raise RuntimeError("Reply route or length mismatch")
                body = raw[5:257]
                kind, operation, echoed, checksum, exit_code = struct.unpack_from("<5I", body)
                if kind != 52 or operation != 0 or checksum != crc16(body[16:]):
                    raise RuntimeError("Reply envelope mismatch")
                if echoed != token:
                    continue
                output = body[20:].split(b"\0", 1)[0].decode("ascii")
                entry.update(matched=True, exit_code=exit_code, output=output)
                result = entry
                if exit_code:
                    raise RuntimeError("Camera command failed: " + label)
                break
            if result is None:
                raise RuntimeError("No matching reply")
        except Exception as error:
            self.failed = True
            entry["error"] = type(error).__name__
            if isinstance(error, UsbFailure):
                entry["usb_error"], entry["win32"] = error.code, error.win32
            raise
        finally:
            entry["submitted"] = int(transport.sent)
            entry["closed"] = all(transport.close().values())
            if not entry["closed"]:
                self.failed = True
            self.entries.append(entry)
            self.output.write_text(json.dumps({"failed": self.failed, "entries": self.entries,
                "agentFlashTrials": 0, "cameraShotsTriggered": 0}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not entry["closed"]:
            raise RuntimeError("USB closure failed")
        return {k: entry[k] for k in ("label", "exit_code", "output", "closed")}
