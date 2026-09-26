"""本候选独立证据目录；仅显式派发固定的只读准备检查。"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'build'
TRANSPORT = ROOT / 'x1d/wireless-flash/research/mechanical_sync_session.py'
TRANSPORT_SHA = '2ebbadf244613f64641266342679743b172899555ff6757f9cfded523433528a'

class Session:
    def __init__(self, label):
        if Path.cwd().resolve() != ROOT:
            raise RuntimeError('workspace mismatch')
        if hashlib.sha256(TRANSPORT.read_bytes()).hexdigest() != TRANSPORT_SHA:
            raise RuntimeError('transport source changed')
        OUT.mkdir(exist_ok=True)
        spec = importlib.util.spec_from_file_location('coexist_verified_transport', TRANSPORT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.HERE = HERE
        name = label + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
        self.transport = module.Session(name)
        folder = OUT / 'sessions'
        folder.mkdir(exist_ok=True)
        self.transport.output = folder / name

    def command(self, name, command):
        if not 0 < len(command.encode('ascii')) <= 231 or '\n' in command or '\0' in command:
            raise ValueError('command boundary')
        return self.transport.command(name, command, 15000)

def inspect():
    session = Session('readonly-prerequisites')
    # 不读取网络名称、密码、序列号、照片或整个网络配置。
    commands = (
        ('tools', 'for n in /usr/bin/wl /usr/sbin/iw /sbin/ip /usr/sbin/wpa_supplicant /sbin/udhcpc;do test ! -x "$n" || echo "$n";done'),
        ('gui', 'systemctl show victory-gui -p ActiveState -p DropInPaths'),
        ('radio-module', 'cat /sys/module/brcmfmac/parameters/firmware_path'),
        ('gui-hash', 'sha256sum /usr/bin/victory-gui'),
        ('wl-hash', 'sha256sum /usr/bin/wl'),
        ('supplicant-hash', 'sha256sum /usr/sbin/wpa_supplicant'),
    )
    for name, command in commands:
        result = session.command(name, command)
        print(json.dumps({'check': name, 'exit': result['exit_code'], 'output': result['output']}, ensure_ascii=False))
        if result['exit_code'] != 0:
            raise RuntimeError('read-only prerequisite failed; no automatic retry')

if __name__ == '__main__':
    if sys.argv[1:] == ['--inspect-tools']:
        inspect()
    elif not sys.argv[1:]:
        print(json.dumps({'offline': True, 'hardwareRequests': 0}))
    else:
        raise SystemExit('Only --inspect-tools is implemented; no install or radio command entry.')
