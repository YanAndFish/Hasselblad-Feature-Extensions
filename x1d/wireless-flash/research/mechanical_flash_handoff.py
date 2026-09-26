"""固定 SUC 的闪光同步交接离线核对；所有寄存器仅为 Unicorn 内存。"""
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R9, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

HERE = Path(__file__).resolve().parents[1]
SUC_SHA = "6bce5b264f431250be952dcfcaefee45a435a6355ebc22b45c9e824c165725a7"
ROM, RAM, MMIO, NVIC, STOP = 0x08000000, 0x20000000, 0x40000000, 0xE000E000, 0x08040000


def run(suc):
    assert Path.cwd().resolve() == HERE.parents[1]
    assert hashlib.sha256(suc.data).hexdigest() == SUC_SHA
    word = lambda a: struct.unpack("<I", suc.read(a, 4))[0]
    # Reset routine 0x080001f6..0x08000208 copies this initialized data range.
    dest, source, end = [word(a) for a in (0x080002bc, 0x080002c0, 0x080002c4)]
    assert (dest, source, end) == (RAM, 0x0803adec, RAM + 0x240)
    port_table = word(0x08012e34)
    assert port_table == RAM + 0x70
    ports = struct.unpack("<6I", suc.read(source + port_table - dest, 24))
    assert ports[2:4] == (0x40011000, 0x40011400)
    pins = []
    for a, selector, name in ((0x08028ce0, 0x209, "FlashSyncSu"), (0x08028e00, 0x305, "FlashEnable")):
        assert word(a) == selector
        assert suc.read(a + 4, 20).split(b"\0")[0].decode() == name
        pins.append({"selector": hex(selector), "name": name, "base": hex(ports[selector >> 8]), "bit": selector & 15})
    assert word(ROM + (16 + 23) * 4) == 0x080038a5
    checks = []
    for at, target in (
        (0x08005366, 0x08017080), (0x08005396, 0x08017080),
        (0x0800552c, 0x08012e04), (0x080055fa, 0x08009554),
        (0x080055b0, 0x08012e38), (0x080055cc, 0x08012e04),
        (0x08005648, 0x08012e38), (0x0800568c, 0x080170c0),
        (0x080038ac, 0x08012e04), (0x080038be, 0x08012ec0),
    ):
        i = suc.instructions(at, 4)[0]
        assert i.mnemonic == "bl" and int(i.op_str[1:], 16) == target
        checks.append({"at": hex(at), "target": hex(target)})

    def emulate(entry, finish, shutter_code=0, calls=None, args=()):
        uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        uc.mem_map(ROM, 0x41000)
        uc.mem_write(ROM, suc.data)
        uc.mem_map(RAM, 0x10000)
        uc.mem_write(dest, suc.read(source, end - dest))
        uc.mem_map(MMIO, 0x20000)
        uc.mem_map(NVIC, 0x2000)
        uc.reg_write(UC_ARM_REG_SP, RAM + 0xf000)
        uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        uc.reg_write(UC_ARM_REG_R9, shutter_code & 0xffffffff)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
            uc.reg_write(reg, value)
        events, executed = [], []
        stubs = {} if calls is None else calls

        def code(u, at, size, _):
            executed.append(at)
            if at == finish:
                u.emu_stop()
            elif at in stubs:
                kind, ret = stubs[at]
                if kind:
                    events.append({"kind": kind, "r0": u.reg_read(UC_ARM_REG_R0), "r1": u.reg_read(UC_ARM_REG_R1)})
                u.reg_write(UC_ARM_REG_R0, ret)
                u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

        def write(u, access, address, size, value, _):
            if address >= MMIO:
                events.append({"kind": "virtual_register_write", "address": hex(address), "size": size, "value": hex(value)})

        uc.hook_add(UC_HOOK_CODE, code)
        uc.hook_add(UC_HOOK_MEM_WRITE, write)
        uc.emu_start(entry | 1, STOP + 2, count=20000)
        assert executed[-1] == finish, (hex(executed[-1]), hex(finish))
        return {"entry": hex(entry), "finish": hex(finish), "events": events, "instruction_count": len(executed)}

    # Only the post-preparation mechanical branch is replayed. Lens/OS services
    # below return explicit synthetic values; no physical shutter timing follows.
    cases = []
    for double in (0, 1):
        for shutter in (0, -24):
            stubs = {
                0x08008f84: (None, 1), 0x08004300: (None, double),
                0x08006c80: (None, 0), 0x08011b9c: (None, 1234),
                0x08009554: ("lens_command", 1), 0x08008738: ("lens_wait", 1),
                0x080040f0: ("capture_state", 0), 0x080097b0: (None, 12),
                0x08018620: (None, 100), 0x080050b0: ("exposure_parameters", 1),
            }
            result = emulate(0x080054f6, 0x08005666, shutter, stubs)
            result.update(double_sync=double, shutter_code=shutter, synthetic_service_returns=True)
            commands = [e["r0"] for e in result["events"] if e["kind"] == "lens_command"]
            assert commands == ([3] if shutter == 0 else [4, 5])
            sync_writes = [e for e in result["events"] if e["kind"] == "virtual_register_write" and e["address"] in ("0x40011010", "0x40011014")]
            assert not sync_writes  # No PC9 output pulse in these replayed branches.
            cases.append(result)
    init_input = emulate(0x08012d8c, STOP, args=(0x209, 0x28, 0))
    init_output = emulate(0x08012d8c, STOP, args=(0x209, 0x42, 0))
    assert init_input["events"][-1]["value"] == "0x80"  # PC9 CNF=10 MODE=00.
    assert init_output["events"][-1]["value"] == "0x20"  # PC9 CNF=00 MODE=10.
    irq = emulate(0x080038a4, STOP)
    assert irq["events"][0] == {"kind": "virtual_register_write", "address": "0x40011410", "size": 4, "value": "0x20"}
    manual = emulate(0x0801799c, STOP, calls={
        0x080019f4: ("synthetic_delay_return", 0),
        0x08016fe0: ("save_power", 0), 0x08016fec: ("queue_power", 0),
    }, args=(64,))
    sync_writes = [e["address"] for e in manual["events"] if e["kind"] == "virtual_register_write" and e["address"] in ("0x40011010", "0x40011014")]
    assert sync_writes == ["0x40011014", "0x40011010", "0x40011014", "0x40011014"]
    regions = ((0x080038a4, 0x2c), (0x08005500, 0x58), (0x0800557c, 0xee),
               (0x08012d8c, 0x74), (0x08012e04, 0x64), (0x08012ec0, 0xa8),
               (0x0801799c, 0x6a), (0x08009328, 0x22))
    report = {
        "sourceVersion": "X1D official 1.25.0", "sucSha256": SUC_SHA,
        "pins": pins, "initializedData": {"source": hex(source), "start": hex(dest), "endExclusive": hex(end)},
        "callChecks": checks, "mechanicalReplay": cases, "syncInputConfiguration": init_input,
        "testOutputConfiguration": init_output, "doubleSyncInterruptReplay": irq,
        "manualFlashTestReplay": manual,
        "regions": [{"start": hex(a), "instructions": [f"{i.address:08x} {i.mnemonic} {i.op_str}" for i in suc.instructions(a, n)]} for a, n in regions],
        "hardwareRequests": 0, "physicalTimingVerified": False,
        "limitations": ["模拟服务明确返回成功，未模拟镜头、实际中断到达或板级电路。",
                        "FlashSyncSu 的板级来源和到热靴触点的连接仍未知。",
                        "GPIO/中断寄存器均为桌面模拟内存，没有访问相机。"],
        "registerReference": "https://raw.githubusercontent.com/STMicroelectronics/cmsis-device-f1/master/Include/stm32f103xe.h",
    }
    (HERE / "research/mechanical-flash-handoff.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"callChecks": len(checks), "mechanicalCases": len(cases), "irqReplayVerified": True, "manualPulseReplayVerified": True, "hardwareRequests": 0}))
    return report
