"""G7R1 第七条固定路径记录候选。先核对原厂代码、空白区和本轮 4500 速度基线。
导入只读电脑文件，不发设备请求；不得覆盖驻留 AF 或更改速度。
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
PAYLOAD_START, PAYLOAD_BYTES, RECORD, RECORD_SIZE = 0x2B2880, 520, 0x2B2A28, 96
PAYLOAD_SHA = "39ddc983149910674ff1a21b18566dff6ea14535852d1d053e3aa51c81ca3459"
MAGIC = 0x31523747
HOOK_ENTRIES = {0x1C4318: 0x2B2880, 0x1CE150: 0x2B28B4, 0x1C8874: 0x2B28E8, 0x1C8950: 0x2B291C,
                0x1C52A0: 0x2B2880, 0x1CA0B4: 0x2B2880}
ORIGINAL_HOOKS = {0x1C4318: 0xEBFFFD3C, 0x1CE150: 0xEBFFE80D, 0x1C8874: 0xEB01C048, 0x1C8950: 0xEBFFFDA1,
                  0x1C52A0: 0xEBFFF95A, 0x1CA0B4: 0xEBFFE5D5}
EXTRA_MARKERS = (0x1C52A0, 0x1CA0B4)
NEW_HOOKS = {a: 0xEB000000 | (((target - a - 8) // 4) & 0xFFFFFF) for a, target in HOOK_ENTRIES.items()}
HOOK_LINES = tuple(sorted({p for a in HOOK_ENTRIES for p in range(a & ~31, (a & ~31) + 32, 4)}))
AF_ENTRY_POINTS = (0x19BB94, 0x19B770, 0x1A4950, 0x1A0240, 0x1A0378,
                   0x1A1CD8, 0x1A1A98, 0x1A0EBC, 0x1A0498, 0x1A06E4,
                   0x19D19C, 0x1A02D8, 0x19BBEC, 0x1A1F64, 0x19DD70, 0x199CCC, 0x1A502C, 0x1A5318)
# 固定核对 R5 的全部入口及八段覆盖区；不导入或修改 AF 文件。
AF_EXTRA = (1686420, 1685360, 1722704, 1704512, 1704824, 1711320, 1710744, 1707708, 1705112, 1705700, 1687476, 1688336, 1689836, 1690656, 1692060, 1693128, 1693820, 1694156, 1685856, 1891244, 1875720, 2221692, 2296152, 1873428, 1874228, 2035308, 1672988, 1712092, 2179344, 2309244)
AF_OVERLAYS = ((1687480, 1688148), (1688340, 1689540), (1689840, 1690380), (1690660, 1691264), (1692064, 1692768), (1693132, 1693640), (1693824, 1694096), (1694160, 1694780))
AF_CODE = tuple(sorted({p for a in AF_ENTRY_POINTS + AF_EXTRA for p in range(a & ~31, (a & ~31) + 32, 4)} | {p for a,b in AF_OVERLAYS for p in range(a,b,4)}))
AF_SPEEDS = (0x2ADC2C, 0x2ADC30, 0x6BC9B0)
# 完整排除所有已知观察代码与 AF 主体留驻，不能以 unhook 代替手动重启。
ZERO_RANGES = ((0x2B26A0, 0x2B4000),)
ZERO_WORDS = tuple(sorted({a for start, end in ZERO_RANGES for a in range(start, end, 4)}))
READ_SET = frozenset(IRQ_GUARDS) | frozenset(CACHE_CODE + HOOK_LINES + AF_CODE + AF_SPEEDS + ZERO_WORDS + (pre.AF_IDLE,))
CACHE_RANGES = ((PAYLOAD_START, PAYLOAD_BYTES),) + tuple((a & ~31, 32) for a in HOOK_ENTRIES)


def payload():
    data = (HERE / "build/farm-route7-trace/target.bin").read_bytes()
    if len(data) != PAYLOAD_BYTES or hashlib.sha256(data).hexdigest() != PAYLOAD_SHA:
        raise RuntimeError("fixed G7R1 payload mismatch")
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
    """当前源码、ELF、固定产物和离线模型证据逐项绑定。"""
    try:
        output = HERE / "build/farm-route7-trace"
        arm_report = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        loader_report = json.loads((output / "loader-validation.json").read_text(encoding="utf-8"))
        built = json.loads((output / "build.json").read_text(encoding="utf-8"))
        if not arm_report.get("passed") or not loader_report.get("passed") or loader_report.get("tests", 0) < 7:
            return False
        if loader_report.get("payload_sha256") != PAYLOAD_SHA:
            return False
        payload()
        for name in ("simulation", "target"):
            if arm_report.get(name) != {"tests": 7, "passed": True}:
                return False
            if hashlib.sha256((output / (name + ".elf")).read_bytes()).hexdigest() != built[name]["elf_sha256"]:
                return False
        required = ("research/farm_route7_loader.py", "research/farm_probe_loader.py",
                    "research/farm_probe_preflight.py", "research/farm_route7_record.py",
                    "CodeTests/test_farm_route7_loader.py", "CodeTests/test_farm_route7_trace.py",
                    "native/farm_route7_trace.S", "research/build_farm_route7_trace.py")
        return all(loader_report.get("source_hashes", {}).get(name) == hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                   for name in required)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
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
        raise ValueError("outside fixed G7R1 scope")
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
        if self.failed or self.requests >= 8000:
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
        for address in AF_SPEEDS:
            if self.io.read(address) != 4500:
                raise RuntimeError("current AF speed differs from observed 4500 baseline")
        for address, (mask, expected) in IRQ_GUARDS.items():
            if self.io.read(address) & mask != expected:
                raise RuntimeError("cache/SGI guard mismatch at " + hex(address))
        for address in sorted(set(CACHE_CODE + HOOK_LINES + AF_CODE)):
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
                       "original_af_code_and_empty_arena_verified": True,
                       "installed": False, "armed": False, "probe_executed": False, "preserved_af_speed": 4500,
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
            raise ValueError("cache range outside fixed G7R1 scope")
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
        self._verify_values(armed, NEW_HOOKS)

    def _verify_values(self, armed, hooks):
        if any(self.io.read(a) != value for a, value in hooks.items()):
            raise RuntimeError("hook mismatch")
        if self.io.read(CB) != ORIG_CB or self.io.read(ARG) != ORIG_ARG or any(self.io.read(a) for a in range(BASE, BASE + 64, 4)):
            raise RuntimeError("scratch/callback mismatch")
        data = payload()
        for off in range(0, RECORD - PAYLOAD_START, 4):
            if self.io.read(PAYLOAD_START + off) != struct.unpack_from("<I", data, off)[0]:
                raise RuntimeError("payload code mismatch")
        if self.io.read(RECORD) != MAGIC or self.io.read(RECORD + 4) != armed or self.io.read(RECORD + 8) & 1:
            raise RuntimeError("record mismatch")
        if any(self.io.read(a) != 4500 for a in AF_SPEEDS) or self.io.read(pre.AF_IDLE) & 255:
            raise RuntimeError("AF state changed")

    def extend_empty_initial_window(self, farm):
        """仅扩展已核对的初版四入口。复用原包装和空记录，不覆盖驻留代码。"""
        initial_original = {a: v for a, v in ORIGINAL_HOOKS.items() if a not in EXTRA_MARKERS}
        initial_new = {a: v for a, v in NEW_HOOKS.items() if a not in EXTRA_MARKERS}
        if (not self.saved or not self.record.get('installed') or self.record.get('armed') or
                self.record.get('original_hooks') != initial_original or self.record.get('new_hooks') != initial_new or
                self.record.get('extended_from_initial_four') or hashlib.sha256(farm).hexdigest() != pre.FARM_SHA):
            raise RuntimeError('not an eligible initial four-hook installation')
        if isinstance(self.io, FixedIO) and not offline_ready():
            raise RuntimeError('extended offline evidence mismatch')
        self._verify_values(0, initial_new)
        if any(self.io.read(RECORD + offset) for offset in range(8, RECORD_SIZE, 4)):
            raise RuntimeError('initial record not empty; do not reset or overwrite it')
        for a in EXTRA_MARKERS:
            for address in range(a & ~31, (a & ~31) + 32, 4):
                if self.io.read(address) != struct.unpack_from('<I', farm, address - 0x100000)[0]:
                    raise RuntimeError('extra original capture marker line differs')
        self.record.update(stage='extending_capture_markers', original_hooks=ORIGINAL_HOOKS, new_hooks=NEW_HOOKS,
                           previous_window='user photo reported; zero events; inconclusive')
        self.save()
        self.upload_thunk()
        for a in EXTRA_MARKERS:
            if self.io.read(pre.AF_IDLE) & 255 or self.io.read(a) != ORIGINAL_HOOKS[a]:
                raise RuntimeError('capture marker state changed')
            self.write(a, NEW_HOOKS[a])
            self.sync_code(a & ~31, 32)
        self.clean_scratch()
        self.verify(0)
        self.write(RECORD + 4, 1)
        self.record.update(stage='extended_capture_markers_armed', armed=True, extended_from_initial_four=True)
        self.save()

    def arm_once(self):
        if not self.record.get("installed") or self.record.get("ever_armed"):
            raise RuntimeError("fresh installation required")
        self.verify(0)
        if any(self.io.read(RECORD + offset) for offset in range(8, RECORD_SIZE, 4)):
            raise RuntimeError("fresh record is not empty")
        self.write(RECORD + 4, 1)
        if self.io.read(RECORD + 4) != 1:
            raise RuntimeError("arm readback")
        self.record.update(stage="armed_for_user_path_observation", armed=True, ever_armed=True)
        self.save()

    def stop_recording(self):
        if not self.record.get("installed"):
            raise RuntimeError("installation required")
        self.write(RECORD + 4, 0)
        if self.io.read(RECORD + 24):
            raise RuntimeError("producer still busy; retain payload and retry only a later read")
        self.record.update(stage="observation_stopped", armed=False)
        self.save()

    def read_record(self):
        if not self.record.get("installed"):
            raise RuntimeError("installation required")
        sequence_before = self.io.read(RECORD + 8)
        words = [self.io.read(a) for a in range(RECORD, RECORD + RECORD_SIZE, 4)]
        sequence_after = self.io.read(RECORD + 8)
        self.record["capture_raw"] = {"sequence_before": sequence_before, "words": words, "sequence_after": sequence_after}
        self.save()
        from farm_route7_record import parse_snapshot
        result = parse_snapshot(struct.pack("<24I", *words), sequence_before=sequence_before, sequence_after=sequence_after)
        self.record.update(stage="path_record_received", armed=result["armed"], capture_decoded=result)
        self.save()
        return result

    def unhook(self):
        if not self.record.get("installed") or any(self.io.read(a) != value for a, value in NEW_HOOKS.items()):
            raise RuntimeError("recorded installation no longer matches")
        self.stop_recording()
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
