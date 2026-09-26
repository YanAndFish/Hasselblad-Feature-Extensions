"""独立回显计时程序；不修改已装 worker、FARM 或无线固件。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/farm-roundtrip-probe'
CACHE=ROOT/'.research-cache/x1d-1.25.0'

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    OUT.mkdir(exist_ok=True)
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    qt=CACHE/'qt-public/qtbase-opensource-src-5.5.1'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(HERE/'build/zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(HERE/'build/zig-local-cache'),PYTHONDONTWRITEBYTECODE='1')
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    source=HERE/'native/farm_roundtrip_probe.cpp'
    obj=OUT/'probe.o'; executable=OUT/'farm-roundtrip-probe'
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(HERE/'build/include'),'-isystem',str(qt/'include'),'-I',str(qt/'mkspecs/linux-arm-gnueabi-g++'),
           '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra']
    libs=[CACHE/'baseline'/p for p in ('usr/lib/libQt5Core.so.5.5.1','usr/lib/libQt5DBus.so.5.5.1',
          'usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libc-2.22.so')]
    commands=[['c++','-std=c++11']+flags+['-c',str(source),'-o',str(obj)],
              ['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-no-pie','-Wl,--no-undefined','-Wl,-s',
               '-Wl,-T,'+str(layout),str(obj)]+[str(p) for p in libs]+['-o',str(executable)]]
    for command in commands:
        result=subprocess.run([str(compiler)]+command,env=env,capture_output=True,text=True,timeout=60)
        if result.returncode: raise RuntimeError(result.stderr)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    elf=ArmElf(executable.read_bytes())
    rel=elf.elf.get_section_by_name('.rel.dyn'); plt=elf.elf.get_section_by_name('.rel.plt')
    if rel['sh_addr']+rel['sh_size']!=plt['sh_addr']: raise RuntimeError('Noncontiguous relocations')
    report={'compiled':True,'sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'bytes':executable.stat().st_size,
            'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'relocationsContiguous':True,
            'targetChecked':False,'measurements':0,'hardwareRequests':0,'newFarmCode':False,'newRadioCode':False}
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__': print(build())
