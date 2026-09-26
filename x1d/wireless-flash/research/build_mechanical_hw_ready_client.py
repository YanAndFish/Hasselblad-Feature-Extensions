"""为芯片预准备实验件构建独立 worker；不改已封包的无诊断版本。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-hw-ready-candidate'
NATIVE=HERE/'native'

def sha(data): return hashlib.sha256(data).hexdigest()
def once(s,a,b):
    if s.count(a)!=1: raise RuntimeError('Client anchor mismatch: '+a[:100])
    return s.replace(a,b)

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    m=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    checks=json.loads((OUT/'instruction-checks.json').read_text(encoding='utf-8'))
    if not checks['passed'] or checks['firmwareSha256']!=m['sha256']: raise RuntimeError('Instruction checks missing')
    wire=(NATIVE/'rf_netlink_wire.h').read_text(encoding='utf-8')
    wire=once(wire,'(selector!=0 && selector!=40)','(selector!=0 && selector!=40 && selector!=41)')
    (OUT/'hardware_ready_netlink_wire.h').write_text(wire,encoding='utf-8')
    channel=(NATIVE/'mechanical_netlink_radio.h').read_text(encoding='utf-8')
    channel='#include "hardware_ready_netlink_wire.h"\n'+channel
    channel=once(channel,'None,Family,Marker,Fire','None,Family,Marker,HardwarePrepare,Fire')
    channel=once(channel,'next==Fire ? 40 : 0','next==Fire ? 40 : next==HardwarePrepare ? 41 : 0')
    channel=once(channel,'''            ready=value==0x584e;
            if (!ready) { error=QStringLiteral("驱动读回版本不符"); closeChannel(); }
            if (ready) ready=prepareNextRequest();
            if (prepared) prepared(ready);''','''            if (value!=0x5850) {
                error=QStringLiteral("芯片预准备版本不符"); closeChannel();
                if (prepared) prepared(false);
            } else if (!send(HardwarePrepare)) { if (prepared) prepared(false); }
        } else if (done==HardwarePrepare) {
            ready=value==1;
            if (!ready) { error=QStringLiteral("芯片准备未完成"); closeChannel(); }
            if (ready) ready=prepareNextRequest();
            if (prepared) prepared(ready);''')
    (OUT/'hardware_ready_netlink_radio.h').write_text(channel,encoding='utf-8')
    radio=(NATIVE/'mechanical_prepared_radio.h').read_text(encoding='utf-8')
    radio=once(radio,'#include "mechanical_netlink_radio.h"','#include "hardware_ready_netlink_radio.h"')
    radio=once(radio,'expected[]={0x584e,1','expected[]={0x5850,1')
    (OUT/'hardware_ready_radio.h').write_text(radio,encoding='utf-8')
    worker=(NATIVE/'mechanical_wireless_worker.cpp').read_text(encoding='utf-8')
    worker=once(worker,'#include "mechanical_prepared_radio.h"','#include "hardware_ready_radio.h"')
    worker=once(worker,'正在设置功率、生成并校验波形','正在完成无线与芯片准备')
    worker=once(worker,'session=0,revision=0,shot=0,eventSequence=0','session=0,revision=0')
    worker=once(worker,'lastSyncShot=0,syncPhases=0,lastSyncProgress=0','lastSyncShot=0,syncPhases=0')
    (OUT/'hardware_ready_worker.cpp').write_text(worker,encoding='utf-8')
    # 当前页面的自动开关仍使用现有配置链；只有芯片准备回复成功才把 ready 传给界面。
    cache=ROOT/'.research-cache/x1d-1.25.0'; baseline=cache/'baseline'
    qt=cache/'qt-public'; base=qt/'qtbase-opensource-src-5.5.1'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    compiler=cache/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(HERE/'build/mechanical-sync-candidate/include'),'-I',str(NATIVE),
           '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
           '-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    commands=[]
    def run(args):
        r=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':r.returncode,'stderr':r.stderr})
        if r.returncode: raise RuntimeError(r.stderr)
    obj=OUT/'worker.o'
    run(['c++','-std=c++11']+flags+['-c',str(OUT/'hardware_ready_worker.cpp'),'-o',str(obj)])
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[baseline/('usr/lib/libQt5'+name+'.so.5.5.1') for name in ('Qml','Core','Network','DBus')]
    libs+=[baseline/p for p in ('usr/lib/libappscommon.so.1.0.0','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so')]
    output=OUT/'wireless-worker'
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-no-pie','-Wl,--no-undefined',
         '-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+list(map(str,libs))+['-o',str(output)])
    probe=(NATIVE/'netlink_probe.c').read_text(encoding='utf-8')
    probe=once(probe,'marker!=0x584e','marker!=0x5850')
    (OUT/'netlink_probe.c').write_text(probe,encoding='utf-8')
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-O2','-Wl,-s','-Wl,-T,'+str(layout),
         '-Wall','-Wextra','-Werror','-I',str(NATIVE),str(OUT/'netlink_probe.c'),'-o',str(OUT/'netlink-probe')])
    wireexe=OUT/'mechanical_hw_ready_wire.test.exe'
    run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(HERE/'CodeTests/mechanical_hw_ready_wire.test.c'),'-o',str(wireexe)])
    wirecheck=subprocess.run([str(wireexe)],env=env,capture_output=True,text=True,timeout=10)
    if wirecheck.returncode: raise RuntimeError(wirecheck.stdout+wirecheck.stderr)
    wirechecks=json.loads(wirecheck.stdout)
    sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
    import io
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(output.read_bytes())); rel=elf.get_section_by_name('.rel.dyn'); plt=elf.get_section_by_name('.rel.plt')
    if rel['sh_addr']+rel['sh_size']!=plt['sh_addr']: raise RuntimeError('REL/JMPREL discontinuity')
    probeelf=ELFFile(io.BytesIO((OUT/'netlink-probe').read_bytes()))
    rel=probeelf.get_section_by_name('.rel.dyn'); plt=probeelf.get_section_by_name('.rel.plt')
    if rel['sh_addr']+rel['sh_size']!=plt['sh_addr']: raise RuntimeError('Probe REL/JMPREL discontinuity')
    report={'passed':True,'workerSha256':sha(output.read_bytes()),'workerBytes':output.stat().st_size,
            'firmwareSha256':m['sha256'],'prepareSelector':41,'readyOnlyAfterHardwareReply':True,
            'persistentDiagnostics':False,'installed':False,'packagedForHardware':False,
            'hardwareRequests':0,'targetQtRuntimeChecked':False,'commands':commands,
            'wireChecks':wirechecks,'netlinkProbeSha256':sha((OUT/'netlink-probe').read_bytes()),
            'sourceHashes':{p.name:sha(p.read_bytes()) for p in [Path(__file__),OUT/'hardware_ready_worker.cpp',OUT/'hardware_ready_radio.h',OUT/'hardware_ready_netlink_radio.h',OUT/'hardware_ready_netlink_wire.h']}}
    (OUT/'client-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('passed','workerBytes','readyOnlyAfterHardwareReply','installed','hardwareRequests')}

if __name__=='__main__': print(build())
