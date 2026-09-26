"""编译独立正式客户端、双模式 observer 与机内无硬件检查程序。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
COMMON=HERE.parent
OUT=HERE/'linux-build'
CACHE=ROOT/'.research-cache/x1d-1.25.0'
BASELINE=CACHE/'baseline'

def sha(data): return hashlib.sha256(data).hexdigest()

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('workspace mismatch')
    OUT.mkdir(exist_ok=True)
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    qt=CACHE/'qt-public'; base=qt/'qtbase-opensource-src-5.5.1'
    include=OUT/'include/QtCore'; include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (include/'qfeatures.h').write_text('/* Fixed Qt 5.5.1 public ABI. */\n',encoding='ascii')
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    commands=[]
    def run(args):
        result=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode: raise RuntimeError(result.stderr)
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUT/'include'),'-I',str(HERE),'-I',str(COMMON),
                 '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
                 '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
                 '-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core')]
    libs += [BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    sources=[HERE/'settings_bus.cpp',COMMON/'native_config.c']
    objects={}
    for source in sources:
        obj=OUT/(source.stem+'.o')
        language=['c++','-std=c++11'] if source.suffix=='.cpp' else ['cc','-std=c11']
        run(language+flags+['-c',str(source),'-o',str(obj)]);objects[source.stem]=obj
    outputs=[]
    for name,inputs in [('libhbl-af-bus.so',['settings_bus','native_config'])]:
        output=OUT/name
        run(['cc']+target+['-shared','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),'-Wl,-soname,'+name]+
            [str(objects[n]) for n in inputs]+list(map(str,libs))+['-o',str(output)])
        outputs.append(output)
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    abi={}
    for path in outputs:
        elf=ELFFile(io.BytesIO(path.read_bytes()))
        rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
        if not rel or not plt or rel['sh_addr']+rel['sh_size']!=plt['sh_addr']:
            raise RuntimeError('old loader relocation layout mismatch: '+path.name)
        if elf.elfclass!=32 or not elf.little_endian or elf['e_machine']!='EM_ARM': raise RuntimeError('ABI mismatch')
        imports={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']=='SHN_UNDEF'}
        if '__lxstat64' not in imports or imports.intersection({'stat','lstat','fstat','stat64','lstat64','fstat64','__xstat','__lxstat','__fxstat'}):
            raise RuntimeError('fixed ARM glibc stat64 interface required: '+path.name)
        abi[path.name]={'relocationsContiguous':True,'statInterface':'__lxstat64',
            'statVersion':3,'statBytes':104,'statModeOffset':16,'statUidOffset':24,
            'needed':[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']}
    sources += [COMMON/name for name in ('settings_wire.h','settings_socket.h','native_config.h','native_af.h')]
    sources += [HERE/'build_bus.py']
    report={'revision':'bus-startup-r2','compiled':True,'outputs':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in outputs},
            'sourceHashes':{os.path.relpath(p,HERE).replace('\\','/'):sha(p.read_bytes()) for p in sources},
            'abi':abi,'commands':commands,'hardwareRequests':0,'installed':False,
            'targetSelfChecksRun':False,'physicalTimingVerified':False}
    (OUT/'client-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'compiled':True,'outputs':report['outputs'],'hardwareRequests':0,'installed':False}

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
