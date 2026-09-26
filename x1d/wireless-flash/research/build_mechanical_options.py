"""隔离生成两个实验开关；固定输入版本，不访问相机。"""
from pathlib import Path
import hashlib, io, json, os, subprocess, sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-options-candidate'
BASE=HERE/'build/mechanical-timing-candidate'
def sha(data): return hashlib.sha256(data).hexdigest()
def once(text,old,new):
    if text.count(old)!=1: raise RuntimeError('Options anchor: '+old[:100])
    return text.replace(old,new)
def put(name,text): (OUT/name).write_text(text,encoding='utf-8')

def firmware():
    import build_mechanical_hw_ready as old
    text=(HERE/'firmware/mechanical_hw_ready.c').read_text(encoding='utf-8')
    text+='''
/* 42 仅选择逐次模式，43 每次执行原有完整准备/发射/清理。 */
__attribute__((used)) unsigned hbl_hw_per_shot_prepare(uintptr_t pi) {
    if (HW->magic==READY_MAGIC && HW->owner!=pi) return 9;
    clean_hardware();
    unsigned error=base_ready(pi,r32(pi+0x100));
    return error ? error : 1;
}
__attribute__((used)) unsigned hbl_hw_per_shot_fire(uintptr_t pi) {
    /* 不允许逐次请求偷偷消费保持准备模式的状态。 */
    if (HW->magic==READY_MAGIC) return 9;
    unsigned error=base_ready(pi,r32(pi+0x100));
    if (error) return error;
    return FN(0x216800, unsigned (*)(uintptr_t,unsigned))(pi,0);
}
'''
    put('options_firmware.c',text)
    build=Path(old.__file__).read_text(encoding='utf-8')
    build=build.replace("OUT=HERE/'build/mechanical-hw-ready-candidate'", "OUT=HERE/'build/mechanical-options-candidate'")
    build=build.replace("source=HERE/'firmware/mechanical_hw_ready.c'", "source=OUT/'options_firmware.c'")
    build=build.replace("('hbl_hw_prepare','hbl_hw_fire','hbl_hw_release')", "('hbl_hw_prepare','hbl_hw_fire','hbl_hw_release','hbl_hw_per_shot_prepare','hbl_hw_per_shot_fire')")
    build=build.replace('0x5850','0x5851').replace("'5850'","'5851'")
    build=once(build, '    dispatch+=branch(entry+16,0x1c620e)', '''    dispatch+=struct.pack('<HH',0x292a,0xd101)+branch(entry+20,symbols['hbl_hw_per_shot_prepare']&~1)
    dispatch+=struct.pack('<HH',0x292b,0xd101)+branch(entry+28,symbols['hbl_hw_per_shot_fire']&~1)
    dispatch+=branch(entry+32,0x1c620e)''')
    scope={'__file__':str(Path(__file__)), '__name__':'options_firmware_build'}
    exec(compile(build,str(Path(__file__)), 'exec'),scope)
    # 文件位于 research，保持原 HERE 计算。
    return scope['build']()

def radio():
    wire=(BASE/'hardware_ready_netlink_wire.h').read_text(encoding='utf-8')
    wire=once(wire,'selector!=41','selector!=41 && selector!=42 && selector!=43')
    put('options_netlink_wire.h',wire)
    request=(HERE/'native/mechanical_prepared_request.h').read_text(encoding='utf-8')
    request=once(request,'uint32_t previous,uint32_t port,uint32_t interfaceIndex)', 'uint32_t previous,uint32_t port,uint32_t interfaceIndex,unsigned perShot)')
    request=once(request,'    if (previous==UINT32_MAX)', '    if (perShot>1 || previous==UINT32_MAX)')
    request=once(request,'port,interfaceIndex,40)', 'port,interfaceIndex,perShot ? 43 : 40)')
    put('options_prepared_request.h',request)
    channel=(BASE/'timing_netlink_radio.h').read_text(encoding='utf-8')
    channel=channel.replace('hardware_ready_netlink_wire.h','options_netlink_wire.h').replace('mechanical_prepared_request.h','options_prepared_request.h').replace('0x5850','0x5851')
    channel=once(channel,'    bool prepare() {','    bool prepare(unsigned mode) {\n        if (mode>1) return false;')
    channel=once(channel,'        ready=false;\n        const unsigned currentIndex','        perShot=mode;\n        ready=false;\n        const unsigned currentIndex')
    channel=once(channel,'    uint16_t family=0;', '    uint16_t family=0;\n    unsigned perShot=0;')
    channel=once(channel,'family,sequence,port,ifindex))', 'family,sequence,port,ifindex,perShot))')
    channel=once(channel,'next==Fire ? 40 : next==HardwarePrepare ? 41 : 0','next==Fire ? (perShot ? 43 : 40) : next==HardwarePrepare ? (perShot ? 42 : 41) : 0')
    put('options_netlink_radio.h',channel)
    radio=(BASE/'timing_radio.h').read_text(encoding='utf-8').replace('timing_netlink_radio.h','options_netlink_radio.h').replace('0x5850','0x5851')
    radio=once(radio,'operation=Idle; preparedPower=activePower;', 'operation=Idle; preparedPower=activePower; preparedMode=activeMode;')
    radio=radio.replace('desiredPower==activePower && held','desiredPower==activePower && desiredMode==activeMode && held')
    radio=radio.replace('desiredPower==preparedPower;', 'desiredPower==preparedPower && desiredMode==preparedMode;')
    radio=once(radio,'bool prepare(int power)', 'bool prepare(int power,unsigned mode)')
    radio=once(radio,'if (power<10 || power>100)', 'if (power<10 || power>100 || mode>1)')
    radio=once(radio,'wanted=true; desiredPower=power;', 'wanted=true; desiredPower=power; desiredMode=mode;')
    radio=once(radio,'ready && preparedPower==power)', 'ready && preparedPower==power && preparedMode==mode)')
    radio=once(radio,'bool fire(int power)', 'bool fire(int power,unsigned mode)')
    radio=once(radio,'preparedPower!=power || !wanted', 'preparedPower!=power || preparedMode!=mode || desiredMode!=mode || !wanted')
    radio=once(radio,'    bool wanted=false,held=false,cleanupFailed=false;', '    bool wanted=false,held=false,cleanupFailed=false;\n    unsigned desiredMode=0,activeMode=0,preparedMode=0;')
    radio=once(radio,'if (ready && preparedPower==desiredPower)', 'if (ready && preparedPower==desiredPower && preparedMode==desiredMode)')
    radio=once(radio,'activePower=desiredPower; stage=0;', 'activePower=desiredPower; activeMode=desiredMode; stage=0;')
    radio=once(radio,'if (!wanted || desiredPower!=activePower)', 'if (!wanted || desiredPower!=activePower || desiredMode!=activeMode)')
    radio=once(radio,'channel.prepare()', 'channel.prepare(activeMode)')
    put('options_radio.h',radio)

def worker():
    bridge=(HERE/'native/mechanical_rf_bridge.h').read_text(encoding='utf-8')
    bridge=bridge.replace('RV_PROGRESS, RV_COUNT','RV_PROGRESS, RV_PER_SHOT, RV_SAME_PROCESS, RV_COUNT').replace('text[156]','text[148]').replace('p->version=2','p->version=3').replace('p->version!=2','p->version!=3')
    bridge=once(bridge,'p->values[RV_PROGRESS]<=100;', 'p->values[RV_PROGRESS]<=100 && p->values[RV_PER_SHOT]<=1 && p->values[RV_SAME_PROCESS]<=1;')
    put('options_rf_bridge.h',bridge)
    w=(BASE/'timing_worker.cpp').read_text(encoding='utf-8').replace('mechanical_rf_bridge.h','options_rf_bridge.h').replace('timing_radio.h','options_radio.h')
    w=once(w,'#include <QtCore/qtimer.h>', '#include <QtCore/qtimer.h>\n#include <QtCore/qthread.h>\n#include <QtCore/qcoreevent.h>\n#include <QtCore/qmutex.h>')
    w=once(w,'volatile sig_atomic_t stopping=0;\nvoid requestStop(int) { stopping=1; }', '''volatile sig_atomic_t stopping=0;
#ifndef HBL_OPTIONS_EMBEDDED
void requestStop(int) { stopping=1; }
#endif
#ifdef HBL_OPTIONS_EMBEDDED
static const bool embedded=true;
#else
static const bool embedded=false;
#endif''')
    w=once(w,'class Worker : public QObject {', '''class DeliveryEvent : public QEvent {
public:
    static QEvent::Type typeId() { static const int id=QEvent::registerEventType(); return static_cast<QEvent::Type>(id); }
    DeliveryEvent(uint32_t e,const HblMechanicalSync &s,uint64_t at) : QEvent(typeId()),epoch(e),sample(s),arrival(at) {}
    uint32_t epoch; HblMechanicalSync sample; uint64_t arrival;
};
class Worker : public QObject {''')
    w=once(w,'explicit Worker(QObject *parent) : QObject(parent),radio(this),bus(QDBusConnection::systemBus()),timer(this)',
        'explicit Worker(QObject *parent,bool check=false) : QObject(parent),radio(this),bus(check ? QDBusConnection(QStringLiteral("options-offline-check")) : QDBusConnection::systemBus()),timer(this)')
    w=once(w,'        rf_init(&core,1);', '''        testOnly=check;
        rf_init(&core,1);
        if (testOnly) { eventAlive=true; sourcePid=uint32_t(getpid()); valid=timer.valid(); return; }''')
    w=once(w,'    bool valid=false;', '''    bool valid=false;
    unsigned queuedDeliveries=0;
    void enqueueSample(uint32_t epoch,const HblMechanicalSync &sample,uint64_t arrival) {
        if (QThread::currentThread()==thread()) { processSample(epoch,sample,arrival); return; }
        if (__atomic_add_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL)>256) {
            __atomic_sub_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL); return;
        }
        QCoreApplication::postEvent(this,new DeliveryEvent(epoch,sample,arrival));
    }
    void customEvent(QEvent *event) override {
        if (event->type()!=DeliveryEvent::typeId()) { QObject::customEvent(event); return; }
        auto *delivery=static_cast<DeliveryEvent *>(event);
        __atomic_sub_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL);
        processSample(delivery->epoch,delivery->sample,delivery->arrival);
    }
    bool checkDelivery() {
        if (!testOnly || !valid) return false;
        const uint64_t now=mechanical_monotonic_us();
        HblMechanicalSync sample={HBL_MECH_MAGIC,1,1,HBL_MECH_CLOCK|(1u<<11),0,0,1,2,1,0,3};
        if (!hbl_mech_fields_valid(&sample)) return false;
        processSample(1,sample,now*1000u);
        if (core.trial!=1 || core.pending || testSubmits) return false;
        rf_configure(&core,1,3,1000000); armedAt=now;
        sample.trial=2; processSample(1,sample,now*1000u);
        if (!core.pending || core.deadline_us!=now+1000000 || testSubmits) return false;
        processSample(1,sample,now*1000u);
        if (!core.pending || testSubmits) return false;
        sample.clear_flags|=HBL_MECH_DONE; processSample(1,sample,now*1000u);
        if (core.pending || testSubmits) return false;
        sample.trial=3; sample.clear_flags&=~HBL_MECH_DONE;
        __atomic_add_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL);
        QCoreApplication::postEvent(this,new DeliveryEvent(1,sample,now*1000u));
        QCoreApplication::sendPostedEvents(this,DeliveryEvent::typeId());
        if (queuedDeliveries || !core.pending || core.trial!=3 || testSubmits) return false;
        sample.trial=4; processSample(2,sample,now*1000u);
        return !core.enabled && !core.pending && !testSubmits;
    }''')
    w=once(w,'    bool page=false,eventAlive=false,shuttingDown=false;', '    bool page=false,eventAlive=false,shuttingDown=false,testOnly=false;\n    unsigned testSubmits=0;')
    w=once(w,'    void transmit() {', '    void transmit() {\n        if (testOnly) { ++testSubmits; return; }')
    w=once(w,'    void record(const char *text) {', '''    void record(const char *text) {
        QSaveFile owner(QStringLiteral("/tmp/hbl-wireless-flash/worker-owner"));
        if (owner.open(QIODevice::WriteOnly)) {
            owner.write("same-process="+QByteArray::number(unsigned(embedded))+" pid="+QByteArray::number(getpid())+"\\n"); owner.commit();
        }''')
    w=once(w,'        syncFd=rf_local_bind(HBL_MECH_SOCKET);', '        if (!embedded) {\n        syncFd=rf_local_bind(HBL_MECH_SOCKET);')
    w=once(w,'        timer.expired=[this]() { due(); };', '        }\n        timer.expired=[this]() { due(); };')
    w=once(w,'eventAlive=sourcePid!=0 && syncFd>=0;', 'eventAlive=sourcePid!=0 && (embedded ? sourcePid==uint32_t(getpid()) : syncFd>=0);')
    w=once(w,'    void refreshSourcePid() {', '''    void refreshSourcePid() {
        if (embedded) { sourcePid=uint32_t(getpid()); eventAlive=bus.isConnected(); return; }''')
    w=once(w,'int fd=-1,syncFd=-1,power=10;', 'int fd=-1,syncFd=-1,power=10;\n    unsigned perShot=0;')
    w=w.replace('radio.prepare(power)','radio.prepare(power,perShot)').replace('radio.fire(power)','radio.fire(power,perShot)')
    # 同一处理函数被认证 socket 路径和同线程直接路径调用。
    begin=w.index('            const uint64_t now=mechanical_monotonic_us(),at=arrival/1000u;')
    end=w.index('\n        }\n    }\n    void receive()',begin)
    logic=w[begin:end].replace('continue;','return;')
    w=w[:begin]+'            processSample(epoch,sample,arrival);'+w[end:]
    method='''public:
    void processSample(uint32_t epoch,const HblMechanicalSync &sample,uint64_t arrival) {
        if (!eventAlive || shuttingDown || QThread::currentThread()!=thread()) return;
'''+logic+'''
    }
private:
'''
    w=once(w,'    void receive() {',method+'    void receive() {')
    w=once(w,'packet.sequence<=revision)', 'packet.sequence<=revision)') # 明确保留一次提交资格
    w=once(w,'            revision=packet.sequence;\n            if (packet.kind==RF_UI_TEST)', '''            if (packet.values[RV_SAME_PROCESS]!=unsigned(embedded)) continue;
            revision=packet.sequence;
            if (packet.kind==RF_UI_TEST)''')
    w=once(w,'power==int(packet.values[RV_POWER])) transmit();', 'power==int(packet.values[RV_POWER]) && perShot==packet.values[RV_PER_SHOT]) transmit();')
    w=once(w,'page!=bool(packet.values[RV_PAGE]);', 'page!=bool(packet.values[RV_PAGE]) || perShot!=packet.values[RV_PER_SHOT];')
    w=once(w,'core.delay_us!=packet.values[RV_DELAY] || power!=int(packet.values[RV_POWER]);', 'core.delay_us!=packet.values[RV_DELAY] || power!=int(packet.values[RV_POWER]) || perShot!=packet.values[RV_PER_SHOT];')
    w=once(w,'            power=int(packet.values[RV_POWER]); page=packet.values[RV_PAGE];', '            perShot=packet.values[RV_PER_SHOT];\n            power=int(packet.values[RV_POWER]); page=packet.values[RV_PAGE];')
    w=once(w,'nextOn|(packet.values[RV_POWER]<<8)', 'nextOn|(packet.values[RV_PER_SHOT]<<2)|(unsigned(embedded)<<3)|(packet.values[RV_POWER]<<8)')
    w=once(w,'2|(unsigned(power)<<8)', '2|(perShot<<2)|(unsigned(embedded)<<3)|(unsigned(power)<<8)')
    w=once(w,'        packet.values[RV_SOURCE]=core.source;', '        packet.values[RV_SOURCE]=core.source;\n        packet.values[RV_PER_SHOT]=perShot; packet.values[RV_SAME_PROCESS]=unsigned(embedded);')
    w=once(w,'int main(int argc,char **argv) {', '#ifndef HBL_OPTIONS_EMBEDDED\nint main(int argc,char **argv) {')
    w=once(w,'    if (argc==2 && !std::strcmp(argv[1],"--check-slots")) {', '''    if (argc==2 && !std::strcmp(argv[1],"--check-options")) {
        Worker check(&application,true);
        if (!check.checkDelivery()) return 28;
        std::puts("options-delivery-check=6 hardware-requests=0"); return 0;
    }
    if (argc==2 && !std::strcmp(argv[1],"--check-slots")) {''')
    w+='''
#else
static Worker *embeddedWorker=nullptr;
static QMutex deliveryMutex;
extern "C" bool hbl_options_begin() {
    QMutexLocker lock(&deliveryMutex);
    if (embeddedWorker || !QCoreApplication::instance()) return false;
    embeddedWorker=new Worker(QCoreApplication::instance());
    if (!embeddedWorker->valid) { delete embeddedWorker; embeddedWorker=nullptr; return false; }
    return true;
}
extern "C" void hbl_options_deliver(uint32_t epoch,const HblMechanicalSync *sample,uint64_t arrival) {
    QMutexLocker lock(&deliveryMutex);
    if (embeddedWorker && sample) embeddedWorker->enqueueSample(epoch,*sample,arrival);
}
extern "C" void hbl_options_end() { QMutexLocker lock(&deliveryMutex); delete embeddedWorker; embeddedWorker=nullptr; }
#endif
'''
    put('options_worker.cpp',w)

def observer():
    # 已装无持续诊断 observer 的源码固定在 minimal 候选。
    old=HERE/'build/mechanical-sync-candidate/mechanical_sync_observer.cpp'
    # 生成候选名字可变；由已安装包源码基线另行定位。
    source=(HERE/'native/mechanical_sync_observer.cpp').read_text(encoding='utf-8')
    source=source.replace('static bool selfTest,observeEnabled;', '''static bool selfTest,observeEnabled,sameProcess;
extern "C" bool hbl_options_begin();
extern "C" void hbl_options_deliver(uint32_t,const HblMechanicalSync *,uint64_t);
extern "C" void hbl_options_end();
static bool selectedSameProcess() {
    const int fd=open("/tmp/hbl-wireless-flash/process-mode",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return false;
    char bytes[3]={}; const ssize_t n=read(fd,bytes,sizeof(bytes)); close(fd);
    return n==2 && bytes[0]=='1' && bytes[1]=='\\n';
}''')
    source=once(source,'    if (selfTest) return;\n    if (!messageMeta', '    if (selfTest) return;\n    sameProcess=selectedSameProcess();\n    if (sameProcess) return;\n    if (!messageMeta')
    source=once(source,'    uint8_t packet[64];', '''    if (sameProcess) {
        hbl_options_deliver(epoch,&sample,uint64_t(now.tv_sec)*1000000000u+uint64_t(now.tv_nsec));
        return;
    }
    uint8_t packet[64];''')
    source+='''
extern "C" int hbl_options_exec() asm("_ZN16QCoreApplication4execEv");
extern "C" int hbl_options_exec() {
    using Exec=int (*)();
    auto original=reinterpret_cast<Exec>(dlsym(RTLD_NEXT,"_ZN16QCoreApplication4execEv"));
    if (!original) return 78;
    if (sameProcess && observeEnabled && !selfTest) {
        timespec now={};
        if (!messageMeta || clock_gettime(CLOCK_MONOTONIC,&now) || !hbl_options_begin()) {
            health("embedded-start-failed"); return 79;
        }
        epoch=uint32_t(now.tv_nsec)^uint32_t(now.tv_sec)^uint32_t(getpid());
        if (!epoch) epoch=1;
        __atomic_store_n(&outputEnabled,1,__ATOMIC_RELEASE);
        health("ready");
    }
    const int result=original();
    if (sameProcess) {
        __atomic_store_n(&outputEnabled,0,__ATOMIC_RELEASE);
        hbl_options_end();
    }
    return result;
}
'''
    put('options_observer.cpp',source)

def runtime():
    r=(HERE/'native/mechanical_wireless_runtime.cpp').read_text(encoding='utf-8').replace('mechanical_rf_bridge.h','options_rf_bridge.h')
    r=once(r,'#include <QtCore/qfile.h>', '#include <QtCore/qfile.h>\n#include <QtCore/qprocess.h>')
    r=once(r,'        insert(QStringLiteral("command"),QString());', '''        insert(QStringLiteral("command"),QString());
        insert(QStringLiteral("perShot"),false); insert(QStringLiteral("sameProcess"),false);
        QProcessEnvironment env=QProcessEnvironment::systemEnvironment();
        env.remove(QStringLiteral("LD_PRELOAD")); env.remove(QStringLiteral("HBL_RF_ENABLE_PLUGIN"));
        switcher.setProcessEnvironment(env);
        QObject::connect(&switcher,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),
                         this,[this](int code,QProcess::ExitStatus state) {
            switching=false; desiredProcess=-1; connected=false; on=false;
            page=code==0 && state==QProcess::NormalExit ? switchPage : false;
            restoreSettings=code==0 && state==QProcess::NormalExit;
            revision=0; pendingKind=0; if (!++session) ++session;
            status(code==0 && state==QProcess::NormalExit ? QStringLiteral("处理方式已切换；自动引闪关闭") : QStringLiteral("切换失败；自动引闪关闭"));
        });
        QObject::connect(&switcher,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),
                         this,[this](QProcess::ProcessError error) {
            if (error==QProcess::FailedToStart) { switching=false; desiredProcess=-1; status(QStringLiteral("切换程序无法启动")); }
        });''')
    r=once(r,'            const uint64_t now=rf_monotonic_ms();', '''            if (switching) return;
            const uint64_t now=rf_monotonic_ms();
            if (desiredProcess>=0 && now-switchRequestedAt>5000) {
                desiredProcess=-1; status(QStringLiteral("释放未获确认，处理方式未切换"));
            }''')
    r=once(r,'        const QString command=value.toString();', '''        if (switching || desiredProcess>=0) return QVariant();
        const QString command=value.toString();''')
    r=once(r,'        if (command==QStringLiteral("cancel"))', '''        if (command.startsWith(QStringLiteral("process "))) {
            bool valid=false; const uint next=command.mid(8).toUInt(&valid);
            if (!valid || next>1 || !connected || next==sameProcess) return QVariant();
            desiredProcess=int(next); switchRequestedAt=rf_monotonic_ms(); switchPage=page;
            on=false; page=false; issue(RF_UI_CONFIG); return QVariant();
        }
        if (command.startsWith(QStringLiteral("pershot "))) {
            bool valid=false; const uint next=command.mid(8).toUInt(&valid);
            if (!valid || next>1 || !connected) return QVariant();
            perShot=next; insert(QStringLiteral("perShot"),bool(perShot));
        }
        else if (command==QStringLiteral("cancel"))''')
    r=once(r,'    QTimer heartbeat;', '''    QTimer heartbeat;
    QProcess switcher;
    uint32_t perShot=0,sameProcess=0;
    int desiredProcess=-1;
    uint64_t switchRequestedAt=0;
    bool switching=false,switchPage=false,restoreSettings=false;''')
    r=once(r,'        packet.values[RV_SOURCE]=source;', '        packet.values[RV_SOURCE]=source;\n        packet.values[RV_PER_SHOT]=perShot; packet.values[RV_SAME_PROCESS]=sameProcess;')
    r=once(r,'            if (packet.sequence==revision) {', '''            if (first && restoreSettings) {
                restoreSettings=false; sameProcess=packet.values[RV_SAME_PROCESS];
                insert(QStringLiteral("sameProcess"),bool(sameProcess));
                issue(RF_UI_CONFIG); continue;
            }
            if (packet.sequence==revision) {''')
    r=once(r,'                source=packet.values[RV_SOURCE]; delay=packet.values[RV_DELAY];', '''                source=packet.values[RV_SOURCE]; delay=packet.values[RV_DELAY];
                perShot=packet.values[RV_PER_SHOT]; sameProcess=packet.values[RV_SAME_PROCESS];
                insert(QStringLiteral("perShot"),bool(perShot)); insert(QStringLiteral("sameProcess"),bool(sameProcess));''')
    r=once(r,'            if (first && page) issue(RF_UI_CONFIG);', '''            if (desiredProcess>=0 && packet.sequence==revision && !packet.values[RV_ON] &&
                !packet.values[RV_PAGE] && !packet.values[RV_BUSY] && !packet.values[RV_ARMED]) {
                switching=true; connected=false;
                insert(QStringLiteral("radioBusy"),true); insert(QStringLiteral("radioReady"),false);
                status(QStringLiteral("正在切换处理方式；自动引闪关闭"));
                switcher.start(QStringLiteral("/bin/sh"),QStringList()<<QStringLiteral("/tmp/hbl-wireless-flash/switch-process.sh")<<QString::number(desiredProcess));
                return;
            }
            if (first && page) issue(RF_UI_CONFIG);''')
    put('options_runtime.cpp',r)

def ui():
    folder=HERE/'build/mechanical-sync-candidate/qml'
    files={'/'+str(p.relative_to(folder)).replace('\\','/'):p.read_text(encoding='utf-8') for p in folder.rglob('*.qml')}
    main=files['/main.qml']
    main=once(main,'    property int hblRfStepUs: 10', '''    property bool hblRfPerShot: hblRfAvailable && hblNative.perShot
    property bool hblRfSameProcess: hblRfAvailable && hblNative.sameProcess
    function hblRfTogglePerShot() { if (hblRfAvailable) hblNative.command="pershot " + (hblRfPerShot ? "0" : "1"); }
    function hblRfToggleProcess() { if (hblRfAvailable) hblNative.command="process " + (hblRfSameProcess ? "0" : "1"); }
    property int hblRfStepUs: 10''')
    files['/main.qml']=main
    page=(HERE/'ui/MechanicalFlashPage.qml').read_text(encoding='utf-8')
    start=page.index('        Row {\n            width: parent.width; height: 48')
    end=page.index('        Grid {',start)
    row='''        Row {
            width: parent.width; height: 44 * panel.unit; spacing: 8 * panel.unit
'''
    for label,value,action in [('自动引闪','hblRfEnabled','if (mainRoot.hblRfEnabled || (mainRoot.hblRfReady && !mainRoot.hblRfBusy)) mainRoot.hblRfConfigure(!mainRoot.hblRfEnabled)'),('每次准备','hblRfPerShot','mainRoot.hblRfTogglePerShot()'),('同一程序处理','hblRfSameProcess','mainRoot.hblRfToggleProcess()')]:
        row+='''            Rectangle {
                width: (parent.width-16*panel.unit)/3; height: parent.height; radius: 4
                color: mainRoot.%s ? "#805829" : "#303030"
                Text { anchors.centerIn: parent; text: "%s："+(mainRoot.%s ? "开" : "关"); color: "white"; font.pixelSize: 18*panel.unit }
                MouseArea { anchors.fill: parent; onClicked: %s }
            }
'''%(value,label,value,action)
    page=page[:start]+row+'        }\n'+page[end:]
    page=page.replace('spacing: 10 * panel.unit','spacing: 7 * panel.unit').replace('height: 48 * panel.unit','height: 42 * panel.unit').replace('height: 48*panel.unit','height: 42*panel.unit')
    files['/controlscreen/MechanicalFlashPage.qml']=page
    for name,text in files.items():
        p=OUT/'qml'/name.lstrip('/'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
    return files

def compile_clients():
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
    flags=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-fPIC','-fno-stack-protector',
           '-I',str(HERE/'build/mechanical-sync-candidate/include'),'-I',str(HERE/'native'),
           '-isystem',str(base/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),
           '-I',str(base/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations',
           '-Wno-enum-constexpr-conversion','-Wall','-Wextra','-Werror']
    layout=OUT/'relocations.ld'
    layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='ascii')
    libs=[baseline/('usr/lib/libQt5'+n+'.so.5.5.1') for n in ('Qml','Core','Network','DBus')]
    libs += [baseline/p for p in ('usr/lib/libappscommon.so.1.0.0','usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so')]
    objects={}
    for name,source,extra in [('worker','options_worker.cpp',[]),('embedded','options_worker.cpp',['-DHBL_OPTIONS_EMBEDDED=1']),('observer','options_observer.cpp',[]),('runtime','options_runtime.cpp',[])]:
        obj=OUT/(name+'.o'); run(['c++','-std=c++11']+flags+extra+['-c',str(OUT/source),'-o',str(obj)]); objects[name]=obj
    outputs=[]
    for name,inputs,shared in [('wireless-worker',['worker'],False),('libhbl-mechanical-observer.so',['embedded','observer'],True),('libhbl-wireless.so',['runtime'],True)]:
        output=OUT/name
        run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared' if shared else '-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)]+[str(objects[n]) for n in inputs]+list(map(str,libs))+['-o',str(output)])
        outputs.append(output)
    probe=(HERE/'native/netlink_probe.c').read_text(encoding='utf-8').replace('marker!=0x584e','marker!=0x5851')
    put('netlink_probe.c',probe)
    run(['cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-O2','-Wl,-s','-Wl,-T,'+str(layout),'-Wall','-Wextra','-Werror','-I',str(HERE/'native'),str(OUT/'netlink_probe.c'),'-o',str(OUT/'netlink-probe')])
    outputs.append(OUT/'netlink-probe')
    sys.path.insert(0,str(cache/'python'))
    from elftools.elf.elffile import ELFFile
    for path in outputs:
        elf=ELFFile(io.BytesIO(path.read_bytes())); rel=elf.get_section_by_name('.rel.dyn'); plt=elf.get_section_by_name('.rel.plt')
        assert rel['sh_addr']+rel['sh_size']==plt['sh_addr'],path.name
    sources=[Path(__file__)]+list(OUT.glob('*.cpp'))+list(OUT.glob('*.h'))+list(OUT.glob('*.c'))
    report={'passed':True,'outputs':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in outputs},'commands':commands,
            'sourceHashes':{str(p.relative_to(HERE)):sha(p.read_bytes()) for p in sources},'installed':False,'hardwareRequests':0,'physicalTimingVerified':False}
    put('client-build.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report['outputs']

def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    OUT.mkdir(exist_ok=True)
    baseline=json.loads((BASE/'client-build.json').read_text(encoding='utf-8'))
    for name,digest in baseline['sourceHashes'].items():
        if sha((HERE/name).read_bytes())!=digest: raise RuntimeError('Baseline changed: '+name)
    fw=firmware(); radio(); worker(); observer(); runtime(); ui()
    return {'firmware':fw,'clients':compile_clients()}

if __name__=='__main__': print(build())
