"""执行原/候选 ARM 取出与完成路径；Qt、VPU 和 Storage 使用有界替身。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

X1D = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(X1D / "tools"))
from binary import ArmElf
from patch_jpeg_failure import build
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

CAPACITY = 8 * 1024 * 1024
PHYSICAL = 0x18000000
VIRTUAL = 0x61000000
WORKER = 0x60000100
HANDLE = 0x60000300
ENCODER = 0x60000400
CALL = 0x60000500
LOG_CONFIG = 0x60000600
STACK = 0x700E0000
STOP = 0x700FF000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
SAVED = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
EVIDENCE: list[dict] = []


@dataclass(frozen=True)
class Segment:
    data: bytes
    start: int = 0


def segment(size: int, label: str, start: int = 0) -> Segment:
    # 人工码流，仅检验字节搬运；不是照片、实际编码输出或解码质量测试。
    return Segment(hashlib.shake_256(label.encode("ascii")).digest(size), start)


class ArmPath:
    def __init__(self, data: bytes, busy: list[Segment], before: Segment, after: Segment,
                 fail: tuple[str, int] | None = None, output_error: bool = False,
                 reset_error: bool = False):
        self.elf = ArmElf(data)
        plt = self.elf.elf.get_section_by_name(".plt")
        self.plt_bounds = (plt["sh_addr"], plt["sh_addr"] + plt["sh_size"])
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(0x10000, 0x40000)
        for item in self.elf.elf.iter_segments():
            if item["p_type"] == "PT_LOAD":
                self.uc.mem_write(item["p_vaddr"], item.data())
        self.uc.mem_map(0x60000000, 0x400000)
        self.uc.mem_map(VIRTUAL, CAPACITY)
        self.uc.mem_map(0x70000000, 0x100000)
        self.heap = 0x60001000
        self.arrays: dict[int, bytearray] = {}
        self.strings: dict[int, str] = {}
        self.array_object = STACK + 0x98
        self.empty = self.allocate(16)
        self.uc.mem_write(self.empty, struct.pack("<iIII", -1, 0, 0, 16))
        self.arrays[self.empty] = bytearray()
        # 相当于装载器解析 Qt shared_null 数据导入；不执行 Qt 库。
        self.put(0x3A79C, self.empty)
        self.put(WORKER + 0x40, HANDLE)
        self.put(WORKER + 0x50, VIRTUAL)
        self.put(STACK + 0x1C0, PHYSICAL)
        self.put(STACK + 0x20, 0x60000700)
        self.set_array(self.array_object, b"OFFLINE_HEADER")
        self.busy_count = len(busy)
        self.after = after
        self.segments = busy + [before] + ([after] if after.data else [])
        self.expected = b"OFFLINE_HEADER" + b"".join(part.data for part in self.segments)
        self.fail = fail
        self.output_error = output_error
        self.reset_error = reset_error
        self.get_calls = 0
        self.updates: list[int] = []
        self.update_attempts: list[int] = []
        self.resets = 0
        self.output_calls = 0
        self.worker_events: list[tuple[str, bytes | str]] = []
        self.encoder_events: list[bytes] = []
        self.writes: list[tuple[str, bytes]] = []
        self.deletions = 0
        self.worker_deletions = 0
        self.next_calls = 0
        self.abi_returns = 0
        self.drain_frame: tuple[int, int, list[int]] | None = None
        self.target_stop = STOP
        self.stopped = False
        self.trace: list[int] = []
        self.hooks = {
            0x15824: self.get_buffer, 0x159B0: self.update_buffer,
            0x1556C: self.is_busy, 0x15650: lambda: self.ret(0),
            0x15938: lambda: self.ret(0), 0x15B6C: self.output_info,
            0x15E84: self.reset, 0x15D28: self.append,
            0x26D8C: self.worker_finished, 0x26DD0: self.worker_failed,
            0x2687C: self.encoder_finished, 0x15AE8: self.delete_worker,
            0x1768C: lambda: self.ret(LOG_CONFIG),
            0x1D75C: self.delete_call, 0x1A538: self.next_call,
            0x15E0C: self.write_file,
            0x15C8C: self.from_utf8, 0x1586C: self.from_ascii,
            0x15FE0: self.number, 0x15B9C: self.string_append,
            0x157B8: self.last_index, 0x1580C: self.string_left,
            0x15A40: self.logger, 0x158C0: self.logger,
            0x15710: lambda: self.ret(0), 0x15974: lambda: self.ret(0),
        }
        for at in [0x15830, 0x15E00, 0x15AA0, 0x15E48]:
            self.hooks[at] = lambda: self.ret(self.reg(0))
        self.uc.hook_add(UC_HOOK_CODE, self.step)

    def allocate(self, size: int) -> int:
        result = self.heap
        self.heap += (size + 15) & ~15
        if self.heap >= 0x60400000:
            raise AssertionError("替身内存越界")
        return result

    def put(self, at: int, value: int) -> None:
        self.uc.mem_write(at, struct.pack("<I", value & 0xFFFFFFFF))

    def word(self, at: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(at, 4))[0]

    def reg(self, number: int) -> int:
        return self.uc.reg_read(REGS[number])

    def ret(self, value: int = 0) -> None:
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def set_array(self, obj: int, data: bytes) -> None:
        descriptor = self.allocate(16)
        self.uc.mem_write(descriptor, struct.pack("<iIII", -1, len(data), 0, 16))
        self.arrays[descriptor] = bytearray(data)
        self.put(obj, descriptor)

    def array(self, obj: int) -> bytes:
        descriptor = self.word(obj)
        result = self.arrays[descriptor]
        assert self.word(descriptor + 4) == len(result)
        return bytes(result)

    def set_string(self, obj: int, text: str) -> int:
        content = text.encode("utf-16le")
        descriptor = self.allocate(18 + len(content))
        self.uc.mem_write(descriptor, struct.pack("<iIII", -1, len(content) // 2, 0, 16) + content + b"\0\0")
        self.strings[descriptor] = text
        self.put(obj, descriptor)
        return descriptor

    def string(self, obj: int) -> str:
        descriptor = self.word(obj)
        return self.strings.get(descriptor, "" if descriptor == self.empty else "UNEXPECTED")

    def append(self) -> None:
        obj, start, size = self.reg(0), self.reg(1), self.reg(2)
        assert VIRTUAL <= start <= start + size <= VIRTUAL + CAPACITY
        descriptor = self.word(obj)
        self.arrays[descriptor].extend(self.uc.mem_read(start, size))
        self.put(descriptor + 4, len(self.arrays[descriptor]))
        self.ret(obj)

    def get_buffer(self) -> None:
        assert self.reg(0) == HANDLE
        index = self.get_calls
        self.get_calls += 1
        if index >= len(self.segments):
            raise AssertionError("重复取出或意外请求额外片段")
        if self.fail == ("get", index):
            self.ret(-6)
            return
        part = self.segments[index]
        assert 0 <= part.start < CAPACITY and len(part.data) <= CAPACITY
        first = min(len(part.data), CAPACITY - part.start)
        if first:
            self.uc.mem_write(VIRTUAL + part.start, part.data[:first])
        if first < len(part.data):
            self.uc.mem_write(VIRTUAL, part.data[first:])
        self.put(self.reg(1), PHYSICAL + part.start)
        self.put(self.reg(2), PHYSICAL + (part.start + len(part.data)) % CAPACITY)
        self.put(self.reg(3), len(part.data))
        self.ret(0)

    def update_buffer(self) -> None:
        assert self.reg(0) == HANDLE
        index = self.get_calls - 1
        assert self.reg(1) == len(self.segments[index].data) > 0
        self.update_attempts.append(index)
        if self.fail == ("update", index):
            self.ret(-6)
            return
        self.updates.append(index)
        self.ret(0)

    def is_busy(self) -> None:
        self.ret(int(self.get_calls < self.busy_count))

    def output_info(self) -> None:
        assert self.reg(0) == HANDLE
        self.output_calls += 1
        if self.output_error:
            self.ret(-4)
        else:
            self.put(self.reg(1) + 4, len(self.after.data))
            self.ret(0)

    def reset(self) -> None:
        assert self.reg(0) == HANDLE and self.reg(1) == 0
        assert self.output_calls == 0, "取完 OutputInfo 后不能重置别的编码任务"
        self.resets += 1
        self.ret(-1 if self.reset_error else 0)

    def worker_finished(self) -> None:
        assert self.reg(0) == WORKER
        self.worker_events.append(("success", self.array(self.reg(1))))
        self.ret(0)

    def worker_failed(self) -> None:
        assert self.reg(0) == WORKER
        self.worker_events.append(("failure", self.string(self.reg(1))))
        self.ret(0)

    def encoder_finished(self) -> None:
        assert self.reg(0) == ENCODER
        self.encoder_events.append(self.array(self.reg(1)))
        self.ret(0)

    def delete_worker(self) -> None:
        assert self.reg(0) == WORKER
        self.worker_deletions += 1
        self.ret(0)

    def delete_call(self) -> None:
        assert self.reg(0) == CALL
        self.deletions += 1
        self.ret(0)

    def next_call(self) -> None:
        assert self.reg(0) == ENCODER and self.word(ENCODER + 16) == 0
        self.next_calls += 1
        self.ret(0)

    def write_file(self) -> None:
        assert self.reg(0) == 0x60000800 and self.reg(2) == 0 and self.reg(3) == 0
        path = self.string(self.word(self.uc.reg_read(UC_ARM_REG_SP)))
        self.writes.append((path, self.array(self.reg(1))))
        self.ret(0)

    def from_utf8(self) -> None:
        out, src, size = self.reg(0), self.reg(1), self.reg(2)
        assert size < 1024
        text = bytes(self.uc.mem_read(src, size)).decode("utf-8")
        self.set_string(out, text)
        self.ret(out)

    def from_ascii(self) -> None:
        src, size = self.reg(0), self.reg(1)
        assert size < 1024
        out = self.allocate(4)
        descriptor = self.set_string(out, bytes(self.uc.mem_read(src, size)).decode("ascii"))
        self.ret(descriptor)

    def number(self) -> None:
        out, value = self.reg(0), self.reg(1)
        if value & 0x80000000:
            value -= 1 << 32
        self.set_string(out, str(value))
        self.ret(out)

    def string_append(self) -> None:
        obj = self.reg(0)
        self.set_string(obj, self.string(obj) + self.string(self.reg(1)))
        self.ret(obj)

    def last_index(self) -> None:
        self.ret(self.string(self.reg(0)).rfind(chr(self.reg(1))))

    def string_left(self) -> None:
        out = self.reg(0)
        self.set_string(out, self.string(self.reg(1))[:self.reg(2)])
        self.ret(out)

    def logger(self) -> None:
        obj = self.reg(0)
        self.put(obj, self.allocate(0x30))
        self.ret(obj)

    def step(self, uc: Uc, address: int, size: int, _data) -> None:
        self.trace.append(address)
        if len(self.trace) > 16:
            self.trace.pop(0)
        if address == self.target_stop:
            self.stopped = True
            uc.emu_stop()
            return
        if address == 0x234CC:
            assert self.drain_frame is None
            self.drain_frame = (uc.reg_read(UC_ARM_REG_LR), uc.reg_read(UC_ARM_REG_SP),
                                [uc.reg_read(reg) for reg in SAVED])
        elif self.drain_frame and address == self.drain_frame[0]:
            _, sp, registers = self.drain_frame
            assert uc.reg_read(UC_ARM_REG_SP) == sp
            assert [uc.reg_read(reg) for reg in SAVED] == registers, "drain 破坏 callee-saved 寄存器"
            self.drain_frame = None
            self.abi_returns += 1
        if address in self.hooks:
            self.hooks[address]()
        elif self.plt_bounds[0] <= address < self.plt_bounds[1]:
            raise AssertionError(f"未声明的外部调用 {address:#x}: {self.elf.name(address)}")

    def execute(self, address: int, stop: int = STOP) -> None:
        self.target_stop = stop
        self.stopped = False
        self.trace.clear()
        self.uc.reg_write(UC_ARM_REG_LR, STOP)
        try:
            self.uc.emu_start(address, 0, count=100000)
        except Exception as error:
            raise AssertionError(f"ARM 路径失败，最近位置 {[hex(a) for a in self.trace]}") from error
        assert self.stopped, "指令预算耗尽或没有到达预定结束位置"

    def run(self) -> dict:
        self.uc.reg_write(UC_ARM_REG_SP, STACK)
        for index, reg in enumerate(SAVED):
            self.uc.reg_write(reg, 0x1000 + index)
        self.uc.reg_write(UC_ARM_REG_R4, WORKER)
        self.uc.reg_write(UC_ARM_REG_R5, self.array_object)
        self.uc.reg_write(UC_ARM_REG_R11, STACK + 0x168)
        self.execute(0x25868, 0x25910)
        assert self.uc.reg_read(UC_ARM_REG_SP) == STACK
        assert len(self.worker_events) == 1 and self.drain_frame is None
        kind, result = self.worker_events[0]
        # 按固件连接关系递送一次替身信号，再执行原 ImxEncoder 回调。
        self.put(ENCODER + 0x28, WORKER)
        self.uc.reg_write(UC_ARM_REG_SP, STACK - 0x1000)
        signal_arg = self.allocate(4)
        if kind == "success":
            self.set_array(signal_arg, result)
            callback = 0x21270
        else:
            self.set_string(signal_arg, result)
            callback = 0x2129C
        self.uc.reg_write(UC_ARM_REG_R0, ENCODER)
        self.uc.reg_write(UC_ARM_REG_R1, signal_arg)
        self.execute(callback)
        assert len(self.encoder_events) == 1 and self.word(ENCODER + 0x28) == 0
        assert self.worker_deletions == 1
        # 执行原 Encoder 完成函数及其真实 ConvertCall 虚调用。
        array_arg = self.allocate(4)
        self.set_array(array_arg, self.encoder_events[0])
        self.put(ENCODER + 16, CALL)
        self.put(CALL, 0x3A094)
        self.set_string(CALL + 8, "offline-fixture.3FR")
        self.put(CALL + 28, 0x60000800)
        self.uc.reg_write(UC_ARM_REG_R0, ENCODER)
        self.uc.reg_write(UC_ARM_REG_R1, array_arg)
        self.execute(0x1AE18)
        assert self.uc.reg_read(UC_ARM_REG_SP) == STACK - 0x1000
        assert self.deletions == 1 and self.next_calls == 1
        return {"workerResult": kind, "gets": self.get_calls, "successfulUpdates": self.updates,
                "updateAttempts": self.update_attempts, "resetRequests": self.resets,
                "outputInfoCalls": self.output_calls, "completionNotifications": len(self.encoder_events),
                "fileWrites": len(self.writes), "queueAdvances": self.next_calls,
                "abiReturnsChecked": self.abi_returns,
                "expectedBytes": len(self.expected), "bytesOfferedToStorage": sum(len(v) for _, v in self.writes)}


class JpegFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = ArmElf.load("usr/bin/jpeg-daemon").data
        cls.candidate, cls.manifest = build()

    def success(self, name: str, busy: list[Segment], before: Segment, after: Segment) -> None:
        for label, data in [("original", self.original), ("candidate", self.candidate)]:
            with self.subTest(name=name, image=label):
                path = ArmPath(data, busy, before, after)
                result = path.run()
                self.assertEqual(result["workerResult"], "success")
                self.assertEqual(path.writes, [("offline-fixture.JPG", path.expected)])
                self.assertEqual(path.updates, [i for i, p in enumerate(path.segments) if p.data])
                self.assertEqual(result["resetRequests"], 0)
                EVIDENCE.append({"case": name, "image": label, **result})

    def test_success_boundaries(self) -> None:
        empty = Segment(b"")
        self.success("within_8mib", [], segment(1024 * 1024, "within"), empty)
        self.success("exact_8mib_empty_tail", [segment(CAPACITY, "exact")], empty, empty)
        self.success("cross_8mib", [segment(CAPACITY, "cross")], segment(137, "tail"), empty)
        self.success("over_16mib_nonempty_final", [segment(CAPACITY, "first"), segment(CAPACITY, "second")],
                     segment(1024 * 1024 + 31, "third"), segment(47, "last"))
        self.success("wrap_each_phase", [segment(1024, "wrap1", CAPACITY - 511)],
                     segment(287, "wrap2", CAPACITY - 63), segment(39, "wrap3", CAPACITY - 10))
        self.success("empty_before_nonempty_final", [segment(4096, "body")], empty, segment(333, "after"))

    def test_failures_do_not_write_and_advance_once(self) -> None:
        parts = [segment(1024, "busy1"), segment(2048, "busy2")]
        for api in ["get", "update"]:
            for index in range(4):
                with self.subTest(api=api, index=index):
                    path = ArmPath(self.candidate, parts, segment(256, "before"), segment(512, "after"), (api, index))
                    result = path.run()
                    self.assertEqual(result["workerResult"], "failure")
                    self.assertEqual(path.encoder_events, [b""])
                    self.assertEqual(path.writes, [])
                    self.assertEqual(path.get_calls, index + 1)
                    self.assertEqual(path.resets, 1 if index < 3 else 0)
                    self.assertEqual(len(set(path.update_attempts)), len(path.update_attempts))
                    EVIDENCE.append({"case": f"{api}_failure_phase_{index}", "image": "candidate", **result})

    def test_original_failure_witness(self) -> None:
        path = ArmPath(self.original, [segment(1024, "body")], segment(31, "end"), Segment(b""), ("get", 0))
        result = path.run()
        self.assertEqual(result["workerResult"], "success")
        self.assertEqual(len(path.writes), 1)
        self.assertNotEqual(path.writes[0][1], path.expected)
        EVIDENCE.append({"case": "original_get_failure_can_publish_partial_result", "image": "original", **result})

    def test_original_empty_write_witness(self) -> None:
        path = ArmPath(self.original, [], segment(64, "body"), Segment(b""), output_error=True)
        result = path.run()
        self.assertEqual(result["workerResult"], "failure")
        self.assertEqual(path.writes, [("offline-fixture.JPG", b"")])
        EVIDENCE.append({"case": "original_output_error_reaches_empty_write", "image": "original", **result})

    def test_output_error_and_reset_error_still_do_not_publish(self) -> None:
        for label, options in [("output_info_error", {"output_error": True}),
                               ("reset_error", {"fail": ("get", 0), "reset_error": True})]:
            with self.subTest(case=label):
                path = ArmPath(self.candidate, [segment(32, "body")], segment(16, "tail"), Segment(b""), **options)
                result = path.run()
                self.assertEqual(result["workerResult"], "failure")
                self.assertEqual(path.writes, [])
                EVIDENCE.append({"case": label, "image": "candidate", **result})

    def test_fixed_baseline_and_layout(self) -> None:
        modified = bytearray(self.original)
        modified[-1] ^= 1
        with self.assertRaises(ValueError):
            build(bytes(modified))
        before, after = ArmElf(self.original), ArmElf(self.candidate)
        self.assertEqual(self.original[:52], self.candidate[:52])
        for name in [".ARM.exidx", ".ARM.extab", ".dynsym", ".rel.dyn", ".rel.plt"]:
            self.assertEqual(before.elf.get_section_by_name(name).data(), after.elf.get_section_by_name(name).data())
        self.assertEqual(before.read(0x23768, 0x2C), after.read(0x23768, 0x2C))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JpegFailureTests))
    if result.wasSuccessful():
        target = X1D / "research/validation/jpeg-failure-arm.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schemaVersion": 1, "method": "Unicorn 执行固定 ARM 路径，Qt/VPU/Storage 替身",
            "realCamera": False, "realVpuEncoding": False, "realFilePersistence": False,
            "candidateSha256": JpegFailureTests.manifest["candidateSha256"],
            "testMethods": result.testsRun, "cases": EVIDENCE}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
