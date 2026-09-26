"""固定 X1D 1.25.0 的观察区只读预检；导入无设备访问，不含写入入口。"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "x1d/tools"))
import read_usb_link_once as usb

FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
HOST_SHA = "8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3"
CONTRACT_SHA = "80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84"
AF_IDLE = 0x6bb46c
PL_FLAG_WORD = 0x2b20cc
AF_R2_STATE = 0x2b3aa0
PADDING = tuple(range(0x2b26a0, 0x2b2800, 4)) + tuple(range(0x2b3e80, 0x2b4000, 4))
HOOK_LINE = tuple(range(0x214100, 0x214120, 4))
READ_SET = frozenset(PADDING + HOOK_LINE + (AF_IDLE, PL_FLAG_WORD,
                                         AF_R2_STATE, AF_R2_STATE + 4, AF_R2_STATE + 8))
VERSION = ("827fa74", "c9bb91d", "abad48d")


def request(kind, address=None, size=512):
    if type(size) is not int or size not in (512, 1024):
        raise ValueError("unreviewed packet size")
    if kind == "version" and address is None:
        body = bytes.fromhex("0d000801")
    elif kind == "read" and type(address) is int and address in READ_SET:
        body = bytes.fromhex("f4000801") + struct.pack("<I", address)
    else:
        raise ValueError("outside fixed read-only scope")
    return body + bytes(size - len(body))


def reply(kind, data, size):
    if type(data) is not bytes or len(data) != size or size not in (512, 1024):
        raise ValueError("reply size")
    if kind == "version":
        if data[:4] != bytes.fromhex("0e000108"):
            raise ValueError("version reply header")
        values = tuple(data[a:a + 64].split(b"\0", 1)[0].decode("ascii") for a in (4, 68, 132))
        if values != VERSION:
            raise ValueError("fixed FARM version mismatch")
        return values
    if kind != "read" or data[:4] != bytes.fromhex("f5000108") or data[8] != 0:
        raise ValueError("read reply mismatch")
    return struct.unpack_from("<I", data, 4)[0]


class FixedReadUsb(usb.NativeWinUsb):
    def __init__(self, kind, address):
        request(kind, address)
        self.kind, self.address = kind, address
        super().__init__()

    def write_query(self, size):
        if not self.prepared or self.sent or size != self.packet_size:
            raise usb.UsbFailure("USB_REQUEST_DENIED")
        packet = request(self.kind, self.address, size)
        buf, count = usb.c.create_string_buffer(packet, size), usb.U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buf, size, usb.c.byref(count), None), "USB_WRITE")
        return count.value


class FixedReadIO:
    def __init__(self):
        self.operations = []
        self.failed = False

    def exchange(self, kind, address=None):
        request(kind, address)
        if self.failed or len(self.operations) >= 210:
            raise RuntimeError("read session closed or budget exceeded")
        row = {"kind": kind, "address": address, "ok": False, "requests": 0}
        self.operations.append(row)
        transport = FixedReadUsb(kind, address)
        try:
            size = usb.validate_interface(transport.open())
            transport.prepare()
            if transport.write_query(size) != size:
                raise RuntimeError("short request write")
            value = reply(kind, transport.read_reply(size), size)
            row.update(ok=True, value=value)
            return value
        except Exception:
            self.failed = True
            raise
        finally:
            row["requests"] = int(transport.sent)
            row["closure"] = transport.close()
            if not all(row["closure"].values()):
                self.failed = True
                row["ok"] = False
                raise RuntimeError("USB handle closure failed")


def run_authorized_once(farm, destination):
    """调用前须已有本轮开机/空闲/独占确认；不自动重试，不启动 PL。"""
    if Path.cwd().resolve() != ROOT.resolve() or hashlib.sha256(farm).hexdigest() != FARM_SHA:
        raise RuntimeError("workspace or source mismatch")
    for name, expected in (("read_usb_link_once.py", HOST_SHA), ("usb_diagnostic_contract.py", CONTRACT_SHA)):
        if hashlib.sha256((ROOT / "x1d/tools" / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("host interface changed")
    destination = Path(destination).resolve()
    if destination.parent != (HERE / "build").resolve():
        raise RuntimeError("report outside module build directory")
    for address in PADDING:
        if struct.unpack_from("<I", farm, address - 0x100000)[0] != 0:
            raise RuntimeError("official padding is not zero")
    io = FixedReadIO()
    result = {"observed_at": datetime.now(timezone.utc).isoformat(), "ok": False,
              "purpose": "read-only split observation-arena preflight with installed AF R2",
              "farm_sha256": FARM_SHA, "camera_memory_writes": 0, "hardware_register_reads": 0,
              "installation_performed": False, "operations": io.operations}
    with destination.open("x", encoding="utf-8") as out:
        try:
            result["version"] = io.exchange("version")
            if io.exchange("read", AF_IDLE) & 255:
                raise RuntimeError("AF is active")
            state = [io.exchange("read", AF_R2_STATE + offset) for offset in (0, 4, 8)]
            if state != [0x41464f57, 3, 2]:
                raise RuntimeError("installed AF R2 state does not match")
            result["af_r2_state_header"] = state
            result["pl_software_flag_word"] = io.exchange("read", PL_FLAG_WORD)
            for address in HOOK_LINE:
                if io.exchange("read", address) != struct.unpack_from("<I", farm, address - 0x100000)[0]:
                    raise RuntimeError("SENSORIF hook cache line differs")
            for address in PADDING:
                if io.exchange("read", address) != 0:
                    raise RuntimeError("observation padding is occupied")
            if io.exchange("read", AF_IDLE) & 255:
                raise RuntimeError("AF became active")
            result.update(ok=True, source_hook_line_matches=True, split_padding_zero=True,
                          ranges=[[0x2b26a0, 0x2b2800], [0x2b3e80, 0x2b4000]])
        except Exception as error:
            result["error"] = type(error).__name__ + ": " + str(error)
        finally:
            result["requests"] = sum(row["requests"] for row in io.operations)
            result["all_handles_closed"] = all(bool(row.get("closure")) and all(row["closure"].values()) for row in io.operations)
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
    return result
