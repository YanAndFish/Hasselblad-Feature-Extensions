"""从已装芯片预准备版生成独立纯记录 worker；不补偿、不连接相机。"""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-hw-ready-candidate'
OUT=HERE/'build/mechanical-timing-candidate'

def sha(data): return hashlib.sha256(data).hexdigest()
def once(text,old,new):
    if text.count(old)!=1: raise RuntimeError('Timing anchor mismatch: '+old[:90])
    return text.replace(old,new)

MEMBERS='''    HblTimingRing timingRing={};
    HblTimingEvent timingDispatch={};
    bool timingActive=false;
    HblTimingEvent timingEvent(unsigned kind,uint64_t now,unsigned detail=0,
                               const HblMechanicalSync *sample=nullptr,uint64_t observer=0) {
        HblTimingEvent e={};
        e.kind=kind; e.mono_us=now; e.trial=sample ? sample->trial : core.trial;
        e.epoch=syncEpoch; e.source=core.source; e.delay_us=core.delay_us;
        e.deadline_us=core.deadline_us; e.detail=detail; e.observer_ns=observer;
        if (sample) {
            e.hardware_ticks=uint64_t(sample->timer_low)|(uint64_t(sample->timer_high)<<32);
            e.timer_control=sample->timer_control;
            e.sync_status=sample->sync_status; e.clear_flags=sample->clear_flags;
        }
        return e;
    }
    void recordTiming(unsigned kind,uint64_t now,unsigned detail=0,
                      const HblMechanicalSync *sample=nullptr,uint64_t observer=0) {
        if (!timingActive) return;
        const HblTimingEvent e=timingEvent(kind,now,detail,sample,observer);
        hbl_timing_push(&timingRing,&e);
    }
    void flushTiming() {
        if (!hbl_timing_can_flush(&timingRing,core.enabled,core.pending,radio.busy)) return;
        static_assert(sizeof(HblTimingEvent)==72,"fixed timing ABI");
        static_assert(__BYTE_ORDER__==__ORDER_LITTLE_ENDIAN__,"little endian record");
        const uint32_t header[8]={HBL_TIMING_MAGIC,1,72,timingRing.count,
            timingRing.overwritten,uint32_t(timingRing.total),uint32_t(timingRing.total>>32),0};
        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/timing.bin"));
        if (!file.open(QIODevice::WriteOnly)) {
            timingRing.dirty=0; timingActive=false;
            message=QStringLiteral("时序记录保存失败"); changed(); return;
        }
        bool ok=file.write(reinterpret_cast<const char *>(header),sizeof(header))==sizeof(header);
        const uint32_t first=hbl_timing_first(&timingRing);
        const uint32_t head=qMin(timingRing.count,HBL_TIMING_CAPACITY-first);
        const qint64 headBytes=qint64(head)*sizeof(HblTimingEvent);
        const qint64 tailBytes=qint64(timingRing.count-head)*sizeof(HblTimingEvent);
        if (ok) ok=file.write(reinterpret_cast<const char *>(timingRing.events+first),headBytes)==headBytes;
        if (ok && tailBytes) ok=file.write(reinterpret_cast<const char *>(timingRing.events),tailBytes)==tailBytes;
        if (ok) ok=file.commit(); else file.cancelWriting();
        timingRing.dirty=0; timingActive=false;
        if (!ok) { message=QStringLiteral("时序记录保存失败"); changed(); }
    }
'''

def generate():
    old=json.loads((BASE/'client-build.json').read_text(encoding='utf-8'))
    installed=json.loads((BASE/'installation.json').read_text(encoding='utf-8'))
    if not old['passed'] or not installed.get('installed'): raise RuntimeError('Missing baseline evidence')
    for name in ('hardware_ready_worker.cpp','hardware_ready_radio.h','hardware_ready_netlink_radio.h','hardware_ready_netlink_wire.h'):
        if sha((BASE/name).read_bytes())!=old['sourceHashes'][name]: raise RuntimeError('Baseline source changed: '+name)
    if sha((BASE/'wireless-worker').read_bytes())!=installed['files']['wireless-worker']['sha256']:
        raise RuntimeError('Installed worker baseline mismatch')
    worker=(BASE/'hardware_ready_worker.cpp').read_text(encoding='utf-8')
    worker=once(worker,'#include "mechanical_rf_core.h"','#include "mechanical_rf_core.h"\n#include "mechanical_timing_record.h"')
    worker=once(worker,'#include "hardware_ready_radio.h"','#include "timing_radio.h"')
    worker=once(worker,'    void refreshSourcePid() {',MEMBERS+'    void refreshSourcePid() {')
    worker=once(worker,'        radio.changed=[this]() { changed(); };','''        radio.timing=[this](unsigned kind,uint64_t at,uint32_t sequence,uint32_t detail) {
            if (!timingActive) return;
            HblTimingEvent e=timingDispatch;
            e.kind=kind; e.mono_us=at; e.sequence=sequence; e.detail=detail;
            hbl_timing_push(&timingRing,&e);
        };
        radio.changed=[this]() { changed(); };''')
    worker=once(worker,'        rf_cancel(&core);','''        if (core.pending) recordTiming(HBL_TIMING_CANCEL,mechanical_monotonic_us(),1);
        rf_cancel(&core);''')
    worker=once(worker,'            message=QStringLiteral("无线尚未就绪，本次跳过");','''            recordTiming(HBL_TIMING_SKIP,mechanical_monotonic_us(),unsigned(radio.busy)|(unsigned(radio.ready)<<1));
            message=QStringLiteral("无线尚未就绪，本次跳过");''')
    worker=once(worker,'        if (radio.fire(power)) message=', '''        // 关联驱动回复到提交时的 trial，后续拍摄不能覆盖它。
        timingDispatch=timingEvent(0,0);
        if (radio.fire(power)) message=''')
    worker=once(worker,'    void due() { if (rf_due(&core,mechanical_monotonic_us())) transmit(); changed(); }','''    void due() {
        const uint64_t now=mechanical_monotonic_us();
        const bool fire=rf_due(&core,now);
        recordTiming(HBL_TIMING_DUE,now,unsigned(fire));
        if (fire) transmit();
        changed();
    }''')
    worker=once(worker,'            syncEpoch=epoch;\n            if (sample.trial<lastSyncShot)', '''            syncEpoch=epoch;
            recordTiming(HBL_TIMING_SAMPLE,now,0,&sample,arrival);
            if (sample.trial<lastSyncShot)''')
    worker=once(worker,'            if (mechanical_rf_accept(&core,&sample,at,now,armedAt)) {','''            if (mechanical_rf_accept(&core,&sample,at,now,armedAt)) {
                recordTiming(HBL_TIMING_ACCEPT,now,1,&sample,arrival);''')
    worker=once(worker,'            if (packet.kind==RF_UI_TEST) {','''            if (packet.kind==RF_UI_TEST) {
                timingActive=true;
                recordTiming(HBL_TIMING_CONFIG,mechanical_monotonic_us(),2|(unsigned(power)<<8));''')
    worker=once(worker,'            rf_configure(&core,nextOn,packet.values[RV_SOURCE],packet.values[RV_DELAY]);','''            if (nextOn) timingActive=true;
            rf_configure(&core,nextOn,packet.values[RV_SOURCE],packet.values[RV_DELAY]);
            if (different) recordTiming(HBL_TIMING_CONFIG,mechanical_monotonic_us(),nextOn|(packet.values[RV_POWER]<<8));''')
    worker=once(worker,'        if (session) rf_local_send(fd,RF_UI_SOCKET,&packet);','''        if (session) rf_local_send(fd,RF_UI_SOCKET,&packet);
        flushTiming();''')
    channel=(BASE/'hardware_ready_netlink_radio.h').read_text(encoding='utf-8')
    channel=once(channel,'    std::function<void(bool)> fired;','''    std::function<void(bool)> fired;
    std::function<void(unsigned,uint64_t,uint32_t,uint32_t)> timing;''')
    channel=once(channel,'''        if (sendto(fd,preparedRequest->bytes,preparedRequest->size,MSG_DONTWAIT,
                   reinterpret_cast<sockaddr *>(&preparedPeer),sizeof(preparedPeer))!=ssize_t(preparedRequest->size)) {''','''        const uint64_t entered=mechanical_monotonic_us();
        const ssize_t submitted=sendto(fd,preparedRequest->bytes,preparedRequest->size,MSG_DONTWAIT,
                   reinterpret_cast<sockaddr *>(&preparedPeer),sizeof(preparedPeer));
        const uint64_t returned=mechanical_monotonic_us();
        if (timing) {
            timing(HBL_TIMING_SUBMIT_BEGIN,entered,sequence,0);
            timing(HBL_TIMING_SUBMIT_END,returned,sequence,submitted<0 ? UINT32_MAX : uint32_t(submitted));
        }
        if (submitted!=ssize_t(preparedRequest->size)) {''')
    channel=once(channel,'        const bool wasFire=operation==Fire;','''        const bool wasFire=operation==Fire;
        if (wasFire && timing) timing(HBL_TIMING_FAILURE,mechanical_monotonic_us(),sequence,1);''')
    channel=once(channel,'        } else if (done==Fire) {','''        } else if (done==Fire) {
            if (timing) timing(HBL_TIMING_REPLY,mechanical_monotonic_us(),sequence,value);''')
    radio=(BASE/'hardware_ready_radio.h').read_text(encoding='utf-8')
    radio=once(radio,'#include "hardware_ready_netlink_radio.h"','#include "timing_netlink_radio.h"')
    radio=once(radio,'        channel.prepared=[this](bool ok) {','''        channel.timing=[this](unsigned kind,uint64_t at,uint32_t sequence,uint32_t detail) {
            if (timing) timing(kind,at,sequence,detail);
        };
        channel.prepared=[this](bool ok) {''')
    radio=once(radio,'    std::function<void()> changed;','''    std::function<void()> changed;
    std::function<void(unsigned,uint64_t,uint32_t,uint32_t)> timing;''')
    OUT.mkdir(exist_ok=True)
    for name,text in [('timing_worker.cpp',worker),('timing_radio.h',radio),('timing_netlink_radio.h',channel)]:
        (OUT/name).write_text(text,encoding='utf-8')
    (OUT/'hardware_ready_netlink_wire.h').write_bytes((BASE/'hardware_ready_netlink_wire.h').read_bytes())
    return old,installed

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    old,installed=generate()
    cache=ROOT/'.research-cache/x1d-1.25.0'; baseline=cache/'baseline'
    qt=cache/'qt-public'; base=qt/'qtbase-opensource-src-5.5.1'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    compiler=cache/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    commands=[]
    def run(args):
        p=subprocess.run([str(compiler)]+args,env=env,capture_output=True,text=True,timeout=60)
        commands.append({'arguments':args,'exit':p.returncode,'stderr':p.stderr})
        if p.returncode: raise RuntimeError(p.stderr)
    test=OUT/'mechanical_timing_record.test.exe'
    run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(HERE/'CodeTests/mechanical_timing_record.test.c'),'-o',str(test)])
    subprocess.run([str(test)],capture_output=True,check=True,timeout=10)
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(HERE/'build/mechanical-sync-candidate/include'),'-I',str(HERE/'native'),
           '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
           '-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    obj=OUT/'worker.o'
    run(['c++','-std=c++11']+flags+['-c',str(OUT/'timing_worker.cpp'),'-o',str(obj)])
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[baseline/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core','Network','DBus')]
    libs += [baseline/p for p in ('usr/lib/libappscommon.so.1.0.0','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so')]
    output=OUT/'wireless-worker'
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+list(map(str,libs))+['-o',str(output)])
    sys.path.insert(0,str(cache/'python'))
    from elftools.elf.elffile import ELFFile
    elf=ELFFile(io.BytesIO(output.read_bytes())); rel=elf.get_section_by_name('.rel.dyn'); plt=elf.get_section_by_name('.rel.plt')
    assert rel['sh_addr']+rel['sh_size']==plt['sh_addr']
    paths=[Path(__file__),HERE/'native/mechanical_timing_record.h',HERE/'CodeTests/mechanical_timing_record.test.c']
    paths += [OUT/n for n in ('timing_worker.cpp','timing_radio.h','timing_netlink_radio.h','hardware_ready_netlink_wire.h')]
    report={'passed':True,'workerSha256':sha(output.read_bytes()),'workerBytes':output.stat().st_size,
            'baselineWorkerSha256':installed['files']['wireless-worker']['sha256'],
            'firmwareSha256':old['firmwareSha256'],'sourceHashes':{str(p.relative_to(HERE)):sha(p.read_bytes()) for p in paths},
            'commands':commands,'ringCapacity':2048,'recordBytes':72,'compensationImplemented':False,
            'duringEnabledFileWrites':False,'newThreads':False,'hardwareRequests':0,'installed':False,
            'targetQtRuntimeChecked':False,'physicalFlashTimestampAvailable':False}
    (OUT/'client-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:report[k] for k in ('passed','workerBytes','compensationImplemented','installed')}

if __name__=='__main__': print(build())
