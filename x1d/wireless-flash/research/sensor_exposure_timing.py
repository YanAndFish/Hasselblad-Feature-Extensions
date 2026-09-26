"""固定 X1D 1.25.0 FARM 的离线滚动曝光参数复核；不连接设备。"""

import hashlib
import struct

import unicorn
from unicorn import arm_const


FARM_SHA256 = "317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca"
CODE_BASE = 0x100000
ALLOWED_CODE = (
    (0x233A4C, 0x233C84),  # 曝光参数换算及 SVR 编码
    (0x15AE34, 0x15AE70),  # 原厂链接的整数除法入口
    (0x15AF54, 0x15AF90),
    (0x15C880, 0x15C994),
)


def verify_farm(farm):
    if len(farm) != 1808280 or hashlib.sha256(farm).hexdigest() != FARM_SHA256:
        raise ValueError("FARM 与固定官方来源不匹配")


def emulate_rolling(farm, exposure_us, h_period, v_period=6320):
    """运行原换算函数及实际除法代码；结果是寄存器编码，非感光测量。"""
    verify_farm(farm)
    if not (
        isinstance(exposure_us, int)
        and 0 <= exposure_us <= 100_000_000
        and isinstance(h_period, int)
        and 1 <= h_period <= 65535
        and isinstance(v_period, int)
        and 2 < v_period < 16384
    ):
        raise ValueError("输入超出本离线模型的范围")
    # 本次仅支持较小的合成案例，避免原函数逐帧循环过长。
    if exposure_us * 54 // h_period > v_period * 4095:
        raise ValueError("合成案例的帧数超出本复核范围")

    machine = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_ARM)
    machine.mem_map(
        CODE_BASE,
        (len(farm) + 4095) & ~4095,
        unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC,
    )
    machine.mem_write(CODE_BASE, farm)
    machine.mem_map(
        0x1000000, 0x10000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE
    )
    config, registers, return_address = 0x1001000, 0x1002000, 0x100F800
    machine.mem_write(config + 0x70, struct.pack("<I", h_period))
    machine.mem_write(config + 0x78, struct.pack("<I", v_period))
    # 高位设为非零，检查原函数保留相邻字段；不是相机实读寄存器。
    initial_registers = bytes.fromhex("0424a05a004055") + bytes(249)
    machine.mem_write(registers, initial_registers)
    machine.reg_write(arm_const.UC_ARM_REG_C1_C0_2, 0xF << 20)
    machine.reg_write(arm_const.UC_ARM_REG_FPEXC, 0x40000000)
    for register, value in (
        (arm_const.UC_ARM_REG_R0, exposure_us & 0xFFFFFFFF),
        (arm_const.UC_ARM_REG_R1, exposure_us >> 32),
        (arm_const.UC_ARM_REG_R2, config),
        (arm_const.UC_ARM_REG_R3, registers),
        (arm_const.UC_ARM_REG_SP, 0x100F000),
        (arm_const.UC_ARM_REG_LR, return_address),
    ):
        machine.reg_write(register, value)

    executed = set()

    def guard_code(emulator, address, size, user_data):
        if not any(start <= address < end for start, end in ALLOWED_CODE):
            raise RuntimeError(f"进入未审核的函数位置：{address:#x}")
        executed.add(address)

    machine.hook_add(unicorn.UC_HOOK_CODE, guard_code)
    machine.emu_start(0x233AC0, return_address, timeout=1_000_000, count=100_000)
    if machine.reg_read(arm_const.UC_ARM_REG_PC) != return_address:
        raise RuntimeError("原函数未在限制内返回")

    encoded = bytes(machine.mem_read(registers, 256))
    extra_frames = struct.unpack("<I", machine.mem_read(config + 0x98, 4))[0]
    line_code = encoded[5] | ((encoded[6] & 0x3F) << 8)
    exposure_lines = exposure_us * 54 // h_period
    expected_frames = max(0, (exposure_lines - 1) // v_period)
    expected_code = max(
        2, min(v_period - 2, (expected_frames + 1) * v_period - exposure_lines)
    )
    if (extra_frames, line_code) != (expected_frames, expected_code):
        raise AssertionError("原 ARM 函数与独立整数表达式不一致")
    if encoded[2] | ((encoded[3] & 15) << 8) != extra_frames & 0xFFF:
        raise AssertionError("SVR 编码不一致")
    if encoded[3] & 0xF0 != 0x50 or encoded[6] & 0xC0 != 0x40:
        raise AssertionError("相邻寄存器位被改变")
    if any(
        encoded[index] != value
        for index, value in enumerate(initial_registers)
        if index not in (2, 3, 5, 6)
    ):
        raise AssertionError("出现预期之外的寄存器缓冲修改")
    returned = machine.reg_read(arm_const.UC_ARM_REG_R0) | (
        machine.reg_read(arm_const.UC_ARM_REG_R1) << 32
    )
    if returned != exposure_us:
        raise AssertionError("返回值不是原输入曝光时长")
    return {
        "exposure_us": exposure_us,
        "h_period": h_period,
        "v_period": v_period,
        "extra_frames": extra_frames,
        "line_code": line_code,
        "unique_instructions": len(executed),
        "physical_timing_measured": False,
    }


def analyze(farm):
    """两种静态行周期、七个合成时长；零值只检查钳制边界。"""
    return [
        emulate_rolling(farm, exposure_us, h_period)
        for h_period in (2582, 3206)
        for exposure_us in (0, 1000, 100000, 250000, 500000, 1000000, 2000000)
    ]
