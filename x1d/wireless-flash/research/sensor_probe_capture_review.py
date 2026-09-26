"""复现 GFP2 实录暴露的软件缓冲寿命问题；只执行固定 FARM 与合成 RAM。"""
import hashlib
import struct

import unicorn
from unicorn import arm_const as arm

FARM_SHA = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
CONFIG, REGISTERS, STACK, STOP = 0x1001000, 0x6DB2E8, 0x100F000, 0x100F800
ALLOWED = ((0x22F9F0, 0x2305CC), (0x226974, 0x226B90), (0x15ED40, 0x15EED4),
           (0x22F69C, 0x22F9F0), (0x234578, 0x2348F4), (0x233C84, 0x2341F4))


def check_constructor_overwrite(farm):
    if len(farm) != 1808280 or hashlib.sha256(farm).hexdigest() != FARM_SHA:
        raise ValueError("fixed FARM mismatch")
    machine = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
    machine.mem_map(0x100000, (len(farm) + 4095) & ~4095,
                    unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
    machine.mem_write(0x100000, farm)
    machine.mem_map(REGISTERS & ~4095, 4096, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
    machine.mem_map(0x1000000, 0x10000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
    # 合成的 1 秒编码 N=3/R=4366；并非从照片或机身读取。
    seed = bytes.fromhex("04200300000e1100")
    machine.mem_write(REGISTERS, seed)
    machine.mem_write(CONFIG + 0x98, struct.pack("<I", 3))
    for register, value in ((arm.UC_ARM_REG_C1_C0_2, 0xF << 20),
                            (arm.UC_ARM_REG_FPEXC, 0x40000000),
                            (arm.UC_ARM_REG_R0, 6), (arm.UC_ARM_REG_R1, 0),
                            (arm.UC_ARM_REG_R2, CONFIG), (arm.UC_ARM_REG_SP, STACK),
                            (arm.UC_ARM_REG_LR, STOP)):
        machine.reg_write(register, value)
    writes, executed = [], set()

    def code_guard(uc, address, size, context):
        if not any(a <= address < b for a, b in ALLOWED):
            raise RuntimeError("unreviewed instruction " + hex(address))
        executed.add(address)

    def write_guard(uc, access, address, size, value, context):
        if not any(a <= address and address + size <= b for a, b in (
                (CONFIG, CONFIG + 0xD0), (REGISTERS, REGISTERS + 256),
                (STACK - 4096, STACK))):
            raise RuntimeError("unexpected write " + hex(address))
        writes.append((address, size))

    machine.hook_add(unicorn.UC_HOOK_CODE, code_guard)
    machine.hook_add(unicorn.UC_HOOK_MEM_WRITE, write_guard)
    machine.emu_start(0x22F9F0, STOP, timeout=1_000_000, count=100_000)
    assert machine.reg_read(arm.UC_ARM_REG_PC) == STOP
    assert machine.reg_read(arm.UC_ARM_REG_R0) == 0
    assert machine.reg_read(arm.UC_ARM_REG_SP) == STACK
    result = bytes(machine.mem_read(REGISTERS, 8))
    config_n = struct.unpack("<I", machine.mem_read(CONFIG + 0x98, 4))[0]
    assert result == bytes.fromhex("0420000000010000")
    assert config_n == 3
    assert not any(a < CONFIG + 0x9C and a + s > CONFIG + 0x98 for a, s in writes)
    return {"source_sha256": FARM_SHA, "entry": "0x22f9f0", "mode": 6,
            "register_head_before_hex": seed.hex(), "register_head_after_hex": result.hex(),
            "config_n_before": 3, "config_n_after": config_n,
            "register_template_overwrites_previous_encoding": True,
            "constructor_alone_explains_live_config_n_zero": False,
            "unique_instructions": len(executed), "hardware_requests": 0,
            "physical_timing_measured": False}
