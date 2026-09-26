"""执行候选 ARM 指令的离线检查；外部固件函数与寄存器均为模拟内存。"""
from pathlib import Path
import json
import struct
import sys

SCOPE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCOPE.parents[1] / ".research-cache/x1d-1.25.0/python"))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR

BASE, FAST, STATE, RETURN = 0x180000, 0x216800, 0x2147E0, 0x217F00
PHY, D11, STACK = 0x300000, 0x400000, 0x500000
HASH = 0x0E77BE41
blob = (SCOPE / "build/prepared-wltest.bin").read_bytes()
checks = 0


def check(condition, detail):
    global checks
    assert condition, detail
    checks += 1


def machine(overrides=None):
    emu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    for start, size in [(BASE, 0xA0000), (0x8000, 0x1000), (PHY, 0x2000), (D11, 0x2000), (STACK, 0x2000)]:
        emu.mem_map(start, size)
    emu.mem_write(BASE, blob)
    emu.mem_write(PHY + 0x100, struct.pack("<I", D11))
    values = {"held": 1, "generated": 1, "verified": 1, "hash": HASH, "channel": 0x1002, "mac": 0, "high": 0, "psm": 2}
    values.update(overrides or {})
    for key, offset in [("generated", 0), ("hash", 4), ("verified", 8), ("held", 16)]:
        emu.mem_write(STATE + offset, struct.pack("<I", values[key]))
    emu.mem_write(PHY + 0x10E, struct.pack("<H", values["channel"]))
    emu.mem_write(D11 + 0x120, struct.pack("<I", values["mac"]))
    emu.mem_write(D11 + 0x538, struct.pack("<H", values["high"]))
    emu.mem_write(D11 + 0x492, struct.pack("<H", values["psm"]))
    trace = {"starts": 0, "calls": [], "samplePort": 0, "tsf": 0, "psmWrites": []}
    external = {0x1C620E: "readPhy", 0x1BB31C: "carrier", 0x1BB3D6: "sampleSetup",
                0x8710: "delay", 0x1BB210: "sampleStop", 0x1C6224: "writePhy"}

    def at_code(cpu, address, size, data):
        if address not in external:
            return
        name = external[address]
        args = [cpu.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        trace["calls"].append([name, args])
        answer = 3 if name == "readPhy" and args[1] == 0x471 else 0
        cpu.reg_write(UC_ARM_REG_R0, answer)
        cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

    def memory_read(cpu, access, address, size, value, data):
        if address == D11 + 0x134:
            trace["samplePort"] += 1
        if address == D11 + 0x180:
            trace["tsf"] += 1

    def memory_write(cpu, access, address, size, value, data):
        if address == D11 + 0x134:
            trace["samplePort"] += 1
        if address == D11 + 0x492:
            trace["psmWrites"].append(value)
            if value == 0x1802:
                trace["starts"] += 1

    emu.hook_add(UC_HOOK_CODE, at_code)
    emu.hook_add(UC_HOOK_MEM_READ, memory_read)
    emu.hook_add(UC_HOOK_MEM_WRITE, memory_write)
    return emu, trace


def invoke(emu):
    emu.reg_write(UC_ARM_REG_CPSR, 0x3F)
    emu.reg_write(UC_ARM_REG_R0, PHY)
    emu.reg_write(UC_ARM_REG_R1, 0)
    emu.reg_write(UC_ARM_REG_SP, STACK + 0x1F00)
    emu.reg_write(UC_ARM_REG_LR, RETURN | 1)
    emu.emu_start(FAST | 1, RETURN, count=1000)
    check(emu.reg_read(UC_ARM_REG_PC) == RETURN, "函数未在有界指令数内返回")
    return emu.reg_read(UC_ARM_REG_R0)


for changed, expected in [({"held": 0}, 2), ({"held": 2}, 2), ({"generated": 0}, 3),
                          ({"verified": 0}, 3), ({"hash": HASH ^ 1}, 3), ({"channel": 0x1001}, 4),
                          ({"mac": 1}, 5), ({"high": 1}, 6), ({"psm": 0}, 7)]:
    emu, trace = machine(changed)
    check(invoke(emu) == expected, "异常准备状态未拒绝：" + str(changed))
    check(trace["starts"] == 0, "异常状态进入了模拟发射")

emu, trace = machine()
for attempt in range(2):
    check(invoke(emu) == 1, "已准备的发射未正常返回")
    check(trace["starts"] == attempt + 1, "每次调用未严格对应一次模拟启动")
    check(struct.unpack("<I", emu.mem_read(STATE, 4))[0] == 1, "可复用准备标志丢失")
    check(struct.unpack("<I", emu.mem_read(STATE + 8, 4))[0] == 1, "校验标志丢失")
    check(struct.unpack("<H", emu.mem_read(D11 + 0x492, 2))[0] == 2, "未清理播放控制")
check(trace["samplePort"] == 0, "发射热路径仍访问整段波形端口")
check(trace["tsf"] == 0, "重新引入了此前实机挂起的计时寄存器访问")
check([args[0] for name, args in trace["calls"] if name == "delay"] == [500, 500], "原单次播放等待被更改")
emu.mem_write(STATE + 16, struct.pack("<I", 0))
check(invoke(emu) == 2 and trace["starts"] == 2, "释放后仍可发射")
print(json.dumps({"preparedFirmwareChecks": checks, "hardwareRequests": 0, "timingMeasured": False}))
