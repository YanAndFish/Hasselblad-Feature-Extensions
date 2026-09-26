"""固定分段 GFP2 候选的临时装入/解除；导入不访问设备，不触发拍摄。"""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "research"))
import farm_probe_preflight as pre
usb = pre.usb

BASE, DESC = 0x2b2800, 0x2b2820
CB, ARG, ORIG_CB, ORIG_ARG, NOOP = 0x2a5074, 0x2a5078, 0x109304, 0x6da728, 0x1009d4
CLEAN, INVALIDATE, CLEAN_RANGE, INVALIDATE_RANGE = 0x10a2d0, 0x10a310, 0x10a270, 0x10a354
SGIR, SELF15 = 0xf8f01f00, 0x0200000f
HOOK, OLD_HOOK, ENTRY, RECORD = 0x214110, 0xe3013990, 0x2b3e80, 0x2b3f58
NEW_HOOK = 0xea000000 | (((ENTRY - HOOK - 8) // 4) & 0xffffff)
PROBE_MAGIC = 0xafaf2026
PROBE = bytes.fromhex("261002e3af1f4ae3001080e51eff2fe1")
THUNK = struct.pack("<7I", 0xe92d4010, 0xe1a04000, 0xe8940007, 0xe12fff32, 0xe3a00001, 0xe584000c, 0xe8bd8010)
SEGMENTS = (
    (0x2b26a0, 236, "farm-sensor-split-head.bin", "9a42ab4ce6758c06cdcea96382e4fd240b5f6504d705f75a63587c3730f2f41a"),
    (0x2b3e80, 304, "farm-sensor-split-tail.bin", "b05ecbbe73c9aebf9f0189aaa56d5bf531261a667d4995c92571bf5f2e439efa"),
)
IRQ_GUARDS = {
    0x2ad78c: (0xffffffff, 0x2a4ffc), 0x6da728: (0xffffffff, 0x2a4ff0),
    0x6da72c: (0xffffffff, 0x11111111), CB: (0xffffffff, ORIG_CB), ARG: (0xffffffff, ORIG_ARG),
    0xf8f01000: (1, 1), 0xf8f00100: (9, 1), 0xf8f01100: (0x8000, 0x8000),
    0xf8f01200: (0x8000, 0), 0xf8f01300: (0x8000, 0),
    0xf8f0140c: (0xff000000, 0xa0000000), 0xf8f01080: (0x8000, 0),
    0x1009d4: (0xffffffff, 0xe12fff1e),
}
CACHE_CODE = tuple(range(0x10a270, 0x10a3ac, 4)) + tuple(range(0x10acac, 0x10acb8, 4))
READ_SET = pre.READ_SET | frozenset(IRQ_GUARDS) | frozenset(CACHE_CODE) | frozenset(range(BASE, BASE + 64, 4))


def load_payloads():
    outputs = []
    for start, length, name, digest in SEGMENTS:
        data = (HERE / "build" / name).read_bytes()
        if len(data) != length or hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError("fixed split payload changed")
        outputs.append((start, data))
    return outputs


def allowed_writes():
    result = {CB: {ORIG_CB, NOOP, CLEAN, INVALIDATE, BASE},
              ARG: {ORIG_ARG, BASE, DESC}, SGIR: {SELF15}, HOOK: {OLD_HOOK, NEW_HOOK}}
    for a in range(BASE, BASE + 64, 4):
        result[a] = {0}
    for start, data in [(BASE, PROBE), (BASE, THUNK)] + load_payloads():
        for off in range(0, len(data), 4):
            result.setdefault(start + off, {0}).add(struct.unpack_from("<I", data, off)[0])
    result[DESC].update(start for start, _, _, _ in SEGMENTS)
    result[DESC].add(HOOK & ~31)
    result[DESC + 4].update((236, 304, 32))
    result[DESC + 8].update((CLEAN_RANGE, INVALIDATE_RANGE))
    result[DESC + 12].add(1)
    result[RECORD + 4].add(1)
    return result


WRITE_VALUES = allowed_writes()


def request(kind, address=None, value=None, size=512):
    if size not in (512, 1024) or type(size) is not int:
        raise ValueError("packet size")
    if kind == "version" and address is None and value is None:
        body = bytes.fromhex("0d000801")
    elif kind == "read" and type(address) is int and address in READ_SET and value is None:
        body = bytes.fromhex("f4000801") + struct.pack("<I", address)
    elif kind == "write" and type(address) is int and type(value) is int and value in WRITE_VALUES.get(address, ()):
        body = bytes.fromhex("f2000801") + struct.pack("<II", address, value)
    else:
        raise ValueError("outside fixed loader scope")
    return body + bytes(size - len(body))


def reply(kind, data, size):
    if kind != "write":
        return pre.reply(kind, data, size)
    if type(data) is not bytes or len(data) != size or data[:5] != bytes.fromhex("f300010800"):
        raise ValueError("write response mismatch")
    return 0


class FixedUsb(usb.NativeWinUsb):
    def __init__(self, kind, address, value):
        request(kind, address, value)
        self.arguments = kind, address, value
        super().__init__()

    def write_query(self, size):
        if not self.prepared or self.sent or size != self.packet_size:
            raise usb.UsbFailure("USB_REQUEST_DENIED")
        packet = request(*self.arguments, size=size)
        buf, count = usb.c.create_string_buffer(packet, size), usb.U32()
        self.sent = True
        self.check(self.winusb.WinUsb_WritePipe(self.usb, 2, buf, size, usb.c.byref(count), None), "USB_WRITE")
        return count.value


class FixedIO:
    def __init__(self):
        self.requests, self.writes = 0, 0
        self.closed, self.failed = True, False

    def exchange(self, kind, address=None, value=None):
        request(kind, address, value)
        if self.failed or self.requests >= 3000:
            raise RuntimeError("session stopped; no retry after ambiguous transport")
        transport = FixedUsb(kind, address, value)
        try:
            size = usb.validate_interface(transport.open())
            transport.prepare()
            count = transport.write_query(size)
            if count != size:
                raise RuntimeError("short write")
            return reply(kind, transport.read_reply(size), size)
        except Exception:
            self.failed = True
            raise
        finally:
            self.requests += int(transport.sent)
            self.writes += int(transport.sent and kind == "write")
            self.closed = all(transport.close().values())
            if not self.closed:
                self.failed = True
                raise RuntimeError("USB closure failed")

    def read(self, address):
        return self.exchange("read", address)


class Loader:
    def __init__(self, io=None):
        self.io = io or FixedIO()
        self.record, self.path = {}, None
        self.saved = False

    def save(self):
        if not self.path or self.path.parent != (HERE / "build").resolve():
            raise RuntimeError("recovery record outside module build")
        self.record.update(requests=self.io.requests, writes=self.io.writes, all_handles_closed=self.io.closed)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(self.record, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)

    def prepare(self, farm, destination):
        if self.saved or Path.cwd().resolve() != ROOT.resolve() or hashlib.sha256(farm).hexdigest() != pre.FARM_SHA:
            raise RuntimeError("workspace/source mismatch")
        for name, digest in (("read_usb_link_once.py", pre.HOST_SHA), ("usb_diagnostic_contract.py", pre.CONTRACT_SHA)):
            if hashlib.sha256((ROOT / "x1d/tools" / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("host transport changed")
        self.io.exchange("version")
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF active")
        for off, expected in ((0, 0x41464f57), (4, 3), (8, 2)):
            if self.io.read(pre.AF_R2_STATE + off) != expected:
                raise RuntimeError("R2 state header mismatch")
        for address, (mask, expected) in IRQ_GUARDS.items():
            if self.io.read(address) & mask != expected:
                raise RuntimeError("cache/SGI guard mismatch at " + hex(address))
        for address in CACHE_CODE + pre.HOOK_LINE:
            if self.io.read(address) != struct.unpack_from("<I", farm, address - 0x100000)[0]:
                raise RuntimeError("fixed original code differs")
        for address in pre.PADDING + tuple(range(BASE, BASE + 64, 4)):
            if self.io.read(address) != 0:
                raise RuntimeError("padding/scratch occupied")
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF became active")
        self.path = Path(destination).resolve()
        if self.path.parent != (HERE / "build").resolve() or self.path.exists() or self.path.with_suffix(".tmp").exists():
            raise RuntimeError("recovery path invalid or already used")
        self.record = {"stage": "prepared", "created_at": datetime.now(timezone.utc).isoformat(),
                       "segments": SEGMENTS, "record_address": RECORD, "original_hook": OLD_HOOK,
                       "new_hook": NEW_HOOK, "original_callback": ORIG_CB, "original_argument": ORIG_ARG,
                       "padding_initially_zero": True, "installed": False, "armed": False,
                       "camera_shots_triggered": 0, "radio_submissions": 0, "probe_executed": False}
        self.save()
        self.saved = True

    def write(self, address, value):
        if not self.saved:
            raise RuntimeError("no saved recovery record")
        request("write", address, value)
        self.record["in_flight"] = {"address": address, "value": value}
        self.save()
        self.io.exchange("write", address, value)
        if address != SGIR and self.io.read(address) != value:
            raise RuntimeError("write readback mismatch")
        self.record["in_flight"] = None

    def quiet(self):
        self.write(CB, NOOP)
        if any(self.io.read(a) & 0x8000 for a in (0xf8f01200, 0xf8f01300)):
            raise RuntimeError("SGI not quiescent")

    def line_cache(self, function):
        if function not in (CLEAN, INVALIDATE):
            raise ValueError("cache function")
        self.quiet()
        self.write(ARG, BASE)
        self.write(CB, function)
        self.write(SGIR, SELF15)
        self.quiet()

    def restore_slot(self):
        self.quiet()
        self.write(ARG, ORIG_ARG)
        self.write(CB, ORIG_CB)

    def clean_scratch(self):
        self.quiet()
        for address in range(BASE, BASE + 64, 4):
            self.write(address, 0)
        self.line_cache(CLEAN)
        self.line_cache(INVALIDATE)
        self.restore_slot()

    def probe(self):
        self.record["stage"] = "cache_probe"
        self.save()
        self.quiet()
        for offset in range(0, len(PROBE), 4):
            self.write(BASE + offset, struct.unpack_from("<I", PROBE, offset)[0])
        self.write(DESC, 0)
        self.line_cache(CLEAN)
        self.line_cache(INVALIDATE)
        self.write(ARG, DESC)
        self.write(CB, BASE)
        self.write(SGIR, SELF15)
        self.quiet()
        if self.io.read(DESC) != PROBE_MAGIC:
            raise RuntimeError("independent RAM/cache probe did not execute")
        self.record["probe_executed"] = True
        self.clean_scratch()
        self.record["stage"] = "cache_probe_restored"
        self.save()

    def upload_thunk(self):
        self.quiet()
        for offset in range(0, len(THUNK), 4):
            self.write(BASE + offset, struct.unpack_from("<I", THUNK, offset)[0])
        self.line_cache(CLEAN)
        self.line_cache(INVALIDATE)

    def range_cache(self, start, size, function):
        if (start, size) not in ((0x2b26a0, 236), (0x2b3e80, 304), (HOOK & ~31, 32)) or function not in (CLEAN_RANGE, INVALIDATE_RANGE):
            raise ValueError("cache range outside fixed segments")
        self.quiet()
        for address, value in ((DESC, start), (DESC + 4, size), (DESC + 8, function), (DESC + 12, 0)):
            self.write(address, value)
        self.write(ARG, DESC)
        self.write(CB, BASE)
        self.write(SGIR, SELF15)
        self.quiet()
        if self.io.read(DESC + 12) != 1:
            raise RuntimeError("cache range did not complete")

    def sync_code(self, start, size):
        self.range_cache(start, size, CLEAN_RANGE)
        self.range_cache(start, size, INVALIDATE_RANGE)

    def install_disarmed(self):
        if not self.record.get("probe_executed") or self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("installation precondition")
        if self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG or any(self.io.read(a) for a in range(BASE, BASE + 64, 4)):
            raise RuntimeError("cache probe not restored")
        self.record["stage"] = "installing_disarmed"
        self.save()
        for start, data in load_payloads():
            for offset in range(0, len(data), 4):
                self.write(start + offset, struct.unpack_from("<I", data, offset)[0])
        self.upload_thunk()
        for start, length, _, _ in SEGMENTS:
            self.sync_code(start, length)
        if self.io.read(HOOK) != OLD_HOOK or self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("hook/AF state changed before activation")
        self.write(HOOK, NEW_HOOK)
        self.sync_code(HOOK & ~31, 32)
        self.clean_scratch()
        self.record.update(stage="installed_disarmed", installed=True)
        self.save()

    def arm_once(self):
        if not self.record.get("installed") or self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("arming precondition")
        if self.io.read(HOOK) != NEW_HOOK or self.io.read(RECORD) != 0x32504647 or self.io.read(RECORD + 8) & 1:
            raise RuntimeError("record/hook mismatch")
        self.write(RECORD + 4, 1)
        self.record.update(stage="armed_for_one_user_exposure", armed=True)
        self.save()

    def read_record(self):
        sequence_before = self.io.read(RECORD + 8)
        data = b"".join(struct.pack("<I", self.io.read(a)) for a in range(RECORD, RECORD + 88, 4))
        sequence_after = self.io.read(RECORD + 8)
        from farm_probe_record import parse_snapshot
        return parse_snapshot(data, sequence_before=sequence_before, sequence_after=sequence_after)

    def unhook(self):
        """恢复原入口；保留不再引用的代码，防止回收仍可能被保存的任务返回地址。"""
        self.write(RECORD + 4, 0)
        self.record["armed"] = False
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("wait for AF idle")
        self.record["stage"] = "unhooking"
        self.save()
        self.upload_thunk()
        self.write(HOOK, OLD_HOOK)
        self.sync_code(HOOK & ~31, 32)
        self.clean_scratch()
        if self.io.read(HOOK) != OLD_HOOK or self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG:
            raise RuntimeError("restoration readback mismatch")
        self.record.update(stage="original_hook_restored_payload_retained_until_restart", installed=False,
                           unreferenced_payload_retained=True, safe_to_overwrite_payload_without_restart=False)
        self.save()
