"""构建独立会话守护库/状态检查器/QML 资源；只在本候选写入，不运行目标程序。"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
OUT=HERE/'artifacts/session'
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf, BASELINE, CACHE, qml_files

def sha(b): return hashlib.sha256(b).hexdigest()

def qhash(s):
    h=0
    for c in s:
        h=(h<<4)+ord(c); h^=(h&0xf0000000)>>23; h&=0xfffffff
    return h

def resource(main):
    # 仅覆盖原根资源 main.qml；Qt 5.5.1 RCC v1 的根目录+单文件结构。
    names=struct.pack('>HI',0,0)+struct.pack('>HI',8,qhash('main.qml'))+'main.qml'.encode('utf-16-be')
    encoded=main.encode('utf-8'); compressed=struct.pack('>I',len(encoded))+zlib.compress(encoded,9)
    payload=struct.pack('>I',len(compressed))+compressed
    tree=struct.pack('>IHII',0,2,1,1)+struct.pack('>IHHHI',6,1,0,1,0)
    return b'qres'+struct.pack('>IIII',1,20+len(payload)+len(names),20,20+len(payload))+payload+names+tree

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    gui=(BASELINE/'usr/bin/victory-gui').read_bytes()
    manifest=json.loads((HERE/'artifacts/adapter/manifest.json').read_text(encoding='utf-8'))
    assert sha(gui)==manifest['inputHashes']['.research-cache/x1d-1.25.0/baseline/usr/bin/victory-gui']
    main=qml_files(ArmElf(gui))['/main.qml']
    assert main.rstrip().endswith('}') and main.count('objectName: "mainRoot"')==1
    addition=(HERE/'session/hold.qml.inc').read_text(encoding='utf-8')
    edited=main.rstrip()[:-1]+addition+'}\n'
    (OUT/'main.qml').write_bytes(edited.encode('utf-8'))
    rcc=resource(edited); (OUT/'replay-ui.rcc').write_bytes(rcc)
    build=HERE/'artifacts/build'
    definitions=(build/'bindings.h').read_text(encoding='utf-8')+'\n#define X1D_SESSION_RCC_SHA256 "'+sha(rcc)+'"\n'
    (OUT/'bindings.h').write_text(definitions,encoding='utf-8')
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    qt=CACHE/'qt-public'; base=qt/'qtbase-opensource-src-5.5.1'; declarative=qt/'qtdeclarative-opensource-src-5.5.1'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(OUT/'zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(OUT/'zig-local-cache'))
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-std=c++11','-fPIC','-fno-stack-protector',
           '-I',str(build/'include'),'-isystem',str(base/'include'),'-isystem',str(declarative/'include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-isystem',str(base/'src/3rdparty/angle/include'),'-include',str(OUT/'bindings.h'),
           '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra']
    common=[BASELINE/'usr/lib'/('libQt5'+m+'.so.5.5.1') for m in ('DBus','Core')]+[
        BASELINE/'usr/lib/libstdc++.so.6.0.21',BASELINE/'lib/libgcc_s.so.1',BASELINE/'lib/libdl-2.22.so',
        BASELINE/'lib/librt-2.22.so',BASELINE/'lib/libc-2.22.so']
    exports=['_Z21qRegisterResourceDataiPKhS0_S0_','_ZN21QQmlApplicationEngine4loadERK4QUrl','x1d_replay_session_admit']
    (OUT/'session.map').write_text('{ global: '+ '; '.join(exports)+'; local: *; };\n',encoding='utf-8')
    products={}
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    for source,name,shared in [('session_runtime.cpp','libx1d-replay-session.so',True),('session_check.cpp','replay-check',False)]:
        obj=OUT/(source+'.o')
        subprocess.run([str(compiler),'c++',*flags,'-c',str(HERE/'session'/source),'-o',str(obj)],cwd=ROOT,env=env,check=True)
        extra=([BASELINE/'usr/lib'/('libQt5'+m+'.so.5.5.1') for m in ('Quick','Qml','Gui','Network')]+[
            HERE/'artifacts/load-preparation/inputs/usr/lib/libGLESv2.so.2.0.0']) if shared else []
        linker=['-shared','-nostdlib','-Wl,-soname,'+name,'-Wl,--version-script,'+str(OUT/'session.map')] if shared else []
        subprocess.run([str(compiler),'cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9',*linker,
                        '-Wl,--no-undefined','-Wl,-T,'+str(layout),str(obj),*[str(p) for p in extra+common],'-o',str(OUT/name)],cwd=ROOT,env=env,check=True)
        elf=ArmElf((OUT/name).read_bytes())
        rel,plt=elf.elf.get_section_by_name('.rel.dyn'),elf.elf.get_section_by_name('.rel.plt')
        assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
        dyn=elf.elf.get_section_by_name('.dynsym')
        products[name]={'sha256':sha((OUT/name).read_bytes()),'bytes':(OUT/name).stat().st_size,
                        'needed':[t.needed for t in elf.elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED'],
                        'imports':sorted({s.name for s in dyn.iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF'})}
        if shared:
            assert sorted(s.name for s in dyn.iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF')==sorted(exports)
    products['replay-ui.rcc']={'sha256':sha(rcc),'bytes':len(rcc)}
    sources=[Path(__file__),*sorted((HERE/'session').glob('*.cpp')),*sorted((HERE/'session').glob('*.h')),HERE/'session/hold.qml.inc']
    report={'status':'compiled-session-not-device-tested','firmware':'X1D-50c 1.25.0','cameraAccess':False,'installed':False,
            'adapterManifestSha256':sha((HERE/'artifacts/adapter/manifest.json').read_bytes()),'products':products,
            'originalMainSha256':sha(main.encode()),'mainSha256':sha(edited.encode()),
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sources}}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sessionBuilt':list(products),'cameraAccess':False}))

if __name__=='__main__':run()
