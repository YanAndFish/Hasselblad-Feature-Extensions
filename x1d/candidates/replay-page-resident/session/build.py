"""独立回放页资源冻结与 ARM Qt5.5 构建；所有输出限本候选。"""
from pathlib import Path
import hashlib,io,json,os,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;CANDIDATE=HERE.parent;ROOT=CANDIDATE.parents[2]
CACHE=ROOT/'.research-cache/x1d-1.25.0';BASELINE=CACHE/'baseline';OUT=CANDIDATE/'build/session'
FIXED=None;RCC_SHA=None;RELEASE_SHA=None
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    p.resolve().relative_to(CANDIDATE.resolve());p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def freeze():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    sys.path.insert(0,str(HERE));from resource_writer import rcc
    report=json.loads((CANDIDATE/'artifacts/original-page.json').read_text(encoding='utf-8'))
    contract=json.loads((CANDIDATE/'artifacts/contract.json').read_text(encoding='utf-8'))
    if not report['passed'] or not contract['passed']:raise ValueError('offline proof missing')
    for name,digest in report['sources'].items():
        if sha(CANDIDATE/name)!=digest:raise ValueError('tested source changed: '+name)
    files={}
    for name,digest in report['candidateQml'].items():
        p=CANDIDATE/'build/overlay'/name.lstrip('/')
        if sha(p)!=digest:raise ValueError('resource changed: '+name)
        files[name]=p.read_text(encoding='utf-8')
    if {r['path']:r['sha256'] for r in contract['resources']}!=report['candidateQml']:raise ValueError('resource contract mismatch')
    blob=rcc(files);digest=hashlib.sha256(blob).hexdigest();folder=OUT/'fixed'/digest[:16]
    payload={'replay-page.rcc':blob,**{'overlay'+k:v.encode() for k,v in files.items()}}
    for name,data in payload.items():
        p=folder/name;p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists() and p.read_bytes()!=data:raise ValueError('immutable resource conflict')
        if not p.exists():p.write_bytes(data)
    proof={'kind':'independent-replay-page-resources','rccSha256':digest,'files':{k:hashlib.sha256(v).hexdigest() for k,v in payload.items()},
        'manifest':{'resources':{k:{'outputSha256':hashlib.sha256(v.encode()).hexdigest()} for k,v in files.items()}},
        'hardwareRequests':0,'targetValidated':False}
    release=folder/'release.json';serialized=json.dumps(proof,ensure_ascii=False,indent=2)+'\n'
    if release.exists() and release.read_text(encoding='utf-8')!=serialized:raise ValueError('immutable release conflict')
    if not release.exists():release.write_text(serialized,encoding='utf-8',newline='\n')
    save(OUT/'fixed-current.json',{'release':release.relative_to(ROOT).as_posix(),'sha256':sha(release)})
    return fixed()
def fixed():
    global FIXED,RCC_SHA,RELEASE_SHA
    pointer=json.loads((OUT/'fixed-current.json').read_text(encoding='utf-8'));release=ROOT/pointer['release']
    release.resolve().relative_to((OUT/'fixed').resolve())
    if sha(release)!=pointer['sha256']:raise ValueError('fixed release changed')
    value=json.loads(release.read_text(encoding='utf-8'));FIXED=release.parent;RCC_SHA=value['rccSha256'];RELEASE_SHA=sha(release)
    for name,digest in value['files'].items():
        p=(FIXED/name).resolve();p.relative_to(FIXED.resolve())
        if sha(p)!=digest:raise ValueError('fixed member changed: '+name)
    return value
def build():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    release=fixed();out=OUT/'native';out.mkdir(parents=True,exist_ok=True)
    binding=out/'resource_binding.h'
    binding.write_text('static const char *rccSha="'+RCC_SHA+'";\nstruct Entry { const char *path; const char *sha; };\nstatic const Entry entries[]={\n'+
        ''.join('{":'+k+'","'+v['outputSha256']+'"},\n' for k,v in sorted(release['manifest']['resources'].items()))+'};\n',encoding='ascii',newline='\n')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=out/name;p.mkdir(exist_ok=True);env[key]=str(p)
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1';include=out/'include/QtCore';include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (include/'qfeatures.h').write_text('/* Qt5.5.1 public ABI */\n',encoding='ascii')
    zig=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe';target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(out),'-I',str(out/'include'),'-isystem',str(base/'include'),
        '-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),
        '-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=out/'relocations.ld';layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    base_libs=[BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    commands=[];outputs={};inputs=set(base_libs)|{binding,Path(__file__),FIXED/'release.json'}
    def run(args):
        result=subprocess.run([str(zig)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'));from elftools.elf.elffile import ELFFile
    for name,source,qtlibs,shared in [('libhbl-replay-page.so','runtime.cpp',('Qml','Core'),True),('replay-health','health.cpp',('DBus','Core'),False),('replay-control','control.cpp',(),False)]:
        path=out/name;obj=path.with_suffix('.o');src=HERE/'native'/source
        libs=[BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in qtlibs]+base_libs;inputs.update(libs);inputs.add(src)
        run(['c++','-std=c++11']+flags+['-c',str(src),'-o',str(obj)])
        run(['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined']+([] if name=='replay-control' else ['-Wl,-s'])+['-Wl,-T,'+str(layout)]+(['-Wl,-soname,'+name] if shared else [])+[str(obj)]+list(map(str,libs))+['-o',str(path)])
        elf=ELFFile(io.BytesIO(path.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
        assert elf.elfclass==32 and elf.little_endian and elf['e_machine']=='EM_ARM'
        assert rel and plt and rel['sh_addr']+rel['sh_size']==plt['sh_addr']
        outputs[name]={'sha256':sha(path),'bytes':path.stat().st_size,'arm32':True,'relocationsContiguous':True,
            'needed':[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']}
    save(out/'build.json',{'compiled':True,'outputs':outputs,'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(inputs)},
        'fixedReleaseSha256':RELEASE_SHA,'rccSha256':RCC_SHA,'commands':commands,'hardwareRequests':0,'targetValidated':False})
    return {'compiled':True,'outputs':outputs,'hardwareRequests':0}
if __name__=='__main__':print(json.dumps(freeze() if sys.argv[1:]==['--freeze'] else build()))
