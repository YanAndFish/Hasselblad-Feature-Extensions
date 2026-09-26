"""固定官方 SPC 的 SPI 回复边界复现；仅运行原 Thumb 代码与合成外设。

不打开设备、不读取实机寄存器。软件地址和标志掩码来自输入固件；
合成状态流不能当作实机曾发生超时或物理积分时序的证据。
"""
import hashlib
import struct

import unicorn
from unicorn import arm_const as arm

SPC_SHA = "dc0a77dd46f7e07a5640fb9407e077b8f544871d007f9c3fa4233ea5fc8e7616"
ROM, RAM, SPI, GPIO = 0x08000000, 0x20000000, 0x40013000, 0x40020000
STACK, REQUEST = RAM + 0x7800, RAM + 0x6000
ENTRY, STOP = ROM + 0x4F50, ROM + 0x4F84
ALLOWED = ((ENTRY, STOP), (ROM + 0x65C0, ROM + 0x6680),
           (ROM + 0x64D8, ROM + 0x652A), (ROM + 0x59E4, ROM + 0x59FE),
           (ROM + 0x0778, ROM + 0x0780), (ROM + 0x0A5A, ROM + 0x0A88))


def run_case(spc, *, start=2, data=bytes.fromhex("0300000e11"), fault=None,
             fault_byte_call=3):
    """fault：初次就绪、某一字节等待接收、最终忙等待；不替换驱动函数。"""
    if type(spc) is not bytes or len(spc) != 48455 or hashlib.sha256(spc).hexdigest() != SPC_SHA:
        raise ValueError("fixed official SPC required")
    if type(start) is not int or not 0 <= start <= 255 or type(data) is not bytes or not 1 <= len(data) <= 256 - start:
        raise ValueError("invalid synthetic SPI request")
    if fault not in (None, "initial_ready", "byte_receive", "final_busy"):
        raise ValueError("unknown synthetic fault")
    if type(fault_byte_call) is not int or fault_byte_call < 1:
        raise ValueError("invalid byte call")
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
    uc.mem_map(ROM, 0xC000, unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
    uc.mem_write(ROM, spc)
    uc.mem_map(RAM, 0x8000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
    uc.mem_map(SPI, 0x1000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
    uc.mem_map(GPIO, 0x1000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
    uc.mem_write(RAM + 0x5246, b"\x01\x01")
    request = struct.pack("<HBBBHB", 0x23, 1, 2, start, len(data), 2) + data
    uc.mem_write(REQUEST, request)
    for register, value in ((arm.UC_ARM_REG_SP, STACK), (arm.UC_ARM_REG_R4, REQUEST),
                            (arm.UC_ARM_REG_R6, 1), (arm.UC_ARM_REG_LR, STOP | 1)):
        uc.reg_write(register, value)
    trace = {"byte_calls": 0, "byte_returns": [], "data_register_writes": [],
             "select_writes": [], "status_reads": 0, "fault_status_reads": 0,
             "instructions": 0, "writes_while_deselected": 0}
    selected = False

    def code_guard(machine, address, size, context):
        if not any(a <= address < b for a, b in ALLOWED):
            raise RuntimeError("unreviewed original instruction " + hex(address))
        trace["instructions"] += 1
        if address == ROM + 0x64F8:
            trace["byte_calls"] += 1
        elif address == ROM + 0x6528:
            trace["byte_returns"].append(machine.reg_read(arm.UC_ARM_REG_R0))

    def read_guard(machine, access, address, size, value, context):
        if SPI <= address < SPI + 0x1000:
            if address not in (SPI, SPI + 8, SPI + 12) or size != 2:
                raise RuntimeError("unexpected synthetic peripheral read")
            if address == SPI + 8:
                mask = machine.reg_read(arm.UC_ARM_REG_R1)
                status = 3
                inject = ((fault == "initial_ready" and trace["byte_calls"] == 0 and mask == 2) or
                          (fault == "byte_receive" and trace["byte_calls"] == fault_byte_call and mask == 1) or
                          (fault == "final_busy" and mask == 0x80))
                if inject:
                    status = 0 if fault == "initial_ready" else 2 if fault == "byte_receive" else 0x83
                    trace["fault_status_reads"] += 1
                machine.mem_write(address, struct.pack("<H", status))
                trace["status_reads"] += 1
        elif GPIO <= address < GPIO + 0x1000:
            raise RuntimeError("unexpected synthetic GPIO read")

    def write_guard(machine, access, address, size, value, context):
        nonlocal selected
        if STACK - 0x200 <= address and address + size <= STACK + 0x20:
            return
        if address == SPI and size == 2:
            return
        if address == SPI + 12 and size == 2:
            trace["data_register_writes"].append(value)
            trace["writes_while_deselected"] += int(not selected)
            return
        if address in (GPIO + 0x18, GPIO + 0x1A) and size == 2 and value == 0x8000:
            selected = address == GPIO + 0x1A
            trace["select_writes"].append({"selected": selected, "after_data_writes": len(trace["data_register_writes"])})
            return
        raise RuntimeError("unexpected write " + hex(address))

    uc.hook_add(unicorn.UC_HOOK_CODE, code_guard)
    uc.hook_add(unicorn.UC_HOOK_MEM_READ, read_guard)
    uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, write_guard)
    uc.emu_start(ENTRY | 1, STOP, timeout=3_000_000, count=500_000)
    if uc.reg_read(arm.UC_ARM_REG_PC) != STOP or uc.reg_read(arm.UC_ARM_REG_SP) != STACK:
        raise RuntimeError("original response path did not finish")
    command, source, destination, status = struct.unpack("<HBBB", uc.mem_read(STACK + 8, 5))
    if (command, source, destination) != (0x24, 2, 1):
        raise RuntimeError("response header mismatch")
    return {"fault": fault, "start_address": start, "payload_hex": data.hex(),
            "response_command": command, "response_status": status,
            "selected_at_return": selected,
            "spi_control_bit_0x40_at_return": bool(struct.unpack("<H", uc.mem_read(SPI, 2))[0] & 0x40),
            **trace}


def verify(spc):
    cases = [run_case(spc),
             run_case(spc, start=0x7F, data=b"\x12\x34\x56"),
             run_case(spc, fault="initial_ready"),
             run_case(spc, fault="byte_receive", fault_byte_call=1),
             run_case(spc, fault="byte_receive", fault_byte_call=3),
             run_case(spc, fault="final_busy")]
    normal, split, initial, header_fault, data_fault, busy = cases
    assert normal["response_status"] == 0 and normal["byte_returns"] == [0] * 7
    assert normal["data_register_writes"] == [2, 2, 3, 0, 0, 14, 17]
    assert not normal["selected_at_return"] and not normal["spi_control_bit_0x40_at_return"]
    assert split["data_register_writes"] == [2, 0x7F, 0x12, 2, 0x80, 0x34, 0x56]
    assert split["response_status"] == 0 and not split["writes_while_deselected"]
    assert initial["response_status"] == 1 and not initial["data_register_writes"]
    for case in (initial, header_fault, data_fault, busy):
        assert case["fault_status_reads"] == 0x1001
    for case in (header_fault, data_fault):
        assert case["response_status"] == 0 and case["byte_returns"].count(1) == 1
        assert case["writes_while_deselected"] > 0 and not case["selected_at_return"]
    assert busy["response_status"] == 1 and busy["selected_at_return"]
    assert busy["spi_control_bit_0x40_at_return"]
    for bad in (spc[:-1], b"not firmware"):
        try:
            run_case(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid firmware accepted")
    return {"source_sha256": SPC_SHA, "original_entry": hex(ENTRY),
            "original_stop": hex(STOP), "cases": cases, "passed": True,
            "case_count": len(cases), "hardware_requests": 0,
            "peripheral_inputs_are_synthetic": True,
            "normal_reply_waits_for_final_busy_flag_clear": True,
            "byte_helper_failure_can_be_ignored_by_outer_driver": True,
            "camera_failure_observed": False, "physical_integration_verified": False}
