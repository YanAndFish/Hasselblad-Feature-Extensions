"""原厂镜头封包片段离线执行；不连接相机、不修改固件。"""
import hashlib
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / '.research-cache/x1d-1.25.0/python'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_SL

def decode(name, digest):
    raw = (HERE / (name + '.hex')).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    memory, upper = {}, 0
    for line in raw.decode('ascii').splitlines():
        if not line:
            continue
        assert line.startswith(':')
        record = bytes.fromhex(line[1:])
        assert sum(record) % 256 == 0 and len(record) == record[0] + 5
        length, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        payload = record[4:4 + length]
        if kind == 4:
            upper = int.from_bytes(payload, 'big') << 16
        elif kind == 0:
            for index, value in enumerate(payload):
                memory[upper + address + index] = value
        elif kind == 1:
            break
        else:
            assert kind in (3, 5), kind
    start, end = min(memory), max(memory) + 1
    return start, bytes(memory.get(a, 0) for a in range(start, end))

def main():
    base, code = decode('XCD_FW_1601245_0_6_4', '6206ef561d4047d048be1f23c53eb71e7c03b759612cd5df815ef99ff66eddff')
    assert base == 0x08000800
    models = [
        ('XCD30_1601327_21_0_1', '1129e742b8f99162abc2d15d88b8617f79402cf250d0615832f6659c89ba614c', (23, 39, 39, 18)),
        ('XCD90_1601210_21_0_1', '0377444e770f9671fc803725906f041a8e956fc98a2a60740c5407435b6d6346', (75, 127, 127, 59)),
    ]
    count = 0
    for name, digest, expected in models:
        cfgbase, cfg = decode(name, digest)
        assert cfgbase == 0x1000
        assert struct.unpack_from('<4H', cfg, 0x26c) == expected
        for flag in (0, 1, 5, 9, 13):
            u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
            u.mem_map(0x08000000, 0x20000)
            u.mem_map(0x20000000, 0x20000)
            u.mem_map(0x08100000, 0x10000)
            u.mem_write(base, code)
            # 合成配置映射及运行状态；不宣称等于实机状态。
            u.mem_write(0x08000064, struct.pack('<I', 0x08100000))
            u.mem_write(0x08101000, cfg)
            u.mem_write(0x2000ab10, bytes((flag, 0, 0, 1)))
            for reg, value in ((UC_ARM_REG_R3, 0x08000040), (UC_ARM_REG_R4, 0x2000ad21),
                               (UC_ARM_REG_R1, 0x2000ab10), (UC_ARM_REG_SL, 0x2000ab10)):
                u.reg_write(reg, value)
            u.emu_start(0x08005c55, 0x08005c96, count=100)
            actual = struct.unpack('>HH', bytes(u.mem_read(0x2000ad23, 4)))
            index = ((flag >> 2) & 7) if flag & 1 else 0
            assert actual == (expected[0], expected[index]), (name, flag, actual)
            print(name, 'state_flags=', flag, 'reply_fields=', actual)
            count += 1
    print('PASS:', count, 'original-instruction cases; no camera I/O')

if __name__ == '__main__':
    main()
