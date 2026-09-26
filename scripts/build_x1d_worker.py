"""显式输入交叉编译 X1D 无线 worker 库；不运行目标库，不安装。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid
from build_contract import validate_radio_tables, write_report

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'x1d/combined-runtime/four-module-r1/persistent-r1/native'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig',required=True)
    parser.add_argument('--qtbase',type=Path,required=True,help='User-provided Qt 5.5.1 source headers')
    parser.add_argument('--target-root',type=Path,required=True,help='User-provided X1D 1.25.0 ARM runtime root')
    parser.add_argument('--radio-tables',type=Path,required=True)
    parser.add_argument('--build-dir',type=Path,required=True)
    a=parser.parse_args()
    qt=a.qtbase.resolve(); baseline=a.target_root.resolve(); tables=a.radio_tables.resolve(); out=a.build_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    run_id=str(uuid.uuid4())
    write_report(out/'worker-build.json', {'passed':False,'compiled':False,'runId':run_id,
                 'installed':False,'cameraUpdateBuilt':False,'deviceAccess':False})
    required=['usr/lib/libQt5Core.so.5.5.1','usr/lib/libstdc++.so.6.0.21',
              'lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so']
    libs=[baseline/name for name in required]
    for path in libs+[qt/'include/QtCore/qglobal.h',qt/'mkspecs/linux-arm-gnueabi-g++/qplatformdefs.h']:
        if not path.is_file(): raise ValueError('Missing explicit input: '+str(path))
    manifest=validate_radio_tables(tables)
    out.mkdir(parents=True,exist_ok=True)
    config=out/'include/QtCore';config.mkdir(parents=True,exist_ok=True)
    (config/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (config/'qfeatures.h').write_text('/* No additional feature overrides. */\n',encoding='ascii')
    layout=out/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'zig-global'),ZIG_LOCAL_CACHE_DIR=str(out/'zig-local'))
    obj=out/'formal_worker.o';library=out/('libhbl-flash-worker.'+run_id+'.pending.so')
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    subprocess.run([a.zig,'c++',*target,'-marm','-std=c++11','-O2','-fPIC','-fno-stack-protector',
                    '-DHBL_EXTERNAL_RADIO_TABLES','-I',str(tables),'-I',str(out/'include'),
                    '-isystem',str(qt/'include'),'-I',str(qt/'mkspecs/linux-arm-gnueabi-g++'),
                    '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion',
                    '-c',str(NATIVE/'formal_worker.cpp'),'-o',str(obj)],env=env,check=True,timeout=180)
    subprocess.run([a.zig,'cc',*target,'-shared','-Wl,--no-undefined','-Wl,-T,'+str(layout),
                    '-Wl,-soname,libhbl-flash-worker.so',str(obj),*[str(p) for p in libs],'-o',str(library)],
                   env=env,check=True,timeout=180)
    data=library.read_bytes()
    if data[:6]!=b'\x7fELF\x01\x01' or struct.unpack_from('<HH',data,16)!=(3,40):
        raise ValueError('Output is not ARM32 little-endian shared ELF')
    shoff=struct.unpack_from('<I',data,32)[0]
    entsize,count,names_index=struct.unpack_from('<HHH',data,46)
    sections=[struct.unpack_from('<10I',data,shoff+i*entsize) for i in range(count)]
    names=sections[names_index]; strings=data[names[4]:names[4]+names[5]]
    byname={strings[s[0]:].split(b'\0')[0].decode():s for s in sections}
    rel=byname['.rel.dyn'];plt=byname['.rel.plt']
    if rel[3]+rel[5]!=plt[3]: raise ValueError('Required contiguous relocation sections not satisfied')
    os.replace(library,out/'libhbl-flash-worker.so')
    library=out/'libhbl-flash-worker.so'
    report={'passed':True,'runId':run_id,'compiled':True,'target':'ARM32 Linux / Qt 5.5.1 / glibc 2.22','sha256':sha(library),
            'inputLibraries':dict(zip(required,map(sha,libs))),'radioTables':manifest['files'],
            'installed':False,'cameraUpdateBuilt':False,'deviceAccess':False,
            'integration':'Exported worker API; observer and startup integration must be linked separately'}
    write_report(out/'worker-build.json',report)
    print('PASS: ARM32 worker compiled and linked; no undefined symbols; not installed; not a complete update')

if __name__=='__main__':main()
