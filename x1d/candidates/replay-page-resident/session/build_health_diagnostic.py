"""独立构建只读 ARM 健康诊断候选；不修改冻结包或 current.json。"""
from pathlib import Path
import importlib.util,io,json,os,subprocess,sys
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('replay_build_base',Path(__file__).with_name('build.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
HERE=base.HERE;ROOT=base.ROOT;OUT=base.OUT/'diagnostic';CACHE=base.CACHE;BASELINE=base.BASELINE
def run():
    if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
    OUT.mkdir(parents=True,exist_ok=True);env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        p=OUT/name;p.mkdir(exist_ok=True);env[key]=str(p)
    qt=CACHE/'qt-public';qbase=qt/'qtbase-opensource-src-5.5.1';include=OUT/'include/QtCore';include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='ascii')
    (include/'qfeatures.h').write_text('/* Qt5.5.1 public ABI */\n',encoding='ascii')
    zig=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe';target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUT),'-I',str(OUT/'include'),'-isystem',str(qbase/'include'),
        '-I',str(qbase/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    src=HERE/'native/health_diagnostic.cpp';obj=OUT/'health_diagnostic.o';binary=OUT/'replay-health-diagnostic'
    layout=OUT/'relocations.ld';layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[BASELINE/p for p in ('usr/lib/libQt5DBus.so.5.5.1','usr/lib/libQt5Core.so.5.5.1','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    commands=[]
    for args in (['c++','-std=c++11']+flags+['-c',str(src),'-o',str(obj)],
                 ['cc']+target+['-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+list(map(str,libs))+['-o',str(binary)]):
        result=subprocess.run([str(zig)]+args,env=env,capture_output=True,text=True,timeout=60);commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode:raise RuntimeError(result.stderr)
    sys.path.insert(0,str(CACHE/'python'));from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(binary.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
    if not (elf.elfclass==32 and elf['e_machine']=='EM_ARM' and rel and plt and rel['sh_addr']+rel['sh_size']==plt['sh_addr']):raise ValueError('ARM ELF layout')
    proof={'compiled':True,'binary':binary.relative_to(ROOT).as_posix(),'binarySha256':base.sha(binary),'bytes':binary.stat().st_size,
        'sourceSha256':base.sha(src),'builderSha256':base.sha(Path(__file__)),'needed':[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED'],
        'commands':commands,'includedInFrozenPackage':False,'hardwareRequests':0,'targetValidated':False}
    base.save(OUT/'build.json',proof);print(json.dumps({k:proof[k] for k in ('compiled','binarySha256','bytes','includedInFrozenPackage','hardwareRequests')}))
if __name__=='__main__':run()
