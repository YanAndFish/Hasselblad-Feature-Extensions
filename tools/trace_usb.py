"""只读复核已固定哈希的官方 USB 两端代码，不执行固件或 PC DLL。"""
from pathlib import Path
import hashlib
import json
import struct
from inspect_phocus import Binary, HASHES
from inspect_phocus_pc import PCBinary, SHA256

ROOT = Path(__file__).resolve().parents[1]


def run():
    firmware = Binary()
    bridge = Binary('msg2dbus')
    desktop = PCBinary()
    descriptors = Binary('usb_bulk_raw_hbl')
    system = Binary('camera-system')
    checks = []
    expected = [
        ('msg2dbus', bridge, 0x3fec8, 'mov', 'x8, #3'),
        ('msg2dbus', bridge, 0x3fecc, 'movk', 'x8, #0x805, lsl #16'),
        ('msg2dbus', bridge, 0x3fedc, 'mov', 'w1, #0xe'),
        ('msg2dbus', bridge, 0x3fee8, 'bl', '#0x4d460'),
        ('msg2dbus', bridge, 0x10aed8, 'ldrb', 'w1, [x20, #4]'),
        ('msg2dbus', bridge, 0x10aedc, 'add', 'x8, x20, #5'),
        ('msg2dbus', bridge, 0x47ae0, 'mov', 'w1, #0x400'),
        ('phocus', firmware, 0x90cd0, 'ldrh', 'w21, [x8]'),
        ('phocus', firmware, 0x8c738, 'ldrh', 'w8, [x20]'),
        ('phocus', firmware, 0x8c73c, 'strh', 'w8, [x19]'),
        ('phocus', firmware, 0x6c9c8, 'subs', 'w25, w25, w22'),
        ('phocus', firmware, 0x6c9d0, 'csel', 'x22, x9, xzr, eq'),
        ('phocus', firmware, 0x91184, 'cmp', 'w9, #1'),
        ('phocus', firmware, 0x91188, 'cset', 'w9, eq'),
        ('phocus', firmware, 0x9118c, 'mov', 'w11, #2'),
        ('phocus', firmware, 0x9121c, 'mov', 'w11, #4'),
        ('PhocusApi64.dll', desktop, 0x1805c8050, 'cmp', 'dword ptr [r13 + 0x4b0], 2'),
        ('PhocusApi64.dll', desktop, 0x1805cbe17, 'mov', 'dword ptr [rsi + 0x4b0], 2'),
        ('PhocusApi64.dll', desktop, 0x1805cc676, 'mov', 'dword ptr [r8 + 0x8c8], 0x30004'),
        ('PhocusApi64.dll', desktop, 0x1805cc681, 'mov', 'word ptr [r8 + 0x8cc], 0x508'),
        ('PhocusApi64.dll', desktop, 0x1805c8090, 'mov', 'byte ptr [rbp - 0x4c], r14b'),
        ('PhocusApi64.dll', desktop, 0x1805c80f6, 'lea', 'ecx, [r14 + 5]'),
        ('PhocusApi64.dll', desktop, 0x1805c8fb0, 'call', 'qword ptr [rax + 0x68]'),
        ('PhocusApi64.dll', desktop, 0x1805bab67, 'movzx', 'edx, byte ptr [rcx + 0xc9]'),
        ('PhocusApi64.dll', desktop, 0x1805ba600, 'movzx', 'eax, byte ptr [rcx + 0xc8]'),
        ('PhocusApi64.dll', desktop, 0x1805bb838, 'mov', 'byte ptr [r15 + 0xc8], r9b'),
        ('PhocusApi64.dll', desktop, 0x1805bb83f, 'mov', 'byte ptr [r15 + 0xc9], dl'),
        ('PhocusApi64.dll', desktop, 0x1805bae73, 'cmovbe', 'r8d, r9d'),
        ('PhocusApi64.dll', desktop, 0x1805bae7a, 'mov', 'dword ptr [rdx + 0x14], r8d'),
    ]
    for name, binary, address, mnemonic, operands in expected:
        instruction = next(binary.cs.disasm(binary.read(address, 16), address))
        if instruction.mnemonic != mnemonic or instruction.op_str != operands:
            raise ValueError(f'USB evidence changed at {name}:{address:#x}')
        checks.append({'binary': name, 'address': hex(address), 'instruction': mnemonic + ' ' + operands, 'passed': True})
    for address, expected_string in [(0x1824bf, b's\0S\0'), (0x1824c7, b'%d,\0'), (0x1824d0, b'%d\0')]:
        if firmware.read(address, len(expected_string)) != expected_string:
            raise ValueError('ToString encoding evidence changed')
        checks.append({'binary': 'phocus', 'address': hex(address), 'kind': 'string-format', 'passed': True})
    if struct.unpack('<Q', desktop.read(0x180ebccb8 + 0x68, 8))[0] != 0x1805bab50:
        raise ValueError('Control vtable entry changed')
    checks.append({'binary': 'PhocusApi64.dll', 'address': '0x180ebcd20', 'kind': 'control-vtable', 'passed': True})
    for address, path in [(0x157bf2, '/ep2'), (0x157bfc, '/ep4')]:
        if bridge.read(address, 8).decode('utf-16le') != path:
            raise ValueError('Camera control endpoint path changed')
        checks.append({'binary': 'msg2dbus', 'address': hex(address), 'kind': 'control-path', 'value': path, 'passed': True})
    for address, stride in [(0x1960, 9), (0x198d, 9), (0x19ba, 15)]:
        header = descriptors.read(address, 9)
        ids = [descriptors.read(address + 9 + i * stride, 3)[2] for i in range(4)]
        if header[:8] != bytes([9,4,0,0,4,255,0,0]) or ids != [1,2,0x81,0x82]:
            raise ValueError('FunctionFS endpoint ordering changed')
        checks.append({'binary': 'usb_bulk_raw_hbl', 'address': hex(address), 'kind': 'descriptor-endpoint-order', 'ids': ids, 'passed': True})
    if system.read(0x39aeaf, 3) != b'v%1':
        raise ValueError('System version_id prefix changed')
    checks.append({'binary': 'camera-system', 'address': '0x39aeaf', 'kind': 'version-prefix-format', 'passed': True})
    source_files = ['WinUsbReadOnly.cs', 'Program.cs']
    report = {
        'firmware': '4.2.0', 'desktopVersion': '4.1.1', 'hardwareRequests': 0,
        'binaries': {'phocus': HASHES['phocus'], 'camera-system': HASHES['camera-system'], 'msg2dbus': HASHES['msg2dbus'], 'usb_bulk_raw_hbl': HASHES['usb_bulk_raw_hbl'], 'PhocusApi64.dll': SHA256},
        'checks': checks,
        'nativeSourceSha256': {name: hashlib.sha256((ROOT / 'native' / name).read_bytes()).hexdigest() for name in source_files},
        'note': '只证明所列固定官方输入的静态字节与本次实现来源；不证明实机固件版本或物理连接成功。',
    }
    (ROOT / 'research/usb-protocol-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': True, 'checks': len(checks), 'hardwareRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    run()
