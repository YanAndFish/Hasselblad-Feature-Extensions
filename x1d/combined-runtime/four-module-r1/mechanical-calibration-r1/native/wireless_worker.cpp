#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "rf_core.h"
#include "rf_es_timing.h"
#include "rf_local_socket.h"
#include "farm_sync_wire.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qprocess.h>
#include <QtCore/qsavefile.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qtimer.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusservicewatcher.h>
#include <functional>
#include <signal.h>
#include <cstdio>
#include "rf_receiver.h"

// 原厂库中的常量访问器；不构造相机代理，也不调用相机方法。
class Bus {
public:
    static const QString &farmService();
};
namespace {
#include "prepared_radio.h"
volatile sig_atomic_t stopping=0;
void requestStop(int) { stopping=1; }

class Worker : public QObject {
public:
    explicit Worker(QObject *parent) : QObject(parent),radio(this),bus(QDBusConnection::systemBus()) {
        rf_init(&core,1);
        fd=rf_local_bind(RF_WORKER_SOCKET);
        if (fd<0) { record("worker-socket-failed"); return; }
        notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,
                         this,[this](int) { receive(); });
        syncFd=rf_local_bind(HBL_SYNC_SOCKET);
        const int passCredentials=1;
        if (syncFd<0 || setsockopt(syncFd,SOL_SOCKET,SO_PASSCRED,&passCredentials,sizeof(passCredentials))) {
            record("worker-sync-socket-failed"); return;
        }
        syncNotifier=new QSocketNotifier(syncFd,QSocketNotifier::Read,this);
        QObject::connect(syncNotifier,&QSocketNotifier::activated,this,[this](int) { receiveSync(); });
        timer.setSingleShot(true); timer.setTimerType(Qt::PreciseTimer);
        QObject::connect(&timer,&QTimer::timeout,this,[this]() { due(); });
        publishTimer.setSingleShot(true);
        QObject::connect(&publishTimer,&QTimer::timeout,this,[this]() { publish(); });
        radio.changed=[this]() { changed(); };
        radio.prepared=[this](bool ok) {
            if (!ok) { increment(RV_FAILURES); disable(QStringLiteral("无线准备失败：")+radio.errorStep); }
            else message=core.enabled ? QStringLiteral("已就绪；等待 FPGA 同步") : QStringLiteral("已就绪；可单次试闪，自动关闭");
            changed();
        };
        radio.completed=[this](bool sent,bool ok) {
            if (sent) increment(RV_SENT);
            if (!ok) { increment(RV_FAILURES); disable(QStringLiteral("无线请求失败：")+radio.errorStep); }
            else message=QStringLiteral("已提交一次引闪请求");
            changed();
        };
        refreshSourcePid();
        watcher=new QDBusServiceWatcher(Bus::farmService(),bus,QDBusServiceWatcher::WatchForOwnerChange,this);
        QObject::connect(watcher,&QDBusServiceWatcher::serviceOwnerChanged,this,
                         [this](const QString &,const QString &,const QString &) {
            syncEpoch=lastSyncShot=0;
            refreshSourcePid();
            disable(QStringLiteral("同步接收服务变化；自动引闪已关闭"));
            record(eventAlive ? "worker-ready-default-off" : "worker-event-unavailable");
        });
        heartbeat.setInterval(200);
        QObject::connect(&heartbeat,&QTimer::timeout,this,[this]() {
            if (stopping && !shuttingDown) {
                shuttingDown=true; disable(QStringLiteral("常驻程序正在退出"));
                QTimer::singleShot(1300,QCoreApplication::instance(),&QCoreApplication::quit);
            }
            if (!bus.isConnected() && eventAlive) {
                eventAlive=false; sourcePid=0; disable(QStringLiteral("同步接收通道断开")); record("worker-event-unavailable");
            }
            const uint64_t now=rf_monotonic_ms();
            if (session && (now<lastUi || now-lastUi>2000)) {
                disable(QStringLiteral("界面连接超时；自动引闪已关闭")); session=0;
            }
        });
        heartbeat.start();
        valid=eventAlive;
        message=eventAlive ? QStringLiteral("同步接收已就绪；自动引闪关闭") : QStringLiteral("同步接收尚未连接");
        record(eventAlive ? "worker-ready-default-off" : "worker-event-unavailable");
        publish();
    }
    ~Worker() override {
        if (fd>=0) { close(fd); unlink(RF_WORKER_SOCKET); }
        if (syncFd>=0) { close(syncFd); unlink(HBL_SYNC_SOCKET); }
    }
    bool valid=false;
private:
    Radio radio;
    QDBusConnection bus;
    QDBusServiceWatcher *watcher=nullptr;
    QSocketNotifier *notifier=nullptr,*syncNotifier=nullptr;
    QTimer timer,publishTimer,heartbeat;
    RfCore core;
    uint32_t counters[RV_COUNT]={};
    uint32_t session=0,revision=0,shot=0,eventSequence=0;
    uint32_t sourcePid=0,syncEpoch=0,lastSyncShot=0,syncPhases=0,lastSyncProgress=0;
    uint64_t lastUi=0,armedAt=0;
    int fd=-1,syncFd=-1,power=10;
    bool page=false,eventAlive=false,shuttingDown=false;
    QString message;
    void increment(unsigned index) { if (counters[index]<INT32_MAX) ++counters[index]; }
    void refreshSourcePid() {
        sourcePid=0;
        if (bus.isConnected() && bus.interface()) {
            const QDBusReply<uint> pid=bus.interface()->servicePid(Bus::farmService());
            if (pid.isValid()) sourcePid=pid.value();
        }
        eventAlive=sourcePid!=0 && syncFd>=0;
    }
    void record(const char *text) {
        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/worker.status"));
        if (file.open(QIODevice::WriteOnly)) { file.write(text); file.write("\n"); file.commit(); }
    }
    void changed() { if (!publishTimer.isActive()) publishTimer.start(20); }
    void cancelPending(const QString &why) {
        if (core.pending) { increment(RV_CANCELLED); message=why; }
        rf_cancel(&core); timer.stop();
    }
    void disable(const QString &why) {
        cancelPending(why); rf_configure(&core,0,core.source,core.delay_ms);
        page=false; radio.cancel(); message=why; changed();
    }
    void prepare() {
        if (!eventAlive || shuttingDown) { disable(QStringLiteral("同步接收不可用")); return; }
        if (core.enabled || page) {
            radio.prepare(power);
            message=radio.ready ? QStringLiteral("已就绪；设置已应用") : QStringLiteral("正在设置功率、生成并校验波形");
        } else radio.cancel();
        changed();
    }
    void transmit() {
        if (!eventAlive || radio.busy || !radio.ready) {
            increment(RV_BUSY_SKIPS); message=QStringLiteral("无线尚未就绪，本次跳过"); changed(); return;
        }
        // Radio 在回调或诊断输出前向常驻驱动 socket 提交唯一请求。
        if (radio.fire(power)) message=QStringLiteral("正在提交预先准备的波形");
        changed();
    }
    void due() { if (rf_due(&core,rf_monotonic_ms())) transmit(); changed(); }
    void receiveSync() {
        for (unsigned count=0;count<16;++count) {
            uint8_t bytes[64];
            union { cmsghdr alignment; char bytes[CMSG_SPACE(sizeof(ucred))]; } control={};
            iovec buffer={bytes,sizeof(bytes)};
            msghdr packet={}; packet.msg_iov=&buffer; packet.msg_iovlen=1;
            packet.msg_control=control.bytes; packet.msg_controllen=sizeof(control.bytes);
            const ssize_t received=recvmsg(syncFd,&packet,MSG_DONTWAIT);
            if (received<0) {
                if (errno==EAGAIN || errno==EWOULDBLOCK || errno==EINTR) return;
                eventAlive=false; disable(QStringLiteral("同步读取失败；自动引闪关闭")); return;
            }
            if (!eventAlive || shuttingDown || received!=ssize_t(sizeof(bytes)) ||
                (packet.msg_flags&(MSG_TRUNC|MSG_CTRUNC))) continue;
            const ucred *credentials=nullptr;
            bool duplicateCredentials=false;
            for (cmsghdr *item=CMSG_FIRSTHDR(&packet);item;item=CMSG_NXTHDR(&packet,item)) {
                if (item->cmsg_level==SOL_SOCKET && item->cmsg_type==SCM_CREDENTIALS &&
                    item->cmsg_len==CMSG_LEN(sizeof(ucred))) {
                    if (credentials) duplicateCredentials=true;
                    credentials=reinterpret_cast<const ucred *>(CMSG_DATA(item));
                }
            }
            if (!credentials || duplicateCredentials || credentials->uid!=geteuid() ||
                credentials->pid<=0 || uint32_t(credentials->pid)!=sourcePid) continue;
            HblFarmSync sample; uint32_t epoch; uint64_t arrival;
            if (!hbl_parse_sync_ipc(bytes,sizeof(bytes),&epoch,&sample,&arrival)) continue;
            const uint64_t now=rf_monotonic_ms(),at=arrival/1000000u;
            if (!at || at>now || now-at>2000) continue;
            if (syncEpoch && epoch!=syncEpoch) {
                disable(QStringLiteral("同步会话变化；自动引闪关闭"));
                syncEpoch=epoch; lastSyncShot=sample.shot; continue;
            }
            syncEpoch=epoch;
            const unsigned source=hbl_sync_source(sample.flags);
            if (source) continue; // 固定电子快门规则只使用 B。
            if (sample.shot<lastSyncShot) continue;
            const bool newShot=sample.shot>lastSyncShot;
            if (newShot) {
                lastSyncShot=sample.shot; syncPhases=0; lastSyncProgress=0;
                cancelPending(QStringLiteral("新拍摄撤销旧延迟"));
            }
            if (source==1) {
                if ((syncPhases&2) && sample.cleared_status<=lastSyncProgress) continue;
                lastSyncProgress=sample.cleared_status;
            } else if (syncPhases&(1u<<source)) continue;
            // 后续节点必须属于本接收器已确认 B 的同一次拍摄。
            if (source && !(syncPhases&1)) continue;
            syncPhases|=1u<<source;
            increment(RV_STARTS);
            if ((sample.flags&255)!=7) {
                if (!source) syncPhases=0;
                cancelPending(QStringLiteral("本次节点未确认"));
                increment(RV_READY_EVENTS);
                message=QStringLiteral("本次 FPGA 同步未确认，未自动引闪"); changed(); continue;
            }
            increment(RV_ENDS);
            if (!core.enabled || at<armedAt) {
                message=QStringLiteral("已确认 FPGA 同步；本次自动引闪未开启"); changed(); continue;
            }
            if (shot==UINT32_MAX || eventSequence>UINT32_MAX-2) {
                disable(QStringLiteral("同步计数耗尽")); return;
            }
            unsigned delay=0;
            if (!rf_es_center_delay(sample.exposure_low,sample.exposure_high,&delay)) {
                cancelPending(QStringLiteral("本次曝光不在电子快门引闪范围"));
                increment(RV_READY_EVENTS);
                message=QStringLiteral("本次未引闪：超过 0.5 秒或曝光参数未覆盖"); changed(); continue;
            }
            RfEvent begin={RF_BEGIN,1,++shot,0,1,++eventSequence};
            RfEvent phase={RF_PHASE,1,shot,0,0,++eventSequence};
            if (!rf_event(&core,&begin,at) || !rf_event(&core,&phase,at) ||
                !rf_es_set_deadline(&core,delay,at)) {
                disable(QStringLiteral("同步事件顺序异常")); return;
            }
            increment(RV_QUEUED);
            if (core.deadline_ms>now) {
                timer.start(int(core.deadline_ms-now)); message=QStringLiteral("电子快门自动引闪：等待 %1 ms").arg(delay);
            }
            else due();
            changed();
        }
    }
    void receive() {
        for (unsigned count=0;count<32;++count) {
            RfBridgePacket packet; char peer[108];
            const int result=rf_local_receive(fd,&packet,peer,sizeof(peer));
            if (!result) return;
            if (result<0 || std::strcmp(peer,RF_UI_SOCKET)) continue;
            const uint64_t now=rf_monotonic_ms(),at=rf_bridge_time(&packet);
            if (!at || at>now || now-at>2000) continue;
            if (packet.kind==RF_UI_HELLO) {
                if (packet.sequence) continue;
                if (packet.session!=session) {
                    disable(QStringLiteral("界面已连接；自动引闪关闭"));
                    session=packet.session; revision=0;
                }
                lastUi=now; changed(); continue;
            }
            if (!session || packet.session!=session) continue;
            lastUi=now;
            if (packet.kind==RF_UI_QUERY) { changed(); continue; }
            if (packet.kind==RF_UI_BYE) {
                if (packet.sequence>revision) { revision=packet.sequence; disable(QStringLiteral("界面退出；自动引闪关闭")); }
                changed(); continue;
            }
            if ((packet.kind!=RF_UI_CONFIG && packet.kind!=RF_UI_ARM && packet.kind!=RF_UI_TEST) || !rf_bridge_settings_valid(&packet)) continue;
            if (packet.sequence<=revision) { changed(); continue; }
            revision=packet.sequence;
            if (packet.kind==RF_UI_TEST) {
                increment(RV_CLICKS); cancelPending(QStringLiteral("单次试闪撤销待发延迟"));
                if (page && packet.values[RV_PAGE] && power==int(packet.values[RV_POWER])) transmit();
                else { increment(RV_BUSY_SKIPS); message=QStringLiteral("设置尚未确认，本次未发射"); }
                changed(); continue;
            }
            // 故障关闭之后，只有用户再次操作自动开关才能重开；旧设置快照不能重开。
            const unsigned nextOn=packet.values[RV_ON] && (core.enabled || packet.kind==RF_UI_ARM);
            if (nextOn && !core.enabled) armedAt=now;
            const bool different=core.enabled!=nextOn ||
                                 power!=int(packet.values[RV_POWER]) || page!=bool(packet.values[RV_PAGE]);
            if (different) cancelPending(QStringLiteral("设置变化撤销待发引闪"));
            rf_configure(&core,nextOn,0,0);
            rf_progress_configure(&core,0);
            power=int(packet.values[RV_POWER]); page=packet.values[RV_PAGE];
            if (different) prepare();
            changed();
        }
    }
    void publish() {
        RfBridgePacket packet;
        rf_bridge_init(&packet,RF_BRIDGE_STATUS,session ? session : 1,revision,rf_monotonic_ms());
        memcpy(packet.values,counters,sizeof(counters));
        packet.values[RV_ON]=core.enabled; packet.values[RV_DELAY]=core.delay_ms;
        packet.values[RV_SOURCE]=core.source;
        packet.values[RV_PROGRESS]=core.progress_threshold;
        packet.values[RV_POWER]=unsigned(power); packet.values[RV_PAGE]=page;
        packet.values[RV_BUSY]=radio.busy; packet.values[RV_ARMED]=radio.ready;
        packet.values[RV_EVENT_ALIVE]=eventAlive;
        const QByteArray utf8=message.toUtf8();
        memcpy(packet.text,utf8.constData(),qMin(size_t(utf8.size()),sizeof(packet.text)-1));
        if (session) rf_local_send(fd,RF_UI_SOCKET,&packet);
        const char *labels[]={"on","delay","gain","page","running","armed","event","click","fpga_samples","fpga_synced","fpga_skipped","queued","sent","fail","cancel","busy","source","progress"};
        QByteArray data;
        for (unsigned i=0;i<RV_COUNT;++i) data+=QByteArray(labels[i])+"="+QByteArray::number(packet.values[i])+" ";
        data+="pending="+QByteArray::number(core.pending)+"\n";
        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/diagnostics"));
        if (file.open(QIODevice::WriteOnly)) { file.write(data); file.commit(); }
    }
};
}
int main(int argc,char **argv) {
    QCoreApplication application(argc,argv);
    if (argc==2 && !std::strcmp(argv[1],"--check-slots")) {
        RfReceiver receiver; unsigned count=0;
        receiver.received=[&count]() { ++count; };
        for (unsigned i=0;i<3;++i)
            if (!QMetaObject::invokeMethod(&receiver,"receive",Qt::DirectConnection)) return 21;
        if (count!=3) return 22;
        std::puts("qt-receiver-check=3 hardware-requests=0"); return 0;
    }
    if (argc!=1) return 64;
    signal(SIGTERM,requestStop); signal(SIGINT,requestStop);
    Worker worker(&application);
    if (!worker.valid) return 20;
    return application.exec();
}
