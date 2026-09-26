"""独立 UI 的 ARM Qt5.5 本地构建；仅写本候选目录，零设备请求。"""
from pathlib import Path
import hashlib, io, json, os, subprocess, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
CANDIDATE=HERE.parent
ROOT=CANDIDATE.parents[2]
CACHE=ROOT/'.research-cache/x1d-1.25.0'
BASELINE=CACHE/'baseline'
OUT=CANDIDATE/'build/session'
FIXED=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57'
RCC_SHA='0456d37bc5ddbc57b97e8a9e8cc41b3eff0bd5efa192215bd9f3ae6022029994'
RELEASE_SHA='030589fb58d6acd503c09dc7d61a9db3e199dd3a169ee0a4f111fad855689d2f'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def fixed():
    if sha(FIXED/'release.json')!=RELEASE_SHA:raise ValueError('fixed release changed')
    report=json.loads((FIXED/'release.json').read_text(encoding='utf-8'))
    for name,value in report['files'].items():
        if sha(FIXED/name)!=value:raise ValueError('fixed member changed: '+name)
    return report
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    fixed();out=OUT/'native';out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=out/name;p.mkdir(exist_ok=True);env[key]=str(p)
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    include=out/'include/QtCore';include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (include/'qfeatures.h').write_text('/* Qt 5.5.1 public ABI */\n',encoding='ascii')
    zig=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(out/'include'),'-isystem',str(base/'include'),
        '-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),
        '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=out/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    base_libs=[BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    commands=[];outputs={};inputs=set(base_libs)
    def run(args):
        result=subprocess.run([str(zig)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'))
    from elftools.elf.elffile import ELFFile
    for name,source,qtlibs,shared in [('libhbl-ui-resident.so','runtime.cpp',('Qml','Core'),True),('ui-health','health.cpp',('DBus','Core'),False)]:
        path=out/name;obj=path.with_suffix('.o');src=HERE/'native'/source
        libs=[BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in qtlibs]+base_libs
        inputs.update(libs);inputs.add(src)
        run(['c++','-std=c++11']+flags+['-c',str(src),'-o',str(obj)])
        run(['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)]+(['-Wl,-soname,'+name] if shared else [])+[str(obj)]+list(map(str,libs))+['-o',str(path)])
        elf=ELFFile(io.BytesIO(path.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
        assert elf.elfclass==32 and elf.little_endian and elf['e_machine']=='EM_ARM'
        assert rel and plt and rel['sh_addr']+rel['sh_size']==plt['sh_addr']
        outputs[name]={'sha256':sha(path),'bytes':path.stat().st_size,'arm32':True,'relocationsContiguous':True,
            'needed':[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']}
    inputs.add(Path(__file__))
    report={'compiled':True,'outputs':outputs,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(inputs)},
        'fixedReleaseSha256':RELEASE_SHA,'rccSha256':RCC_SHA,'commands':commands,'hardwareRequests':0,'targetValidated':False}
    save(out/'build.json',report)
    return {'compiled':True,'outputs':outputs,'hardwareRequests':0}
if __name__=='__main__':print(json.dumps(build()))
