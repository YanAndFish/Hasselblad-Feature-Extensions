"""编译纯编码函数，并用固定参考灯原始 Thumb 接收指令验证；无设备访问。"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / '.research-cache/x1d-1.25.0/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

SHA = '7eea75d17dea9d0ab8345ea4410148305ffb755b241132e3c5facd936a429dcb'
OUT = HERE / 'build/manual-power-offline'


def check():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Workspace mismatch')
    firmware = (HERE / 'build/receiver-reference/AD400pro_V1.50.bin').read_bytes()
    assert hashlib.sha256(firmware).hexdigest() == SHA
    # 真实的字节索引跳表：BC -> C352 -> C3B4，目标参数 20000133。
    assert (0xc161 + 2 * firmware[0xc161 - 0x3000 + 0xbc - 0xb0]) & ~1 == 0xc352
    assert struct.unpack_from('<I', firmware, 0xc4a8 - 0x3000)[0] == 0x20000133
    # 参考显示函数将 (80 - 参数) / 10 分解为分母及正向小数档。
    assert firmware[0x6630 - 0x3000:0x6636 - 0x3000].hex() == '5020401a0a21'
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key, name in [('ZIG_GLOBAL_CACHE_DIR', 'global-cache'), ('ZIG_LOCAL_CACHE_DIR', 'local-cache'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        env[key] = str(folder)
    zig = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    source = HERE / 'CodeTests/godox_manual_power.test.c'
    exe = OUT / 'godox_manual_power.test.exe'
    subprocess.run([str(zig), 'cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(exe)], env=env, check=True, capture_output=True, timeout=60)
    subprocess.run([str(exe)], check=True, capture_output=True, timeout=10)
    vectors = subprocess.run([str(exe), '--vectors'], check=True, capture_output=True, text=True, timeout=10).stdout.splitlines()
    assert len(vectors) == 405
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    u.mem_map(0, 0x20000)
    u.mem_write(0x3000, firmware)
    u.mem_map(0x20000000, 0x10000)
    stop = 0x1f000
    writes = []

    def code(uc, address, size, _):
        if address == stop:
            uc.emu_stop()
        elif not (0xc134 <= address < 0xc478 or 0xdef6 <= address < 0xdf10):
            raise AssertionError('Unexpected receiver execution: ' + hex(address))

    def write(uc, access, address, size, value, _):
        assert 0x20000000 <= address < 0x20010000
        if address < 0x2000e000:
            writes.append((address, size, value))

    u.hook_add(UC_HOOK_CODE, code)
    u.hook_add(UC_HOOK_MEM_WRITE, write)
    cases = 0
    for vector in vectors:
        frame = bytes.fromhex(vector)
        assert frame[0] == 0xa9 and frame[2] == 0xbc
        for matched in (True, False):
            for mode in (0, 1, 2):
                u.mem_write(0x20000000, bytes(0x1000))
                u.mem_write(0x20000123, bytes([frame[1] if matched else 0x0a + ((frame[1] - 0x0a + 1) % 5)]))
                u.mem_write(0x20000132, bytes([mode]))
                u.mem_write(0x20000133, b'\xfe')
                writes.clear()
                u.reg_write(arm.UC_ARM_REG_SP, 0x2000fff0)
                u.reg_write(arm.UC_ARM_REG_LR, stop | 1)
                for reg, value in zip((arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2), frame[1:]):
                    u.reg_write(reg, value)
                u.emu_start(0xc135, stop + 2, count=1000)
                assert u.reg_read(arm.UC_ARM_REG_PC) == stop
                assert u.reg_read(arm.UC_ARM_REG_SP) == 0x2000fff0
                assert u.mem_read(0x20000133, 1)[0] == (frame[3] if matched else 0xfe)
                assert u.mem_read(0x20000132, 1)[0] == mode
                assert writes == ([(0x20000133, 1, frame[3])] if matched else [])
                cases += 1
    report = {'passed': True, 'reference': 'Godox AD400Pro V1.50', 'referenceSha256': SHA,
              'compiledEncodingVectors': len(vectors), 'originalReceiverInstructionCases': cases,
              'groupMismatchIgnored': True, 'modeUnchanged': True, 'flashRoutineReached': False,
              'nativeHardwareAccess': False, 'hardwareRequests': 0, 'transmitSchedulingImplemented': False,
              'installed': False, 'physicalLampPowerVerified': False,
              'sourceHashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               (Path(__file__), source, HERE / 'native/godox_manual_power.h')}}
    (OUT / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    check()
