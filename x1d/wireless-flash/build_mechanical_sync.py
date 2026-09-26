"""机械 FPGA 七信号候选的独立构建；不安装、不访问相机。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-sync-candidate'
PREPARED_SHA='654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688'
SOURCES=['A 路首次同步','B 路首次同步','启动保持置位','退出空闲','状态 1 置位','状态 3 置位','返回空闲']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def build():
    assert Path.cwd().resolve()==ROOT
    sys.path.insert(0,str(HERE/'research'))
    from prepare_mechanical_candidate import prepare
    prepare()
    OUT.mkdir(exist_ok=True)
    common={'__name__':'mechanical_build_helpers','__file__':str(HERE/'build.py')}
    helper=(HERE/'build.py').read_text(encoding='utf-8')
    helper=helper.replace('ui/main_additions.qml.inc','ui/mechanical_main_additions.qml.inc').replace('ui/settings_additions.qml.inc','ui/mechanical_settings_additions.qml.inc')
    exec(compile(helper,str(HERE/'build.py'),'exec'),common)
    common['OUT']=OUT
    from prepare_mechanical_ui import extend
    qml=extend(common,common['patch_qml']())
    cache,baseline,compiler=common['CACHE'],common['BASELINE'],common['COMPILER']
    include=OUT/'include/QtCore'; include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n')
    (include/'qfeatures.h').write_text('/* Fixed public Qt ABI. */\n')
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    env['PYTHONDONTWRITEBYTECODE']='1'
    qt=cache/'qt-public'; base=qt/'qtbase-opensource-src-5.5.1'
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(OUT/'include'),'-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra']
    commands=[]
    def run(args):
        result=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode: raise RuntimeError(result.stderr)
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n')
    libs=[baseline/('usr/lib/libQt5'+m+'.so.5.5.1') for m in ('Qml','Core','Network','DBus')]
    libs += [baseline/p for p in ('usr/lib/libappscommon.so.1.0.0','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so')]
    files={}
    for name,output,kind in [('mechanical_wireless_runtime','libhbl-wireless.so','-shared'),
                             ('mechanical_wireless_worker','wireless-worker','-no-pie'),
                             ('mechanical_sync_observer','libhbl-mechanical-observer.so','-shared'),
                             ('mechanical_sync_hook_check','mechanical-sync-hook-check','-no-pie')]:
        obj=OUT/(name+'.o')
        run(['c++','-std=c++11']+flags+['-c',str(HERE/'native'/(name+'.cpp')),'-o',str(obj)])
        link=['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9',kind,'-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)]
        if kind=='-shared': link+=['-Wl,-soname,'+output]
        if name=='mechanical_sync_hook_check': link+=['-Wl,--export-dynamic']
        run(link+[str(obj)]+[str(p) for p in libs]+['-o',str(OUT/output)])
        elf=common['ArmElf']((OUT/output).read_bytes())
        rel,plt=(elf.elf.get_section_by_name(n) for n in ('.rel.dyn','.rel.plt'))
        if rel['sh_addr']+rel['sh_size']!=plt['sh_addr']: raise RuntimeError('REL/JMPREL discontinuity')
        files[output]={'sha256':sha(OUT/output),'bytes':(OUT/output).stat().st_size,'relocations_contiguous':True}
    exe=OUT/'mechanical_wire.test.exe'
    run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(HERE/'CodeTests/mechanical_wire.test.c'),'-o',str(exe)])
    result=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=10)
    if result.returncode: raise RuntimeError(result.stdout+result.stderr)
    checks=json.loads(result.stdout)
    prepared=HERE/'build/prepared-wltest.bin'
    if sha(prepared)!=PREPARED_SHA: raise RuntimeError('prepared radio bytes changed')
    (OUT/'prepared-wltest.bin').write_bytes(prepared.read_bytes())
    (OUT/'prepare-radio.sh').write_text((HERE/'prepare-radio.sh.in').read_text(encoding='ascii').replace('@FIRMWARE_SHA256@',PREPARED_SHA),encoding='ascii',newline='\n')
    for name in ('ui.rcc','prepared-wltest.bin','prepare-radio.sh'):
        files[name]={'sha256':sha(OUT/name),'bytes':(OUT/name).stat().st_size}
    paths=[Path(__file__),HERE/'build.py',HERE/'research/prepare_mechanical_candidate.py',HERE/'prepare-radio.sh.in',HERE/'CodeTests/mechanical_wire.test.c']
    paths += [HERE/'research/prepare_mechanical_ui.py',HERE/'ui/MechanicalFlashPage.qml',HERE/'research/prepare_mechanical_fastpath.py',HERE/'research/prepare_mechanical_dispatch.py']
    paths+=list((HERE/'native').glob('*.h'))+list((HERE/'native').glob('mechanical*.cpp'))
    paths+=[HERE/'native/wireless_worker.cpp',HERE/'native/wireless_runtime.cpp',HERE/'native/farm_sync_observer.cpp']+list((HERE/'ui').glob('*.inc'))
    report={'status':'机械七信号离线候选；未安装','sourceKind':'gms1-mechanical-seven-signals',
            'availableSources':SOURCES,'files':files,'qml':qml,'checks':checks,
            'radioShaUnchanged':True,'hardwareRequests':0,'installed':False,'targetQtCheckRun':False,
            'physicalTimingMeasured':False,'delayUnits':'integer us, step 10 us; absolute monotonic timerfd from Linux message arrival; physical accuracy unmeasured',
            'sourceHashes':{str(p.relative_to(HERE)):sha(p) for p in paths},'commands':commands}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'built':list(files),'sources':len(SOURCES),'wire_checks':report['checks'],'hardware_requests':0}

if __name__=='__main__': print(build())
