"""无线支持层离线测试与真实 ARM/Qt 5.5 交叉链接；不打开设备。"""
from pathlib import Path
import hashlib
import json
import os
import re
import io
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'CodeTests/formal_radio_output'
CACHE=ROOT/'.research-cache/x1d-1.25.0'
def sha(data): return hashlib.sha256(data).hexdigest()
def run():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('workspace mismatch')
    manifest=json.loads((HERE/'build/formal-flash-candidate/firmware-build.json').read_text(encoding='utf-8'))
    for name,digest in manifest['sourceHashes'].items():
        assert sha((HERE/name).read_bytes())==digest, name
    hashes_path=HERE/'build/formal-flash-candidate/expected-hashes.json'
    assert sha(hashes_path.read_bytes())==manifest['expectedHashesSha256']
    expected=json.loads(hashes_path.read_text())
    table=(HERE/'build/formal-flash-candidate/formal_flash_hashes.h').read_text()
    assert [int(x,16) for x in re.findall(r'0x([0-9a-f]{8})u',table)]==expected
    assert len(expected)==1345 and manifest['marker']=='5854' and manifest['fireIndex']==1344
    OUT.mkdir(exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        path=OUT/name; path.mkdir(exist_ok=True); env[key]=str(path)
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    commands=[]
    def invoke(args,tool=compiler):
        result=subprocess.run([str(tool)]+list(map(str,args)),capture_output=True,text=True,env=env,timeout=120)
        commands.append({'arguments':list(map(str,args)),'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode: raise RuntimeError(result.stderr or result.stdout)
        return result.stdout
    qt=CACHE/'qt-public/qtbase-opensource-src-5.5.1'
    obj=OUT/'formal-radio.o'
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
        '-I',HERE/'build/mechanical-sync-candidate/include','-I',HERE/'native','-isystem',qt/'include',
        '-I',qt/'mkspecs/linux-arm-gnueabi-g++','-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion',
        '-Wall','-Wextra','-Werror']
    invoke(['c++','-std=c++11']+flags+['-c',HERE/'CodeTests/formal_radio_compile.cpp','-o',obj])
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    baseline=CACHE/'baseline'
    libs=[baseline/p for p in ('usr/lib/libQt5Core.so.5.5.1','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1',
        'lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    library=OUT/'libhbl-formal-radio.so'
    invoke(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared','-Wl,--no-undefined','-Wl,-s',
            '-Wl,-T,'+str(layout),obj]+libs+['-o',library])
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(library.read_bytes()))
    assert elf.elfclass==32 and elf['e_machine']=='EM_ARM' and elf['e_type']=='ET_DYN'
    rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    tests=[]
    for name in ('formal_radio_wire.test.c','formal_radio_state.test.cpp','mechanical_direct_dispatch.test.cpp'):
        source=HERE/'CodeTests'/name
        if not source.exists(): raise RuntimeError('missing test: '+name)
        executable=OUT/(name+'.exe')
        invoke(['c++' if name.endswith('cpp') else 'cc','-O2','-Wall','-Wextra','-Werror',
                '-I',HERE/'native','-I',HERE/'CodeTests',source,'-o',executable])
        tests.append(invoke([],executable).strip())
    sources=[HERE/'native'/name for name in ('formal_radio.h','formal_netlink_wire.h','formal_prepared_request.h',
                'mechanical_direct_dispatch.h','rf_netlink_wire.h')]
    sources+=list((HERE/'CodeTests').glob('formal_radio*.py'))+list((HERE/'CodeTests').glob('formal_radio*.cpp'))+list((HERE/'CodeTests').glob('formal_radio*.c'))+list((HERE/'CodeTests').glob('formal_radio*.h'))
    report={'passed':True,'tests':tests,'commands':commands,'hardwareRequests':0,'installed':False,
        'sourceHashes':{str(p.relative_to(HERE)):sha(p.read_bytes()) for p in sources},
        'firmwareSha256':manifest['sha256'],'expectedHashesSha256':manifest['expectedHashesSha256'],
        'library':{'sha256':sha(library.read_bytes()),'bytes':library.stat().st_size},
        'physicalTimingVerified':False}
    (OUT/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('sourceHashes','commands')}
if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False))
