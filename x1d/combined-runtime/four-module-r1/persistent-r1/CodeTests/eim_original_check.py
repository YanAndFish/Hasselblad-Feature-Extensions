"""仅离线执行 X1D 1.25.0 EIM 编排机器码；DMA、资源与日志为替身。

目的：核对选择、失败传播及清理。不能证明内存映射、DMA 或实际速度。
运行：python -B 本文件。输入为 build/fast-start-research/farm-1.25.0.bin。
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.research-cache/x1d-1.25.0/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

data = (BASE / 'build/fast-start-research/farm-1.25.0.bin').read_bytes()
digest = hashlib.sha256(data).hexdigest()
assert digest == '317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]


class Machine:
    def __init__(self, acquire=0, setup=0, finish=0):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x100000, 0x200000)
        self.u.mem_write(0x100000, data)
        self.u.mem_map(0x6c0000, 0x10000)
        self.u.mem_map(0x700000, 0x10000)
        self.calls = []
        self.asserted = False
        self.results = {0x22da78: acquire, 0x1f7ef8: setup, 0x212650: setup,
                        0x1f84a8: finish, 0x212c58: finish,
                        0x214c38: 0, 0x22e1a8: 0, 0x1f856c: 0,
                        0x212e58: 0, 0x236a14: 0}
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def hook(self, u, address, size, context):
        if address == 0x2209f4:
            self.asserted = True
            u.emu_stop()
        elif address in self.results:
            self.calls.append((address, [u.reg_read(r) for r in REGS]))
            u.reg_write(UC_ARM_REG_R0, self.results[address])
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        elif not (0x1fa864 <= address < 0x1fae54):
            raise AssertionError(f'未建模调用 {address:x}')

    def run(self, address, *args):
        self.u.reg_write(UC_ARM_REG_SP, 0x70fff0)
        self.u.reg_write(UC_ARM_REG_LR, 0x100000)
        for reg, value in zip(REGS, args):
            self.u.reg_write(reg, value)
        self.u.emu_start(address, 0x100000, count=5000)
        assert self.asserted or self.u.reg_read(UC_ARM_REG_PC) == 0x100000, '指令预算耗尽'
        return self.u.reg_read(UC_ARM_REG_R0)

    def active(self):
        return bytes(self.u.mem_read(0x6cc79c, 1)) == b'\x01'

    def count(self, address):
        return sum(a == address for a, _ in self.calls)


cases = []
for destination, setup_address, wait_address, cleanup_address, channel in [
    (0x00400000, 0x212650, 0x212c58, 0x212e58, 1),
    (0x80400000, 0x1f7ef8, 0x1f84a8, 0x1f856c, 2),
]:
    # 这些合成地址仅用于验证分支；不是已验证的可写实机地址。
    for setup_result, finish_result in [(0, 0), (7, 0), (0, 9)]:
        m = Machine(setup=setup_result, finish=finish_result)
        assert m.run(0x1fa890, destination, 4096) == setup_result
        assert m.count(setup_address) == 1
        setup_args = next(args for a, args in m.calls if a == setup_address)
        assert setup_args[:3] == [destination, 4096, channel]
        assert m.active() == (setup_result == 0)
        if setup_result == 0:
            assert m.run(0x1fabe0, 123) == finish_result
            assert m.count(wait_address) == 1
            wait_args = next(args for a, args in m.calls if a == wait_address)
            assert wait_args[:2] == [channel, 123]
            assert m.count(cleanup_address) == (1 if finish_result else 0)
        assert not m.active()
        assert m.count(0x22e1a8) == 1
        cases.append({'branch': channel, 'setupResult': setup_result, 'finishResult': finish_result})

m = Machine(acquire=5)
assert m.run(0x1fa890, 0x400000, 512) == 5
assert not m.active() and m.count(0x212650) == 0 and m.count(0x22e1a8) == 0
cases.append({'case': 'resource-busy'})
m = Machine()
assert m.run(0x1fabe0, 123) == 1 and not m.calls
cases.append({'case': 'finish-without-transfer'})
m = Machine()
m.run(0x1fa890, 0x400000, 513)
assert m.asserted and not m.calls and not m.active()
cases.append({'case': 'unaligned-length-asserts-before-acquire'})
report = {'firmware': 'X1D 1.25.0', 'sha256': digest, 'passed': len(cases), 'cases': cases,
          'scope': 'original ARM orchestration with mocked DMA/resource/logging; no hardware or timing claim'}
(BASE / 'build/fast-start-research/eim-original-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
