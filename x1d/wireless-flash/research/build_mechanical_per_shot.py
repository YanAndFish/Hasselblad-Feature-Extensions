"""恢复已验证的逐次 PHY 准备入口，保留现有纯记录 worker。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-timing-candidate'
OUT=HERE/'build/mechanical-per-shot-candidate'
FIRMWARE_SHA='654f13688c17e017497184b1a6873347c6b8cd7b01abdab5327bc8035d08f688'

def sha(data): return hashlib.sha256(data).hexdigest()
def once(text,old,new):
    if text.count(old)!=1: raise RuntimeError('Per-shot anchor mismatch: '+old[:70])
    return text.replace(old,new)

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    baseline=json.loads((BASE/'client-build.json').read_text(encoding='utf-8'))
    installed=json.loads((BASE/'installation.json').read_text(encoding='utf-8'))
    if not baseline['passed'] or not installed['installed']: raise RuntimeError('Missing recording baseline')
    for name,digest in baseline['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('Recording source changed')
    if sha((BASE/'wireless-worker').read_bytes())!=installed['files']['wireless-worker']['sha256']:
        raise RuntimeError('Installed worker differs')
    firmware=(HERE/'build/prepared-wltest.bin').read_bytes()
    if sha(firmware)!=FIRMWARE_SHA: raise RuntimeError('Original per-shot firmware mismatch')
    prior=(HERE/'build/mechanical-hw-ready-candidate/hardware-ready-wltest.bin').read_bytes()
    if prior[0x214800-0x180000:0x215f00-0x180000]!=firmware[0x214800-0x180000:0x215f00-0x180000]:
        raise RuntimeError('Waveform changed')
    OUT.mkdir(exist_ok=True)
    (OUT/'per-shot-wltest.bin').write_bytes(firmware)
    worker=once((BASE/'timing_worker.cpp').read_text(encoding='utf-8'),'#include "timing_radio.h"','#include "per_shot_radio.h"')
    worker=once(worker,'正在完成无线与芯片准备','正在准备无线波形；芯片在每次引闪时准备')
    radio=once((BASE/'timing_radio.h').read_text(encoding='utf-8'),'#include "timing_netlink_radio.h"','#include "per_shot_netlink_radio.h"')
    radio=once(radio,'expected[]={0x5850,1','expected[]={0x584e,1')
    channel=once((BASE/'timing_netlink_radio.h').read_text(encoding='utf-8'),'#include "hardware_ready_netlink_wire.h"\n','')
    channel=once(channel,'None,Family,Marker,HardwarePrepare,Fire','None,Family,Marker,Fire')
    channel=once(channel,'next==Fire ? 40 : next==HardwarePrepare ? 41 : 0','next==Fire ? 40 : 0')
    channel=once(channel,'''            if (value!=0x5850) {
                error=QStringLiteral("芯片预准备版本不符"); closeChannel();
                if (prepared) prepared(false);
            } else if (!send(HardwarePrepare)) { if (prepared) prepared(false); }
        } else if (done==HardwarePrepare) {
            ready=value==1;
            if (!ready) { error=QStringLiteral("芯片准备未完成"); closeChannel(); }
            if (ready) ready=prepareNextRequest();
            if (prepared) prepared(ready);''','''            ready=value==0x584e;
            if (!ready) { error=QStringLiteral("逐次准备版本不符"); closeChannel(); }
            if (ready) ready=prepareNextRequest();
            if (prepared) prepared(ready);''')
    if 'HardwarePrepare' in channel or 'hardware_ready_netlink_wire' in channel:
        raise RuntimeError('Hardware pre-prepare path retained')
    for name,content in (('per_shot_worker.cpp',worker),('per_shot_radio.h',radio),('per_shot_netlink_radio.h',channel)):
        (OUT/name).write_text(content,encoding='utf-8')
    cache=ROOT/'.research-cache/x1d-1.25.0'; target=cache/'baseline'
    qt=cache/'qt-public'; core=qt/'qtbase-opensource-src-5.5.1'
    compiler=cache/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(HERE/'build/zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(HERE/'build/zig-local-cache'),PYTHONDONTWRITEBYTECODE='1')
    commands=[]
    def run(args):
        result=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':result.returncode,'stderr':result.stderr})
        if result.returncode: raise RuntimeError(result.stderr)
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(HERE/'build/mechanical-sync-candidate/include'),'-I',str(HERE/'native'),
           '-isystem',str(core/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
           '-I',str(core/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    obj=OUT/'worker.o'; worker_path=OUT/'wireless-worker'
    run(['c++','-std=c++11']+flags+['-c',str(OUT/'per_shot_worker.cpp'),'-o',str(obj)])
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[target/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core','Network','DBus')]
    libs+=[target/p for p in ('usr/lib/libappscommon.so.1.0.0','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so')]
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+list(map(str,libs))+['-o',str(worker_path)])
    probe=OUT/'netlink-probe'
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-O2','-Wl,-s','-Wl,-T,'+str(layout),'-Wall','-Wextra','-Werror',
         '-I',str(HERE/'native'),str(HERE/'native/netlink_probe.c'),'-o',str(probe)])
    sys.path.insert(0,str(cache/'python'))
    from elftools.elf.elffile import ELFFile
    for file in (worker_path,probe):
        elf=ELFFile(io.BytesIO(file.read_bytes())); rel=elf.get_section_by_name('.rel.dyn'); plt=elf.get_section_by_name('.rel.plt')
        if rel['sh_addr']+rel['sh_size']!=plt['sh_addr']: raise RuntimeError('Noncontiguous relocations')
    sources=[Path(__file__),HERE/'native/netlink_probe.c',HERE/'native/rf_netlink_wire.h',HERE/'native/mechanical_prepared_request.h',
             HERE/'native/mechanical_timing_record.h']+[OUT/n for n in ('per_shot_worker.cpp','per_shot_radio.h','per_shot_netlink_radio.h')]
    result={'passed':True,'firmwareSha256':FIRMWARE_SHA,'workerSha256':sha(worker_path.read_bytes()),'workerBytes':worker_path.stat().st_size,
            'netlinkProbeSha256':sha(probe.read_bytes()),'sourceHashes':{str(p.relative_to(HERE)):sha(p.read_bytes()) for p in sources},
            'baselineWorkerSha256':baseline['workerSha256'],'commands':commands,'sourcesRetained':7,
            'timingRecordingRetained':True,'perShotHardwarePrepare':True,'hardwarePrepareAfterFire':False,
            'waveformBytesUnchanged':True,'compensationImplemented':False,'hardwareRequests':0,'installed':False}
    (OUT/'client-build.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:result[k] for k in ('passed','workerBytes','perShotHardwarePrepare','timingRecordingRetained','installed')}

if __name__=='__main__': print(build())
