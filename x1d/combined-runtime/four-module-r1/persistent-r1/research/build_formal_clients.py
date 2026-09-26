"""编译独立正式客户端、双模式 observer 与机内无硬件检查程序。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/formal-flash-program'
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
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUT/'include'),'-I',str(HERE/'native'),
                 '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
                 '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
                 '-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[BASELINE/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core')]
    libs += [BASELINE/p for p in ('usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so')]
    sources=[HERE/'native'/name for name in ('formal_worker.cpp','formal_sync_observer.cpp','boot_transport.cpp','boot_loader.cpp','boot_session.cpp','boot_probe_hook.cpp','boot_batch_wire_check.cpp','persistent_check.cpp','formal_runtime.cpp','formal_sync_hook_check.cpp','formal_client_check.cpp','formal_system_check.cpp')]
    objects={}
    for source in sources:
        obj=OUT/(source.stem+'.o')
        run(['c++','-std=c++11']+flags+['-c',str(source),'-o',str(obj)]);objects[source.stem]=obj
    outputs=[]
    for name,inputs,shared in [('libhbl-formal-observer.so',['formal_worker','formal_sync_observer','boot_transport','boot_loader','boot_session'],True),
                               ('libhbl-boot-probe.so',['boot_probe_hook','boot_transport','boot_loader','boot_session'],True),
                               ('libhbl-formal.so',['formal_runtime'],True),
                               ('formal-sync-hook-check',['formal_sync_hook_check'],False),
                               ('formal-client-check',['formal_client_check'],False),
                               ('persistent-check',['persistent_check','boot_loader'],False),
                               ('batch-wire-check',['boot_batch_wire_check','boot_session','boot_loader'],False),
                               ('formal-system-check',['formal_system_check'],False)]:
        output=OUT/name
        extra=['-Wl,-soname,'+name] if shared else ['-Wl,--export-dynamic']
        if name=='formal-system-check': extra += [str(BASELINE/'usr/lib/libQt5DBus.so.5.5.1')]
        run(['cc']+target+['-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)]+extra+
            [str(objects[n]) for n in inputs]+list(map(str,libs))+['-o',str(output)])
        outputs.append(output)
    probe=(HERE/'native/netlink_probe.c').read_text(encoding='utf-8')
    if probe.count('marker!=0x584e')!=1: raise RuntimeError('probe baseline changed')
    probe=probe.replace('marker!=0x584e','marker!=0x5854')
    source=OUT/'formal_netlink_probe.c'; source.write_text(probe,encoding='utf-8');sources.append(source)
    output=OUT/'formal-netlink-probe'
    run(['cc']+target+['-O2','-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),'-Wall','-Wextra','-Werror','-I',str(HERE/'native'),str(source),'-o',str(output)])
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
        abi[path.name]={'relocationsContiguous':True,'needed':[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']}
    sources += list((HERE/'native').glob('formal_*.h'))
    sources += [HERE/'native'/n for n in ('rf_local_socket.h','rf_bridge.h','rf_receiver.h','rf_netlink_wire.h',
                'mechanical_sync_wire.h','farm_sync_wire.h','mechanical_rf_core.h','rf_core.h','rf_es_timing.h',
                'mechanical_direct_dispatch.h','formal_direct_check.h','godox_formal_wave.h','godox_power_wave.h')]
    sources += [HERE/'build/formal-flash-candidate/formal_flash_hashes.h',Path(__file__)]
    sources += [HERE/'native'/n for n in ('boot_transport.h','boot_loader.h','boot_batch.h','boot_session.h','persistent_settings.h','persistent_settings_store.h','mechanical_calibration.h','settings_restore_check.h')]
    sources += [HERE/'build/boot-data'/n for n in ('boot_contract_data.h','af_relocation_data.h')]
    sources += [HERE/'build/batch-model/adapter_data.h']
    report={'compiled':True,'outputs':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in outputs},
            'sourceHashes':{str(p.relative_to(HERE)).replace('\\','/'):sha(p.read_bytes()) for p in sources},
            'abi':abi,'commands':commands,'hardwareRequests':0,'installed':False,
            'targetSelfChecksRun':False,'physicalTimingVerified':False}
    (OUT/'client-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'compiled':True,'outputs':report['outputs'],'hardwareRequests':0,'installed':False}

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
