"""HFS1 固定候选的临时装入/解除。只占用约定的空白采集区与缓存临时区。
导入只读电脑文件，不发设备请求。保留 AF 独立区域；不允许覆盖仍驻留的旧引闪代码。
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm_probe_loader as common

HERE, ROOT, pre, usb = common.HERE, common.ROOT, common.pre, common.usb
BASE, DESC, CB, ARG = common.BASE, common.DESC, common.CB, common.ARG
ORIG_CB, ORIG_ARG, NOOP = common.ORIG_CB, common.ORIG_ARG, common.NOOP
CLEAN, INVALIDATE = common.CLEAN, common.INVALIDATE
CLEAN_RANGE, INVALIDATE_RANGE, SGIR, SELF15 = common.CLEAN_RANGE, common.INVALIDATE_RANGE, common.SGIR, common.SELF15
PROBE, PROBE_MAGIC, THUNK = common.PROBE, common.PROBE_MAGIC, common.THUNK
IRQ_GUARDS, CACHE_CODE = common.IRQ_GUARDS, common.CACHE_CODE
PAYLOAD_START, PAYLOAD_BYTES, RECORD, RECORD_SIZE = 2828416, 2716, 2830768, 364
PAYLOAD_SHA = 'c539658c060a38cfff89cd9fd66049fa6172ee2c2cbfdebaacdd0a2a867fa1c6'
MAGIC = 0x31534648
HOOK_ENTRIES = {2179228: 2828416, 2179340: 2828696, 2178656: 2828868, 2178808: 2828868, 2180068: 2828936, 1852288: 2829004, 1852504: 2829060, 1852660: 2829112}
ORIGINAL_HOOKS = {2179228: 3942683103, 2179340: 3942683075, 2178656: 3942683341, 2178808: 3942683303, 2180068: 3942682988, 1852288: 3808507536, 1852504: 3785371648, 1852660: 3818913793}
BRANCH_LINK = {2179228: True, 2179340: True, 2178656: True, 2178808: True, 2180068: True, 1852288: False, 1852504: False, 1852660: False}
NEW_HOOKS = {a: (0xEB000000 if BRANCH_LINK[a] else 0xEA000000) | (((target - a - 8) // 4) & 0xFFFFFF) for a, target in HOOK_ENTRIES.items()}
HOOK_LINES = tuple(sorted({p for a in HOOK_ENTRIES for p in range(a & ~31, (a & ~31) + 32, 4)}))
# 这两个原厂指令仅排除相同 SENSORIF 路径的旧观察钩子，不覆盖 AF。
ZERO_RANGES = ((PAYLOAD_START, PAYLOAD_START + PAYLOAD_BYTES), (BASE, BASE + 64))
ZERO_WORDS = tuple(sorted({a for start, end in ZERO_RANGES for a in range(start, end, 4)}))
READ_SET = frozenset(IRQ_GUARDS) | frozenset(CACHE_CODE + HOOK_LINES + (0x214110, 0x233c7c) + ZERO_WORDS + (pre.AF_IDLE,))
CACHE_RANGES = ((PAYLOAD_START, PAYLOAD_BYTES),) + tuple((a & ~31, 32) for a in HOOK_ENTRIES)


def payload():
    data = (HERE / "build/formal-sync-capture/target.bin").read_bytes()
    if len(data) != PAYLOAD_BYTES or hashlib.sha256(data).hexdigest() != PAYLOAD_SHA:
        raise RuntimeError("fixed HFS1 payload mismatch")
    return data


def allowed_writes():
    values = {CB: {ORIG_CB, NOOP, CLEAN, INVALIDATE, BASE}, ARG: {ORIG_ARG, BASE, DESC}, SGIR: {SELF15}}
    values.update({a: {ORIGINAL_HOOKS[a], NEW_HOOKS[a]} for a in HOOK_ENTRIES})
    for address in range(BASE, BASE + 64, 4):
        values[address] = {0}
    for start, data in ((BASE, PROBE), (BASE, THUNK), (PAYLOAD_START, payload())):
        for offset in range(0, len(data), 4):
            values.setdefault(start + offset, {0}).add(struct.unpack_from("<I", data, offset)[0])
    values[DESC].update(start for start, _ in CACHE_RANGES)
    values[DESC + 4].update(size for _, size in CACHE_RANGES)
    values[DESC + 8].update((CLEAN_RANGE, INVALIDATE_RANGE))
    values[DESC + 12].add(1)
    values[RECORD + 4].add(1)
    return values


WRITE_VALUES = allowed_writes()


def offline_ready():
    """当前 ARM、装载故障模型、FPGA 证据均绑定固定来源与当前字节。"""
    try:
        output=HERE/'build/formal-sync-capture'
        arm=json.loads((output/'validation.json').read_text(encoding='utf-8'))
        loader=json.loads((output/'loader-validation.json').read_text(encoding='utf-8'))
        if not arm.get('passed') or not loader.get('passed') or loader.get('tests',0)<7: return False
        if arm.get('payload_sha256')!=PAYLOAD_SHA or loader.get('payload_sha256')!=PAYLOAD_SHA: return False
        payload()
        for variant in ('simulation','target'):
            check=arm.get(variant,{})
            if not check.get('passed') or check.get('tests')!=12: return False
            if hashlib.sha256((output/(variant+'.elf')).read_bytes()).hexdigest()!=check['elf_sha256']: return False
        for report in (arm,loader):
            if not report.get('source_hashes'): return False
            for name,digest in report['source_hashes'].items():
                if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest: return False
        # 原厂 FPGA 的 bit6 清旧位、control3/7 启动语义未改，复用既有离线证明。
        for folder in ('farm-sync-capture','mechanical-sync-capture'):
            fpga=json.loads((HERE/'build'/folder/'fpga-validation.json').read_text(encoding='utf-8'))
            if not fpga.get('passed'): return False
            for name,digest in fpga['source_hashes'].items():
                if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest: return False
        return True
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        return False


def request(kind, address=None, value=None, size=512):
    if type(size) is not int or size not in (512, 1024):
        raise ValueError("packet size")
    if kind == "version" and address is None and value is None:
        body = bytes.fromhex("0d000801")
    elif kind == "read" and type(address) is int and address in READ_SET and value is None:
        body = bytes.fromhex("f4000801") + struct.pack("<I", address)
    elif kind == "write" and type(address) is int and type(value) is int and value in WRITE_VALUES.get(address, ()):
        body = bytes.fromhex("f2000801") + struct.pack("<II", address, value)
    else:
        raise ValueError("outside fixed HFS1 scope")
    return body + bytes(size - len(body))


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


class FixedIO(common.FixedIO):
    def exchange(self, kind, address=None, value=None):
        request(kind, address, value)
        if self.failed or self.requests >= 16000:
            raise RuntimeError("session stopped; no retry after ambiguous transport")
        transport = FixedUsb(kind, address, value)
        try:
            size = usb.validate_interface(transport.open())
            transport.prepare()
            if transport.write_query(size) != size:
                raise RuntimeError("short write")
            return common.reply(kind, transport.read_reply(size), size)
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


class Loader(common.Loader):
    """复用已验证的 SGI 暂存和缓存调用顺序，不修改共用模块的全局白名单。"""
    def __init__(self, io=None):
        super().__init__(io or FixedIO())

    def prepare(self, farm, destination):
        if isinstance(self.io, FixedIO) and not offline_ready():
            raise RuntimeError("offline verification no longer matches; no device requests sent")
        if self.saved or Path.cwd().resolve() != ROOT.resolve() or hashlib.sha256(farm).hexdigest() != pre.FARM_SHA:
            raise RuntimeError("workspace/source mismatch")
        for name, digest in (("read_usb_link_once.py", pre.HOST_SHA), ("usb_diagnostic_contract.py", pre.CONTRACT_SHA)):
            if hashlib.sha256((ROOT / "x1d/tools" / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("host transport changed")
        for a in ZERO_WORDS:
            if struct.unpack_from("<I", farm, a - 0x100000)[0] != 0:
                raise RuntimeError("official padding is not zero")
        self.io.exchange("version")
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF active")
        for address, (mask, expected) in IRQ_GUARDS.items():
            if self.io.read(address) & mask != expected:
                raise RuntimeError("cache/SGI guard mismatch at " + hex(address))
        for address in sorted(set(CACHE_CODE + HOOK_LINES + (0x214110, 0x233C7C))):
            if self.io.read(address) != struct.unpack_from("<I", farm, address - 0x100000)[0]:
                raise RuntimeError("original instruction differs at " + hex(address))
        for address in ZERO_WORDS:
            if self.io.read(address):
                raise RuntimeError("payload or previous observer still resident; manual restart required")
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF became active")
        self.path = Path(destination).resolve()
        if self.path.parent != (HERE / "build").resolve() or self.path.exists() or self.path.with_suffix(".tmp").exists():
            raise RuntimeError("recovery path invalid or already used")
        self.record = {"stage": "prepared", "created_at": datetime.now(timezone.utc).isoformat(),
                       "payload_sha256": PAYLOAD_SHA, "payload_base": PAYLOAD_START,
                       "payload_bytes": PAYLOAD_BYTES, "record_address": RECORD,
                       "original_hooks": ORIGINAL_HOOKS, "new_hooks": NEW_HOOKS,
                       "own_arena_initially_zero": True, "af_code_and_configuration_untouched": True,
                       "installed": False, "armed": False, "probe_executed": False,
                       "camera_shots_triggered": 0, "radio_submissions": 0}
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

    def range_cache(self, start, size, function):
        if (start, size) not in CACHE_RANGES or function not in (CLEAN_RANGE, INVALIDATE_RANGE):
            raise ValueError("cache range outside fixed HFS1 scope")
        self.quiet()
        for address, value in ((DESC, start), (DESC + 4, size), (DESC + 8, function), (DESC + 12, 0)):
            self.write(address, value)
        self.write(ARG, DESC)
        self.write(CB, BASE)
        self.write(SGIR, SELF15)
        self.quiet()
        if self.io.read(DESC + 12) != 1:
            raise RuntimeError("cache range did not complete")

    def install_disarmed(self):
        if not self.record.get("probe_executed") or self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("installation precondition")
        if self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG or any(self.io.read(a) for a in range(BASE, BASE + 64, 4)):
            raise RuntimeError("cache probe not restored")
        self.record["stage"] = "installing_disarmed"
        self.save()
        data = payload()
        for off in range(0, len(data), 4):
            self.write(PAYLOAD_START + off, struct.unpack_from("<I", data, off)[0])
        self.upload_thunk()
        self.sync_code(PAYLOAD_START, PAYLOAD_BYTES)
        for address, original in ORIGINAL_HOOKS.items():
            if self.io.read(address) != original or self.io.read(pre.AF_IDLE) & 255:
                raise RuntimeError("hook/AF state changed before activation")
            self.write(address, NEW_HOOKS[address])
            self.sync_code(address & ~31, 32)
        self.clean_scratch()
        self.record.update(stage="installed_disarmed", installed=True)
        self.verify(0)
        self.save()

    def verify(self, armed):
        if any(self.io.read(a) != value for a, value in NEW_HOOKS.items()):
            raise RuntimeError("hook mismatch")
        if self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG or any(self.io.read(a) for a in range(BASE, BASE + 64, 4)):
            raise RuntimeError("scratch/callback mismatch")
        data = payload()
        for off in range(0, RECORD - PAYLOAD_START, 4):
            if self.io.read(PAYLOAD_START + off) != struct.unpack_from("<I", data, off)[0]:
                raise RuntimeError("payload code mismatch")
        if self.io.read(RECORD) != MAGIC or self.io.read(RECORD + 4) != armed or self.io.read(RECORD + 8) != 0:
            raise RuntimeError("record mismatch")
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF state changed")

    def arm(self):
        if not self.record.get("installed"):
            raise RuntimeError("installation required")
        self.verify(0)
        self.write(RECORD + 4, 1)
        self.record.update(stage="armed_for_user_exposures", armed=True)
        self.save()

    def unhook(self):
        if not self.record.get("installed") or any(self.io.read(a) != value for a, value in NEW_HOOKS.items()):
            raise RuntimeError("recorded installation no longer matches")
        self.write(RECORD + 4, 0)
        self.record["armed"] = False
        if self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("wait for AF idle")
        self.record["stage"] = "unhooking"
        self.save()
        self.upload_thunk()
        for address, original in ORIGINAL_HOOKS.items():
            self.write(address, original)
            self.sync_code(address & ~31, 32)
        self.clean_scratch()
        if any(self.io.read(a) != value for a, value in ORIGINAL_HOOKS.items()):
            raise RuntimeError("hook restoration mismatch")
        if self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG:
            raise RuntimeError("callback restoration mismatch")
        self.record.update(stage="original_hooks_restored_payload_retained_until_restart", installed=False,
                           unreferenced_payload_retained=True, safe_to_overwrite_payload_without_restart=False)
        self.save()
