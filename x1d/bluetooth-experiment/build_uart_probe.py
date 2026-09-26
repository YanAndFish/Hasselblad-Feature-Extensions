"""固定 UART5 一次身份查询的离线构建；不运行实机入口。"""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / 'build/uart-probe-r1'
ZIG = ROOT / '.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    if Path.cwd().resolve() != ROOT:
        raise SystemExit('workspace mismatch')
    for name in ('tmp', 'zig-local', 'zig-global'):
        (BUILD / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TEMP=str(BUILD/'tmp'), TMP=str(BUILD/'tmp'),
               ZIG_LOCAL_CACHE_DIR=str(BUILD/'zig-local'), ZIG_GLOBAL_CACHE_DIR=str(BUILD/'zig-global'))
    sources = [HERE/'native/bt_hci.c', HERE/'native/uart_probe.c']
    base = [str(ZIG),'cc','-O2','-s','-Wall','-Wextra','-Werror','-std=c11']
    outputs = {}
    for target, flags, name in (
        ('host', [], 'uart-probe-self-test.exe'),
        ('arm', ['-target','arm-linux-musleabihf','-mcpu=cortex_a9','-marm','-static'], 'uart-probe')):
        p = BUILD/name
        subprocess.run(base+flags+list(map(str,sources))+['-o',str(p)],cwd=HERE,env=env,check=True)
        outputs[target] = p
    test = subprocess.run([str(outputs['host']),'--self-test'],capture_output=True,text=True,check=True,env=env)
    denied = subprocess.run([str(outputs['host']),'--scan'],capture_output=True,text=True,env=env)
    assert denied.returncode == 2
    data = outputs['arm'].read_bytes()
    assert data[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H',data,18)[0] == 40
    start = struct.unpack_from('<I',data,28)[0]
    stride, count = struct.unpack_from('<HH',data,42)
    assert not any(struct.unpack_from('<I',data,start+i*stride)[0] == 3 for i in range(count))
    report = {'purpose':'single fixed UART5 HCI version probe; connection hypothesis unverified',
              'host_self_test':test.stdout.strip(),'compiler_sha256':sha(ZIG),
              'sources':{str(p.relative_to(HERE)):sha(p) for p in sources+[HERE/'native/bt_hci.h',Path(__file__).resolve()]},
              'artifacts':{k:{'path':str(p.relative_to(HERE)),'bytes':p.stat().st_size,'sha256':sha(p)} for k,p in outputs.items()}}
    (BUILD/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
