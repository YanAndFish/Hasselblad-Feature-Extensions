"""固定来源离线编译；只在本候选内落盘，不装载或连接设备。"""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'x1d/wireless-flash'
CACHE=ROOT/'.research-cache/x1d-1.25.0'
BASELINE=CACHE/'baseline'
OUT=HERE/'build/program'
GUI_SHA='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'

def sha(data):return hashlib.sha256(data).hexdigest()
def replace(text,old,new,count=1):
    if text.count(old)!=count:raise RuntimeError('source anchor mismatch: '+old[:70])
    return text.replace(old,new)
def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8',newline='\n')

def inputs():
    sources=list((SOURCE/'native').glob('*.h'))
    sources += [SOURCE/'native'/n for n in ('formal_worker.cpp','formal_sync_observer.cpp','formal_sync_hook_check.cpp','formal_system_check.cpp')]
    sources += [SOURCE/'build/formal-flash-candidate'/n for n in ('formal_flash_hashes.h','formal_flash_lut.h')]
    sources += [SOURCE/'ui/formal-runtime/main_formal_runtime.qml.inc',SOURCE/'research/prepare_formal_runtime_ui.py',SOURCE/'build.py']
    hashes={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sources}
    lock=HERE/'source-lock.json'
    if lock.exists():
        if json.loads(lock.read_text(encoding='utf-8'))!=hashes:raise RuntimeError('frozen source changed')
    else:write(lock,json.dumps(hashes,indent=2)+'\n')
    return sources,hashes

def prepare_vendor(sources):
    vendor=OUT/'vendor'
    for source in sources:
        if source.suffix not in ('.h','.cpp'):continue
        text=source.read_text(encoding='utf-8')
        text=text.replace('/tmp/hbl-wireless-flash','/tmp/hbl-flash-wifi-coexist')
        text=text.replace('../build/formal-flash-candidate/','')
        if source.name=='formal_bridge.h':
            text=replace(text,'FV_CHANNEL,FV_ID,FV_LAMPS,FV_RECONFIGURING,',
                'FV_CHANNEL,FV_ID,FV_LAMPS,FV_RECONFIGURING,FV_RELEASED,FV_RELEASE_FAILED,FV_INSTALL_READY,')
            text=replace(text,'p->version=2;','p->version=3;')
            text=replace(text,'p->version!=2','p->version!=3')
            text=replace(text,'p->values[FV_RECONFIGURING]>1 ||',
                'p->values[FV_RECONFIGURING]>1 || p->values[FV_RELEASED]>1 || p->values[FV_RELEASE_FAILED]>1 || p->values[FV_INSTALL_READY]>1 ||')
            text=replace(text,'for (unsigned i=FV_RECONFIGURING+1;', 'for (unsigned i=FV_INSTALL_READY+1;')
        if source.name=='formal_worker.cpp':
            text=replace(text,'bool stopReported=false;', 'bool stopReported=false;\n    bool releaseConfirmed=true,releaseFailed=false;')
            text=replace(text,'policy.complete(action,ok,formalNowUs());pump();',
                '''if(operation==FormalRadio::Close) {releaseConfirmed=ok && !radio.held && !radio.busy && !radio.ready;releaseFailed=!releaseConfirmed;}
            policy.complete(action,ok,formalNowUs());pump();''')
            text=replace(text,'case FormalPolicy::Open:accepted=radio.open(policy.channel,policy.wirelessId);break;',
                'case FormalPolicy::Open:releaseConfirmed=false;releaseFailed=false;accepted=radio.open(policy.channel,policy.wirelessId);break;')
            text=replace(text,'p.values[FV_RECONFIGURING]=policy.reconfiguring;',
                '''p.values[FV_RECONFIGURING]=policy.reconfiguring;
        p.values[FV_RELEASED]=releaseConfirmed && !radio.held && !radio.busy && !radio.ready && !policy.held && !policy.busy();
        p.values[FV_RELEASE_FAILED]=releaseFailed;
        p.values[FV_INSTALL_READY]=policy.installationReady;''')
        write(vendor/source.name,text)
    return vendor

def resources():
    # 导入原有离线 RCC 编码器，但不调用它的构建/设备入口。
    spec=importlib.util.spec_from_file_location('coexist_rcc_encoder',SOURCE/'build.py')
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    raw=(BASELINE/'usr/bin/victory-gui').read_bytes()
    if sha(raw)!=GUI_SHA:raise RuntimeError('GUI baseline mismatch')
    original=common.qml_files(common.ArmElf(raw));main=original['/main.qml']
    if sha(main.encode())!='9793c2eb01018e1f17610d99934425638884338167fc055237211f70f757e0e3':raise RuntimeError('main baseline mismatch')
    specification=importlib.util.spec_from_file_location('coexist_anchor',SOURCE/'research/prepare_formal_runtime_ui.py')
    module=importlib.util.module_from_spec(specification);specification.loader.exec_module(module)
    main=replace(main,module.EXPOSURE,'                    formalExposureGate.begin(liveviewAfterExposure)')
    for level in ('full','half'):
        old='                console.log("Got '+level+' release")'
        main=replace(main,old,'                formalExposureGate.cancel()\n'+old)
    main=replace(main,'    function stopExposure()\n    {','    function stopExposure()\n    {\n        formalExposureGate.cancel()')
    addition=(SOURCE/'ui/formal-runtime/main_formal_runtime.qml.inc').read_text(encoding='utf-8')
    addition=addition[addition.index('    FormalExposureGate {'):]
    addition=replace(addition,'    FormalExposureGate {','    CoexistExposureGate {')
    addition=replace(addition,'typeof hblNative!=="undefined" ? hblNative : null','typeof hblCoexist!=="undefined" ? hblCoexist : null')
    # 只在原厂 Camera.exposing 已为 false 时报告结束；错误本身不冒充曝光结束。
    addition=replace(addition,'formalExposureGate.cancel(); formalExposureGate.shotEnded()',
        'formalExposureGate.cancel(); if(!Camera.exposing) formalExposureGate.shotEnded()',2)
    if addition.count(module.EXPOSURE)!=1:raise RuntimeError('factory continuation changed')
    addition+=(HERE/'ui/status.qml.inc').read_text(encoding='utf-8')
    main=main[:main.rfind('}')]+addition+'\n}\n'
    files={'/main.qml':main,'/CoexistExposureGate.qml':(HERE/'ui/CoexistExposureGate.qml').read_text(encoding='utf-8')}
    for name,text in files.items():write(OUT/'qml'/name.lstrip('/'),text)
    (OUT/'coexist-ui.rcc').write_bytes(common.rcc(files))
    return {name:sha(text.encode()) for name,text in files.items()}

def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace mismatch')
    OUT.mkdir(parents=True,exist_ok=True)
    sources,source_hashes=inputs();vendor=prepare_vendor(sources);qml=resources()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name;folder.mkdir(exist_ok=True);env[key]=str(folder)
    write(OUT/'include/QtCore/qconfig.h','#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n')
    write(OUT/'include/QtCore/qfeatures.h','/* Qt 5.5.1 public ABI. */\n')
    layout=OUT/'relocations.ld';write(layout,'SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    zig=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    qt=CACHE/'qt-public';base=qt/'qtbase-opensource-src-5.5.1'
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUT/'include'),'-I',str(vendor),'-I',str(HERE/'native'),
        '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
        '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    commands=[]
    def run(args):
        result=subprocess.run([str(zig)]+args,env=env,capture_output=True,text=True,timeout=90)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        write(OUT/'commands.json',json.dumps(commands,ensure_ascii=False,indent=2)+'\n')
        if result.returncode:raise RuntimeError(result.stderr)
    objects={}
    for source in [vendor/'formal_worker.cpp',vendor/'formal_sync_observer.cpp',HERE/'native/coexist_runtime.cpp',vendor/'formal_sync_hook_check.cpp',vendor/'formal_system_check.cpp']:
        output=OUT/(source.stem+'.o');run(['c++','-std=c++11']+flags+['-c',str(source),'-o',str(output)]);objects[source.stem]=output
    libs=[BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core','DBus')]
    libs += [BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    binaries=[]
    for name,keys,shared in [('libhbl-coexist-observer.so',['formal_worker','formal_sync_observer'],True),('libhbl-coexist.so',['coexist_runtime'],True),
                            ('coexist-hook-check',['formal_sync_hook_check'],False),('coexist-system-check',['formal_system_check'],False)]:
        output=OUT/name
        run(['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),
            '-Wl,-soname,'+name if shared else '-Wl,--export-dynamic']+[str(objects[key]) for key in keys]+list(map(str,libs))+['-o',str(output)])
        binaries.append(output)
    sys.path.insert(0,str(CACHE/'python'));from elftools.elf.elffile import ELFFile
    abi={}
    for binary in binaries:
        elf=ELFFile(io.BytesIO(binary.read_bytes()));rel=elf.get_section_by_name('.rel.dyn');plt=elf.get_section_by_name('.rel.plt')
        if elf.elfclass!=32 or not elf.little_endian or elf['e_machine']!='EM_ARM' or not rel or not plt or rel['sh_addr']+rel['sh_size']!=plt['sh_addr']:
            raise RuntimeError('ARM/old-loader ABI mismatch')
        abi[binary.name]={'sha256':sha(binary.read_bytes()),'bytes':binary.stat().st_size,'relocationsContiguous':True}
    _,after=inputs()
    if after!=source_hashes:raise RuntimeError('source changed while building')
    report={'compiled':True,'installed':False,'targetRuntimeChecked':False,'wifiCoexistenceVerified':False,'hardwareRequests':0,
        'target':'X1D-50c 1.25.0','guiSha256':GUI_SHA,'qml':qml,'outputs':abi,'sourceHashes':source_hashes,
        'candidateHashes':{p.relative_to(HERE).as_posix():sha(p.read_bytes()) for p in list((HERE/'native').glob('*'))+list((HERE/'ui').glob('*'))+[Path(__file__)]}}
    write(OUT/'build-result.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'compiled':True,'outputs':abi,'installed':False,'hardwareRequests':0}))

if __name__=='__main__':build()
