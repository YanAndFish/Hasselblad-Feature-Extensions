"""固定 X3 Pro C 固件的发送顺序证据；仅模拟，外设替身不访问硬件。"""
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / '.research-cache/x1d-1.25.0/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn import arm_const as a

BASE = 0x08020000
RAW = (HERE / 'build/transmitter-reference/X3pro_C_v1.22_app.bin').read_bytes()
SHA = '2e2b8a3b5ff70e62c4acddc406b055ea2625e4833a213e81863f96c0da5a911b'
assert hashlib.sha256(RAW).hexdigest() == SHA
assert int.from_bytes(RAW[4:8], 'little') == BASE + 0x11345

def machine(stop):
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    u.mem_map(BASE, 0x200000)
    u.mem_write(BASE, RAW)
    u.mem_map(0x20000000, 0x10000)
    events = []
    def hook(cpu, address, size, _):
        if address == stop:
            cpu.emu_stop()
            return
        offset = address - BASE
        if offset in (0xe71c, 0xe88c, 0x12a64, 0xb5dc, 0xb5ac):
            r = [cpu.reg_read(reg) for reg in (a.UC_ARM_REG_R0, a.UC_ARM_REG_R1, a.UC_ARM_REG_R2)]
            if offset == 0xe71c:
                events.append(['fifo', bytes(cpu.mem_read(r[1], r[2])).hex()])
            elif offset == 0xe88c:
                events.append(['strobe', r[0]])
            cpu.reg_write(a.UC_ARM_REG_PC, cpu.reg_read(a.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)
    u.reg_write(a.UC_ARM_REG_SP, 0x2000fff0)
    u.reg_write(a.UC_ARM_REG_LR, stop | 1)
    return u, events

def run():
    priority = []
    for phase in range(4):
        stop = BASE + 0x1ff00
        u, events = machine(stop)
        u.mem_write(0x20001d06, bytes([phase, 7, 3, 0]))
        for reg, val in [(a.UC_ARM_REG_R0, 0x50), (a.UC_ARM_REG_R1, 0xb4), (a.UC_ARM_REG_R2, 9)]:
            u.reg_write(reg, val)
        u.emu_start(BASE + 0xcadd, stop, count=10000)
        assert u.reg_read(a.UC_ARM_REG_PC) == stop
        assert ['fifo', 'a950b409'] in events
        assert u.mem_read(0x20001d07, 2) == bytes([7, 3])
        assert u.mem_read(0x20001d09, 1) == b'\0'
        if phase == 1:
            assert events[:2] == [['strobe', 0x3b], ['strobe', 0x36]]
        priority.append({'queuePhase': phase, 'events': events})
    modes = []
    for mode in range(3):
        stop = BASE + 0x6096
        u, events = machine(stop)
        for group in range(16):
            u.mem_write(0x20001644 + 10 * group, bytes([0, 40, 0, 0xc0, 0, 0, 0, 0, 0, 0]))
        u.mem_write(0x200010d5, bytes([mode]))
        u.mem_write(0x20000eb4, bytes([0xb6, 0, 0, 0, 0, 0, 0, 0]))
        # 进入已完成消息分发的 B6 分支；不声称模拟了热靴电气握手。
        for repeat in range(2):
            events.clear()
            u.reg_write(a.UC_ARM_REG_R5, 0x20000eb4)
            u.reg_write(a.UC_ARM_REG_SP, 0x2000fff0)
            u.emu_start(BASE + 0x6385, stop, count=100000)
            assert u.reg_read(a.UC_ARM_REG_PC) == stop
            packets = [x[1] for x in events if x[0] == 'fifo']
            assert packets[:2] == ['a950c000', 'a950b300']
            assert packets[-1] == 'a950b402'
            power = [p for p in packets if p[4:6] == 'bc']
            assert power == ([f'a9{g:02x}bc28' for g in range(10, 15)] if mode == 1 else [])
            modes.append({'mode': mode, 'repeat': repeat, 'packets': packets})
    result = {'passed': True, 'sourceSha256': SHA, 'loadBase': hex(BASE),
              'hardwareRequests': 0, 'physicalTimingMeasured': False,
              'directPriority': priority, 'preparationBranch': modes,
              'limitations': ['SHOOT UI label binding not independently proved',
                              'B6 branch starts after dispatch; no hotshoe electrical simulation',
                              'radio, GPIO and delay functions are stubs; no RF timing claim']}
    out = HERE / 'build/transmitter-reference/shoot-order-validation.json'
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    run()
