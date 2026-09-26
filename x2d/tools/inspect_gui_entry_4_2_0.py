"""静态复核 X2D 4.2.0 页面入口，只读固件；不执行 ARM 程序或访问设备。"""
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from firmware_image import system_file, system_elf, instruction

GUI_SHA = '16391452abdc69de9e0807e065c0f4ab3f1ccb5fc288f6fc4e6f5cb3bdca12e0'
SHELL_SHA = 'e6c7e863df6ac6148d1d34ea7692c33215503a30770295ea62e70d13b669e272'


def resource(binary, tree_address, names_address, data_address, node, expected_name):
    row = binary.read(tree_address + node * 22, 22)
    name_offset, flags = struct.unpack_from('>IH', row)
    length = struct.unpack('>H', binary.read(names_address + name_offset, 2))[0]
    name = binary.read(names_address + name_offset + 6, length * 2).decode('utf-16-be')
    if name != expected_name or flags != 0:
        raise ValueError('资源名称或未压缩文件标志不匹配')
    offset = struct.unpack_from('>I', row, 10)[0]
    size = struct.unpack('>I', binary.read(data_address + offset, 4))[0]
    return binary.read(data_address + offset + 4, size).decode('utf-8')


def main():
    gui = system_elf('/bin/camera-gui', GUI_SHA)
    shell = system_elf('/lib64/weston/eagle-shell.so', SHELL_SHA)
    checks = []

    def check(name, result):
        if not result:
            raise AssertionError(name)
        checks.append(name)

    def ins(binary, address, mnemonic, operands):
        actual = instruction(binary, address)
        check(f'{address:#x}: {mnemonic} {operands}', (actual.mnemonic, actual.op_str) == (mnemonic, operands))

    rc = system_file('/etc/init/camera-gui.rc')
    check('GUI 启动配置哈希', hashlib.sha256(rc).hexdigest() == '1d6a8f9e41e269be38b3fb9ba53f4c47d18007f413c90893fdfa9d7542d1f688')
    check('原厂 GUI 使用 Wayland EGL', b'camera-gui -platform wayland-egl --fullscreen' in rc)
    check('测试模式切换停启 GUI', b'stop camera-gui' in rc and b'start camera-sutest-gui' in rc)
    check('Weston 启动配置哈希', hashlib.sha256(system_file('/etc/init/weston.rc')).hexdigest() == '60c2c61de0cac28178a1e670c9a064a83760106161694bc0ef86b9a439d86b73')
    check('正常页面固定资源前缀', gui.read(0x14d1f0f, 13) == b'qrc:/app/qml/')
    check('正常页面名称', gui.read(0x14d1f75, 8) == b'main.qml')
    ins(gui, 0x3344ec, 'add', 'x1, x1, #0xf0f')
    ins(gui, 0x3349b8, 'add', 'x1, x1, #0xf75')
    ins(gui, 0x3349e0, 'bl', '#0x682ab8')
    check('显示窗口角色字串', shell.read(0x13600, 12) == b'gui\0overlay\0')
    ins(shell, 0x9da8, 'bl', '#0x78a8')
    ins(shell, 0x9ddc, 'mov', 'w8, #1')
    ins(shell, 0x9dd4, 'mov', 'w8, #2')
    for address in [0x88e4, 0x89dc, 0x8ad4]:
        ins(shell, address, 'cmp', 'w13, #1')
    ins(shell, 0x8b68, 'bl', '#0x77e8')
    ins(shell, 0xa35c, 'bl', '#0x7868')
    ins(shell, 0xa370, 'b', '#0x8f48')
    ins(shell, 0x853c, 'cmp', 'x8, x21')
    ins(shell, 0x8540, 'b.eq', '#0x8564')
    check('私有背景协议拒绝未匹配客户端', b'permission to bind victory_shell denied' in shell.data)
    print(json.dumps({
        'model': 'X2D 100C', 'firmware': '4.2.0', 'source': 'official-firmware-static',
        'generatedUtc': datetime.now(timezone.utc).isoformat(),
        'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'inputSha256': {'camera-gui': GUI_SHA, 'eagle-shell.so': SHELL_SHA},
        'result': 'pass', 'checks': checks, 'deviceAccesses': 0,
        'limitations': ['没有显示或输入实机验证', '没有新增页面可装载程序', '没有射频实现', '未证明外部 QML 页面扩展接口'],
    }, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
