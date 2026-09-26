#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "formal_policy.h"
#include "formal_radio.h"
#include "rf_local_socket.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qcoreevent.h>
#include <QtCore/qmutex.h>
#include <QtCore/qsavefile.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qthread.h>
#include <QtCore/qtimer.h>
#include <cstring>
#include <fcntl.h>

static_assert(unsigned(MechanicalDirectDispatch::Empty)==FormalPolicy::CancelEmpty &&
              unsigned(MechanicalDirectDispatch::Submitted)==FormalPolicy::CancelSubmitted &&
              unsigned(MechanicalDirectDispatch::Cancelled)==FormalPolicy::CancelConfirmed &&
              unsigned(MechanicalDirectDispatch::Failed)==FormalPolicy::CancelFailed,"取消结果映射必须一致");

/* 与自有同步 observer 同一进程；这里没有相机代理，也不发送相机命令。 */
namespace {
uint64_t formalNowUs() {
    timespec ts={};
    if(clock_gettime(CLOCK_MONOTONIC,&ts) || ts.tv_sec<0 || ts.tv_nsec<0) return 0;
    return uint64_t(ts.tv_sec)*1000000+uint64_t(ts.tv_nsec)/1000;
}
class FormalDelivery : public QEvent {
public:
    static QEvent::Type id() { static const int n=QEvent::registerEventType();return static_cast<QEvent::Type>(n); }
    FormalDelivery(uint32_t e,const HblMechanicalSync &s,uint64_t at):QEvent(id()),epoch(e),arrival(at),es(false),mech(s) {}
    FormalDelivery(uint32_t e,const HblFarmSync &s,uint64_t at):QEvent(id()),epoch(e),arrival(at),es(true),electronic(s) {}
    uint32_t epoch;uint64_t arrival;bool es;
    HblMechanicalSync mech={};HblFarmSync electronic={};
};
class FormalWorker : public QObject {
public:
    explicit FormalWorker(QObject *parent):QObject(parent),policy(false),radio(this) {
        policy.shutterPower=false;
        policy.halfPressPower=true;
        // 当前正式无线固件仍使用已验证的短波形入口。
        policy.batchEnabled=false;radio.batchEnabled=false;
        if(!radio.valid()) return;
        uint32_t mode=0,uid=0;
        if(rf_local_stat("/tmp/hbl-wireless-flash",&mode,&uid) || !S_ISDIR(mode) ||
            uid!=geteuid() || (mode&0777)!=0700) return;
        fd=rf_local_bind(HBL_FORMAL_WORKER_SOCKET);
        const int enabled=1;
        if(fd<0 || setsockopt(fd,SOL_SOCKET,SO_PASSCRED,&enabled,sizeof(enabled))) return;
        notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int) { receive(); });
        radio.completed=[this](FormalRadio::Operation operation,bool ok) {
            FormalPolicy::Action action=policy.activeAction();
            const bool expected=(operation==FormalRadio::Open && action==FormalPolicy::Open) ||
                (operation==FormalRadio::Select && (action==FormalPolicy::Select || action==FormalPolicy::Restore)) ||
                (operation==FormalRadio::Power && action==FormalPolicy::Power) ||
                (operation==FormalRadio::Batch && action==FormalPolicy::Batch) ||
                (operation==FormalRadio::Fire && action==FormalPolicy::Fire) ||
                (operation==FormalRadio::Close && action==FormalPolicy::Close);
            if(!expected) { policy.disconnect(formalNowUs());pump();return; }
            // Radio 的完成回调已核验驱动响应；额外核对 single buffer 实际状态。
            if(ok && (action==FormalPolicy::Open || action==FormalPolicy::Restore || action==FormalPolicy::Fire || action==FormalPolicy::Batch))
                ok=radio.held && radio.ready && radio.selectedIndex==HBL_FORMAL_FIRE_INDEX;
            if(ok && (action==FormalPolicy::Select || action==FormalPolicy::Power))
                ok=radio.held && radio.ready && radio.selectedIndex==policy.activeWave();
            policy.complete(action,ok,formalNowUs());pump();
        };
        heartbeat.setInterval(100);
        QObject::connect(&heartbeat,&QTimer::timeout,this,[this]() {
            const uint64_t now=formalNowUs();
            pollStopRequest(now);
            pollInstallationReady(now);
            if(__atomic_exchange_n(&deliveryOverflow,0,__ATOMIC_ACQ_REL)) policy.disconnect(now);
            if(session && (now<lastUiUs || now-lastUiUs>=uint64_t(FORMAL_DISCONNECT_MS)*1000)) {
                policy.disconnect(now);pump();session=0;revision=0;sourcePid=0;
            }
            policy.tick(formalNowUs());pump();
            reportStopResult();
        });
        heartbeat.start();
        valid=true;
        // 仅构造成功时写一次安装核验标记；deadline/同步回调绝不写文件。
        writeWorkerState("formal-worker-ready-default-off");
    }
    ~FormalWorker() override {
        radio.completed=nullptr;heartbeat.stop();
        if(fd>=0) { ::close(fd);::unlink(HBL_FORMAL_WORKER_SOCKET); }
    }
    bool valid=false;
    void deliver(uint32_t epoch,const HblMechanicalSync &sample,uint64_t arrivalNs) {
        if(QThread::currentThread()==thread()) {
            policy.mechanicalSample(epoch,sample,arrivalNs,formalNowUs());pump();return;
        }
        if(reserveDelivery()) QCoreApplication::postEvent(this,new FormalDelivery(epoch,sample,arrivalNs));
    }
    void deliver(uint32_t epoch,const HblFarmSync &sample,uint64_t arrivalNs) {
        if(QThread::currentThread()==thread()) {
            policy.electronicSample(epoch,sample,arrivalNs,formalNowUs());pump();return;
        }
        if(reserveDelivery()) QCoreApplication::postEvent(this,new FormalDelivery(epoch,sample,arrivalNs));
    }
    void customEvent(QEvent *event) override {
        if(event->type()!=FormalDelivery::id()) { QObject::customEvent(event);return; }
        __atomic_sub_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL);
        auto *item=static_cast<FormalDelivery *>(event);
        if(item->es) deliver(item->epoch,item->electronic,item->arrival);
        else deliver(item->epoch,item->mech,item->arrival);
    }
private:
    FormalPolicy policy;
    FormalRadio radio;
    QSocketNotifier *notifier=nullptr;
    QTimer heartbeat;
    int fd=-1;
    uint32_t session=0,revision=0,sourcePid=0;
    uint64_t lastUiUs=0,lastStatusUs=0;
    unsigned queuedDeliveries=0,deliveryOverflow=0;
    bool pumping=false;
    bool stopReported=false;
    bool enableConfirmedWritten=false;
    void writeWorkerState(const char *state) {
        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/formal-worker.status"));
        if(file.open(QIODevice::WriteOnly)) {
            file.write(state);file.write("\n");
            file.write("master="+QByteArray::number(unsigned(policy.master))+" radio-held="+
                       QByteArray::number(unsigned(radio.held))+" radio-busy="+QByteArray::number(unsigned(radio.busy))+
                       " same-process=1 pid="+QByteArray::number(getpid())+"\n");
            file.commit();
        }
    }
    void pollStopRequest(uint64_t nowUs) {
        // 固定路径只在100ms维护回调读取；同步接收/截止点提交路径没有文件IO。
        if(policy.stopLocked) return;
        const char *path="/tmp/hbl-wireless-flash/formal-stop.request";
        uint32_t mode=0,uid=0;
        if(rf_local_stat(path,&mode,&uid) || !S_ISREG(mode) || uid!=geteuid() || (mode&0777)!=0600) return;
        const int request=::open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
        if(request<0) return;
        char bytes[8]={};const ssize_t size=::read(request,bytes,sizeof(bytes));::close(request);
        if((size==4 && !std::memcmp(bytes,"stop",4)) || (size==5 && !std::memcmp(bytes,"stop\n",5)))
            policy.requestStop(nowUs);
    }
    void pollInstallationReady(uint64_t nowUs) {
        // 安装端完成FARM和默认关闭核验后才提供此固定文件；未通过不缓存开关意图。
        if(policy.stopLocked || enableConfirmedWritten) return;
        if(!policy.installationReady) {
            const char *path="/tmp/hbl-wireless-flash/formal-enable.ready";
            uint32_t mode=0,uid=0;
            if(rf_local_stat(path,&mode,&uid) || !S_ISREG(mode) || uid!=geteuid() || (mode&0777)!=0600) return;
            const int request=::open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
            if(request<0) return;
            char bytes[8]={};const ssize_t size=::read(request,bytes,sizeof(bytes));::close(request);
            if(!((size==5 && !std::memcmp(bytes,"ready",5)) || (size==6 && !std::memcmp(bytes,"ready\n",6)))) return;
            if(!policy.unlockInstallation(nowUs)) return;
        }
        if(!policy.canConfirmInstallationReady()) return;
        QSaveFile confirmed(QStringLiteral("/tmp/hbl-wireless-flash/formal-enable.confirmed"));
        if(confirmed.open(QIODevice::WriteOnly) && confirmed.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner) &&
            confirmed.write("ready\n",6)==6 && confirmed.commit()) enableConfirmedWritten=true;
    }
    void reportStopResult() {
        if(!policy.stopLocked || stopReported || policy.busy() || radio.busy) return;
        // Close,false绝不生成成功标记，未知的held状态也不能声称已经释放。
        const bool safe=policy.stoppedSafely(radio.held,radio.busy,radio.ready);
        writeWorkerState(safe ? "formal-worker-stopped-default-off" : "formal-worker-stop-failed");
        stopReported=true;
    }
    bool reserveDelivery() {
        if(__atomic_add_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL)<=256) return true;
        __atomic_sub_fetch(&queuedDeliveries,1,__ATOMIC_ACQ_REL);
        __atomic_store_n(&deliveryOverflow,1,__ATOMIC_RELEASE);return false;
    }
    bool sendPacket(const FormalPacket &packet) {
        sockaddr_un peer={};const int size=rf_local_address(&peer,HBL_FORMAL_UI_SOCKET);
        return session && fd>=0 && size && sendto(fd,&packet,sizeof(packet),MSG_DONTWAIT|MSG_NOSIGNAL,
            reinterpret_cast<const sockaddr *>(&peer),socklen_t(size))==ssize_t(sizeof(packet));
    }
    void status(unsigned kind=FORMAL_STATUS,uint32_t token=0,unsigned result=FORMAL_OK) {
        if(!session) return;
        FormalPacket p;formal_packet_init(&p,kind,session,revision,formalNowUs()/1000);
        p.values[FV_MASTER]=policy.master;p.values[FV_POWER]=policy.powerUpdates;p.values[FV_SYNC]=policy.flashSync;
        p.values[FV_READY]=policy.restored();p.values[FV_BUSY]=policy.busy();p.values[FV_EVENT_ALIVE]=policy.eventAlive;
        p.values[FV_PENDING]=policy.dirty;p.values[FV_ERROR]=policy.lastError;p.values[FV_RESULT]=result;p.values[FV_ACK_TOKEN]=token;
        p.values[FV_SHOT_ACTIVE]=policy.shotActive;
        p.values[FV_CHANNEL]=policy.channel;p.values[FV_ID]=policy.wirelessId;
        p.values[FV_RECONFIGURING]=policy.reconfiguring;
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) {
            p.values[FV_GROUP_A_ACTIVE+i*2]=policy.groups[i].active;
            p.values[FV_GROUP_A_TENTHS+i*2]=policy.groups[i].tenths;
            if(policy.lamps[i]) p.values[FV_LAMPS]|=1u<<i;
        }
        const char *message=policy.lastError==FORMAL_GROUPS_UNSENT ? "请开启功率更新以同步分组开关" :
            policy.reconfiguring ? "正在切换无线配置" :
            policy.lastError==FORMAL_TIMEOUT ? "准备超时；无线已关闭" :
            policy.lastError==FORMAL_RADIO_ERROR ? "无线请求失败；已关闭" :
            policy.lastError==FORMAL_UNAVAILABLE ? "连接不可用；无线已关闭" :
            policy.flushing ? "正在发送本次功率并恢复同步波形" :
            policy.master ? (policy.restored() ? "已开启" : "正在准备") : "已关闭";
        const QByteArray detail=policy.lastError==FORMAL_RADIO_ERROR ? radio.error.toUtf8() : QByteArray();
        std::strncpy(p.text,detail.isEmpty() ? message : detail.constData(),sizeof(p.text)-1);
        if(!sendPacket(p) && kind==FORMAL_FLUSH_ACK && result==FORMAL_OK) {
            // ACK 丢失时 UI 不续拍；撤销相应资格，禁止迟到事件触发。
            policy.cancel(token,formalNowUs());
        }
        lastStatusUs=formalNowUs();
    }
    void pump() {
        if(pumping) return;
        pumping=true;
        if(policy.takeCancelDispatch()) {
            formal_cancel_pending(policy,radio);
        }
        // 同步 deadline 的直接提交先于任何 UI 状态序列化。
        for(unsigned i=0;i<4;++i) {
            const FormalPolicy::Command command=policy.next(formalNowUs());
            if(command.action==FormalPolicy::None) break;
            bool accepted=false;
            switch(command.action) {
            case FormalPolicy::Open:accepted=radio.open(policy.channel,policy.wirelessId);break;
            case FormalPolicy::Select:case FormalPolicy::Restore:accepted=radio.select(command.wave);break;
            case FormalPolicy::Power:accepted=radio.sendPower();break;
            case FormalPolicy::Batch:accepted=radio.sendBatch(command.mask,command.indices);break;
            case FormalPolicy::Fire:accepted=radio.fire(command.deadlineUs);break;
            case FormalPolicy::Close:radio.close();accepted=true;break;
            default:break;
            }
            if(accepted) break;
            policy.complete(command.action,false,formalNowUs());
        }
        FormalPolicy::Ack ack;
        while(policy.popAck(&ack)) status(FORMAL_FLUSH_ACK,ack.token,ack.result);
        const uint64_t now=formalNowUs();
        if(!policy.syncPending() && (!lastStatusUs || now-lastStatusUs>=200000)) status();
        pumping=false;
    }
    void receive() {
        for(unsigned i=0;i<32;++i) {
            FormalPacket p={};sockaddr_un peer={};iovec body={&p,sizeof(p)};
            union { cmsghdr align;char bytes[CMSG_SPACE(sizeof(ucred))]; } control={};
            msghdr message={};message.msg_name=&peer;message.msg_namelen=sizeof(peer);
            message.msg_iov=&body;message.msg_iovlen=1;message.msg_control=control.bytes;message.msg_controllen=sizeof(control.bytes);
            const ssize_t bytes=recvmsg(fd,&message,MSG_DONTWAIT);
            if(bytes<0) {
                if(errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK) break;
                policy.disconnect(formalNowUs());break;
            }
            if((message.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) || !formal_packet_valid(&p,unsigned(bytes)) ||
                p.kind>=FORMAL_STATUS || peer.sun_family!=AF_UNIX ||
                message.msg_namelen<offsetof(sockaddr_un,sun_path)+sizeof(HBL_FORMAL_UI_SOCKET) ||
                message.msg_namelen>sizeof(peer) || std::memcmp(peer.sun_path,HBL_FORMAL_UI_SOCKET,sizeof(HBL_FORMAL_UI_SOCKET))) continue;
            const ucred *credentials=nullptr;bool duplicate=false;
            for(cmsghdr *c=CMSG_FIRSTHDR(&message);c;c=CMSG_NXTHDR(&message,c)) {
                if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_CREDENTIALS && c->cmsg_len==CMSG_LEN(sizeof(ucred))) {
                    if(credentials) duplicate=true;
                    credentials=reinterpret_cast<const ucred *>(CMSG_DATA(c));
                }
            }
            if(!credentials || duplicate || credentials->uid!=geteuid() || credentials->pid<=0) continue;
            const uint64_t now=formalNowUs(),at=formal_packet_time(&p);
            if(!now || at>now/1000 || now/1000-at>=FORMAL_DISCONNECT_MS) continue;
            if(p.kind==FORMAL_HELLO) {
                if(session!=p.session || sourcePid!=uint32_t(credentials->pid)) {
                    policy.newSession(now);pump();
                    session=p.session;revision=0;sourcePid=uint32_t(credentials->pid);
                    policy.setEventAlive(true,formalNowUs());
                }
                lastUiUs=now;status();continue;
            }
            if(!session || p.session!=session || sourcePid!=uint32_t(credentials->pid) || p.sequence<=revision) continue;
            revision=p.sequence;lastUiUs=now;
            switch(p.kind) {
            case FORMAL_HEARTBEAT:break;
            case FORMAL_OPTIONS:
                policy.setOptions(p.values[FV_MASTER],p.values[FV_POWER],p.values[FV_SYNC],now,at*1000);break;
            case FORMAL_GROUP:
                policy.updateGroup(p.values[FV_GROUP],p.values[FV_ACTIVE],p.values[FV_TENTHS],now);break;
            case FORMAL_WIRELESS:policy.setWireless(p.values[FV_CHANNEL],p.values[FV_ID],now);break;
            case FORMAL_LAMP:policy.updateLamp(p.values[FV_GROUP],p.values[FV_ACTIVE],now);break;
            case FORMAL_TEST:policy.test(now);break;
            case FORMAL_PREPARE:case FORMAL_FLUSH: {
                FormalPolicy::Group groups[HBL_FORMAL_GROUPS];
                for(unsigned j=0;j<HBL_FORMAL_GROUPS;++j) {
                    groups[j].active=p.values[FV_GROUP_A_ACTIVE+j*2];groups[j].tenths=p.values[FV_GROUP_A_TENTHS+j*2];
                }
                policy.flush(p.values[FV_TOKEN],formal_packet_exposure(&p),p.values[FV_ELECTRONIC],groups,now,&p.values[FV_CAL_125],p.kind==FORMAL_PREPARE,p.kind==FORMAL_PREPARE ? p.values[FV_LIST_MASK] : HBL_FORMAL_GROUP_MASK);break;
            }
            case FORMAL_QUEUE_SYNC:
                policy.queueSync(p.values[FV_TOKEN],formal_packet_exposure(&p),p.values[FV_ELECTRONIC],now);break;
            case FORMAL_CANCEL:policy.cancel(p.values[FV_TOKEN],now);break;
            case FORMAL_SHOT_END:policy.endShot(p.values[FV_TOKEN],now);break;
            case FORMAL_BYE:policy.disconnect(now);break;
            default:break;
            }
            pump();
            if(p.kind==FORMAL_BYE) { session=0;revision=0;sourcePid=0; }
        }
        pump();
    }
};
FormalWorker *formalWorker=nullptr;
QMutex formalDeliveryMutex;
}
extern "C" bool hbl_formal_begin() {
    QMutexLocker lock(&formalDeliveryMutex);
    if(formalWorker || !QCoreApplication::instance() ||
        QThread::currentThread()!=QCoreApplication::instance()->thread()) return false;
    formalWorker=new FormalWorker(QCoreApplication::instance());
    if(!formalWorker->valid) { delete formalWorker;formalWorker=nullptr;return false; }
    return true;
}
extern "C" void hbl_formal_deliver_mech(uint32_t epoch,const HblMechanicalSync *sample,uint64_t arrivalNs) {
    QMutexLocker lock(&formalDeliveryMutex);
    if(formalWorker && sample) formalWorker->deliver(epoch,*sample,arrivalNs);
}
extern "C" void hbl_formal_deliver_es(uint32_t epoch,const HblFarmSync *sample,uint64_t arrivalNs) {
    QMutexLocker lock(&formalDeliveryMutex);
    if(formalWorker && sample) formalWorker->deliver(epoch,*sample,arrivalNs);
}
extern "C" void hbl_formal_end() {
    QMutexLocker lock(&formalDeliveryMutex);
    delete formalWorker;formalWorker=nullptr;
}
