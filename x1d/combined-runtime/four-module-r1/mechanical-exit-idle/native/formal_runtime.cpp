#include "formal_bridge.h"
#include "rf_local_socket.h"
#include "formal_install_hold.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qfile.h>
#include <QtCore/qjsonarray.h>
#include <QtCore/qjsondocument.h>
#include <QtCore/qjsonobject.h>
#include <QtCore/qresource.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlpropertymap.h>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

#ifndef HBL_FORMAL_RUNTIME_STATUS_PATH
#define HBL_FORMAL_RUNTIME_STATUS_PATH "/tmp/hbl-wireless-flash/formal-runtime.status"
#endif
#ifndef HBL_FORMAL_RUNTIME_RCC_PATH
#define HBL_FORMAL_RUNTIME_RCC_PATH "/tmp/hbl-wireless-flash/formal-ui.rcc"
#endif

namespace {
bool requested() {
    const char *v=std::getenv("HBL_FORMAL_ENABLE_PLUGIN");
    return v && !std::strcmp(v,"1");
}
bool overlay=false;
class Runtime;
Runtime *runtime=nullptr;
void report(const char *text) {
    QFile file(QStringLiteral(HBL_FORMAL_RUNTIME_STATUS_PATH));
    if(file.open(QIODevice::WriteOnly|QIODevice::Truncate)) { file.write(text); file.write("\n"); }
}
bool integer(const QJsonObject &obj,const char *key,uint64_t max,uint64_t *out) {
    const QJsonValue value=obj.value(QString::fromLatin1(key));
    if(!value.isDouble()) return false;
    const double n=value.toDouble();
    if(!std::isfinite(n) || n<0 || n>double(max) || std::floor(n)!=n) return false;
    *out=uint64_t(n); return true;
}
class Runtime : public QQmlPropertyMap {
public:
    explicit Runtime(QQmlApplicationEngine *engine):QQmlPropertyMap(engine) {
        session=uint32_t(rf_monotonic_ms())^(uint32_t(getpid())<<16); if(!session) session=1;
        insert(QStringLiteral("command"),QString());
        const char *hold=std::getenv("HBL_FORMAL_INSTALL_HOLD");
        holdDeadline=hold && !std::strcmp(hold,"1") ? holdReadDeadline() : 0;
        insert(QStringLiteral("installationHold"),holdWindow(holdNow(),holdDeadline) && !holdReleased());
        insert(QStringLiteral("installPulse"),false);
        insert(QStringLiteral("connected"),false);
        insert(QStringLiteral("masterEnabled"),false); insert(QStringLiteral("masterRequested"),false);
        insert(QStringLiteral("sendPowerUpdates"),true); insert(QStringLiteral("sendFlashSync"),true);
        insert(QStringLiteral("adjustmentThirds"),true);
        insert(QStringLiteral("busy"),false); insert(QStringLiteral("ready"),false);
        insert(QStringLiteral("shotActive"),false);
        insert(QStringLiteral("supportedGroupCount"),HBL_FORMAL_GROUPS);
        insert(QStringLiteral("channel"),5); insert(QStringLiteral("wirelessId"),5);
        insert(QStringLiteral("statusText"),QString()); insert(QStringLiteral("errorText"),QString()); insert(QStringLiteral("flushAckToken"),0);
        insert(QStringLiteral("lastFlushToken"),0);
        insert(QStringLiteral("flushResult"),int(FORMAL_UNAVAILABLE));
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { active[i]=0; tenths[i]=40; publishGroup(i); }
        fd=rf_local_bind(HBL_FORMAL_UI_SOCKET);
        int credentials=1;
        if(fd<0 || setsockopt(fd,SOL_SOCKET,SO_PASSCRED,&credentials,sizeof(credentials))) {
            if(fd>=0) { close(fd); fd=-1; unlink(HBL_FORMAL_UI_SOCKET); } return;
        }
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int) { receive(); });
        timer.setInterval(FORMAL_HEARTBEAT_MS);
        QObject::connect(&timer,&QTimer::timeout,this,[this]() {
            const uint64_t now=rf_monotonic_ms();
            updateHold();
            if(connected && (now<lastReply || now-lastReply>=FORMAL_DISCONNECT_MS)) disconnect();
            if(pendingToken && (now<flushAt || now-flushAt>=6500)) cancelPending(FORMAL_TIMEOUT);
            send(connected ? FORMAL_HEARTBEAT : FORMAL_HELLO);
        });
        timer.start();
        QObject::connect(QCoreApplication::instance(),&QCoreApplication::aboutToQuit,this,[this]() { goodbye(); });
        QTimer::singleShot(0,this,[this]() { send(FORMAL_HELLO); });
    }
    ~Runtime() override {
        goodbye();
        if(fd>=0) { close(fd); unlink(HBL_FORMAL_UI_SOCKET); }
        if(runtime==this) runtime=nullptr;
    }
    bool usable() const { return fd>=0; }
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key==QStringLiteral("installPulse")) {
            updateHold();
            if(value(QStringLiteral("installationHold")).toBool()) {
                if(!holdAtomicPulse(unsigned(getpid()),holdDeadline,input.type()==QVariant::Bool && input.toBool() ? holdNow() : 0)) {
                    holdDeadline=0;insert(QStringLiteral("installationHold"),false);
                }
            }
            return false;
        }
        if(key!=QStringLiteral("command")) return value(key);
        const QByteArray bytes=input.toString().toUtf8();
        if(bytes.size()>1024 || leaving) return QVariant();
        QJsonParseError error;
        const QJsonDocument document=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject()) return QVariant();
        const QJsonObject o=document.object(); const QString op=o.value(QStringLiteral("op")).toString();
        if(op==QStringLiteral("options")) {
            if(o.size()!=4 || !o.value("master").isBool() || !o.value("power").isBool() || !o.value("sync").isBool()) return QVariant();
            const bool nextMaster=o.value("master").toBool();
            power=o.value("power").toBool(); sync=o.value("sync").toBool();
            insert(QStringLiteral("sendPowerUpdates"),power); insert(QStringLiteral("sendFlashSync"),sync);
            masterRequested=nextMaster && connected;
            insert(QStringLiteral("masterRequested"),masterRequested);
            if(!masterRequested) { masterAcknowledged=false; insert(QStringLiteral("masterEnabled"),false); cancelPending(FORMAL_CANCELLED); }
            if(connected) options();
        } else if(op==QStringLiteral("step")) {
            if(o.size()!=2 || !o.value("thirds").isBool()) return QVariant();
            // 仅保留本次界面调节偏好；不因此改变功率或提交无线请求。
            insert(QStringLiteral("adjustmentThirds"),o.value("thirds").toBool());
        } else if(op==QStringLiteral("wireless")) {
            uint64_t channel=0,id=0;
            if(o.size()!=3 || !integer(o,"channel",32,&channel) || !channel || !integer(o,"id",99,&id)) return QVariant();
            if(!connected) return QVariant();
            cancelPending(FORMAL_CANCELLED);
            if(activeToken) {
                FormalPacket cancel;init(cancel,FORMAL_CANCEL);cancel.values[FV_TOKEN]=activeToken;transmit(cancel);activeToken=0;
            }
            FormalPacket p;init(p,FORMAL_WIRELESS);wirelessSequence=p.sequence;
            p.values[FV_CHANNEL]=uint32_t(channel);p.values[FV_ID]=uint32_t(id);
            insert(QStringLiteral("ready"),false);insert(QStringLiteral("busy"),true);
            if(!transmit(p)) { disconnect();return QVariant(); }
            insert(QStringLiteral("channel"),int(channel));insert(QStringLiteral("wirelessId"),int(id));
        } else if(op==QStringLiteral("lamp")) {
            uint64_t group=0;
            if(o.size()!=3 || !integer(o,"group",HBL_FORMAL_GROUPS-1,&group) || !o.value("on").isBool() || !connected || !masterRequested) return QVariant();
            lamps[group]=o.value("on").toBool();publishGroup(unsigned(group));
            FormalPacket p;init(p,FORMAL_LAMP);p.values[FV_GROUP]=uint32_t(group);p.values[FV_ACTIVE]=lamps[group];
            if(!transmit(p)) disconnect();
        } else if(op==QStringLiteral("group")) {
            uint64_t group=0,powerValue=0;
            if(o.size()!=4 || !integer(o,"group",HBL_FORMAL_GROUPS-1,&group) || !integer(o,"tenthStops",80,&powerValue) || !o.value("active").isBool()) return QVariant();
            active[group]=o.value("active").toBool(); tenths[group]=uint32_t(powerValue); publishGroup(unsigned(group));
            if(connected) groupUpdate(unsigned(group));
        } else if(op==QStringLiteral("cancelCurrent")) {
            if(o.size()!=1) return QVariant();
            cancelPending(FORMAL_CANCELLED);
        } else if(op==QStringLiteral("test")) {
            if(o.size()!=1 || !connected || !masterRequested || !value(QStringLiteral("masterEnabled")).toBool() ||
               !sync || !value(QStringLiteral("ready")).toBool() || value(QStringLiteral("busy")).toBool() ||
               pendingToken || activeToken || value(QStringLiteral("shotActive")).toBool()) return QVariant();
            send(FORMAL_TEST); // 一次请求，无自动重试；worker 再次检查同步开关及忙状态。
        } else if(op==QStringLiteral("flush")) {
            uint64_t token=0,exposure=0;
            if(o.size()!=4 || !integer(o,"token",INT32_MAX,&token) || !token ||
               !integer(o,"exposureUs",UINT64_C(86400000000),&exposure) || !exposure || !o.value("electronic").isBool()) return QVariant();
            if(token<=lastToken) return QVariant(); // stale UI actions cannot replace an active request.
            lastToken=uint32_t(token);
            insert(QStringLiteral("lastFlushToken"),int(lastToken));
            if(pendingToken || activeToken || !connected || !masterRequested || !value(QStringLiteral("masterEnabled")).toBool()) {
                acknowledge(uint32_t(token),FORMAL_REJECTED); return QVariant();
            }
            FormalPacket p; init(p,FORMAL_FLUSH);
            p.values[FV_TOKEN]=uint32_t(token); p.values[FV_ELECTRONIC]=o.value("electronic").toBool();
            p.values[FV_EXPOSURE_LO]=uint32_t(exposure); p.values[FV_EXPOSURE_HI]=uint32_t(exposure>>32);
            for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) { p.values[FV_GROUP_A_ACTIVE+2*i]=active[i]; p.values[FV_GROUP_A_TENTHS+2*i]=tenths[i]; }
            pendingToken=uint32_t(token); flushAt=rf_monotonic_ms();
            if(!transmit(p)) cancelPending(FORMAL_UNAVAILABLE);
        } else if(op==QStringLiteral("cancel") || op==QStringLiteral("shotEnd")) {
            uint64_t token=0;
            if(o.size()!=2 || !integer(o,"token",INT32_MAX,&token) || !token) return QVariant();
            if(token!=pendingToken && token!=activeToken) return QVariant();
            const bool cancel=op==QStringLiteral("cancel");
            FormalPacket p; init(p,cancel ? FORMAL_CANCEL : FORMAL_SHOT_END); p.values[FV_TOKEN]=uint32_t(token); transmit(p);
            if(token==pendingToken) pendingToken=0;
            if(token==activeToken) activeToken=0;
        }
        return QVariant();
    }
private:
    uint64_t holdDeadline=0;
    void updateHold() {
        if(!holdWindow(holdNow(),holdDeadline) || holdReleased()) holdDeadline=0;
        insert(QStringLiteral("installationHold"),holdDeadline!=0);
    }
    int fd=-1;
    uint32_t session=0,sequence=0,lastAccepted=0,optionsSequence=0,wirelessSequence=0;
    uint32_t pendingToken=0,activeToken=0,lastToken=0,active[HBL_FORMAL_GROUPS],tenths[HBL_FORMAL_GROUPS],lamps[HBL_FORMAL_GROUPS]={};
    uint64_t lastReply=0,flushAt=0;
    bool connected=false,masterRequested=false,masterAcknowledged=false,power=true,sync=true,leaving=false;
    QTimer timer;
    void publishGroup(unsigned i) {
        insert(QStringLiteral("lamp")+QString::number(i),bool(lamps[i]));
        insert(QStringLiteral("active")+QString::number(i),bool(active[i]));
        insert(QStringLiteral("tenthStops")+QString::number(i),int(tenths[i]));
    }
    void init(FormalPacket &p,unsigned kind) {
        formal_packet_init(&p,kind,session,kind==FORMAL_HELLO ? 0 : ++sequence,rf_monotonic_ms());
    }
    bool transmit(const FormalPacket &p) {
        if(fd<0 || !formal_packet_valid(&p,sizeof(p)) || (!p.sequence && p.kind!=FORMAL_HELLO)) return false;
        sockaddr_un peer; const int len=rf_local_address(&peer,HBL_FORMAL_WORKER_SOCKET);
        return len && sendto(fd,&p,sizeof(p),MSG_DONTWAIT|MSG_NOSIGNAL,reinterpret_cast<sockaddr *>(&peer),socklen_t(len))==ssize_t(sizeof(p));
    }
    bool send(unsigned kind) { if(sequence==UINT32_MAX) return false; FormalPacket p; init(p,kind); return transmit(p); }
    void options() {
        FormalPacket p; init(p,FORMAL_OPTIONS); optionsSequence=p.sequence;
        p.values[FV_MASTER]=masterRequested; p.values[FV_POWER]=power; p.values[FV_SYNC]=sync;
        if(!transmit(p)) disconnect();
    }
    void groupUpdate(unsigned group) {
        FormalPacket p; init(p,FORMAL_GROUP); p.values[FV_GROUP]=group;
        p.values[FV_ACTIVE]=active[group]; p.values[FV_TENTHS]=tenths[group];
        if(!transmit(p)) disconnect();
    }
    void acknowledge(uint32_t token,unsigned result) {
        insert(QStringLiteral("flushResult"),int(result));
        insert(QStringLiteral("flushAckToken"),int(token));
    }
    void cancelPending(unsigned result) {
        if(!pendingToken) return;
        const uint32_t token=pendingToken; pendingToken=0;
        FormalPacket p; init(p,FORMAL_CANCEL); p.values[FV_TOKEN]=token; transmit(p);
        acknowledge(token,result);
    }
    void disconnect() {
        cancelPending(FORMAL_UNAVAILABLE); activeToken=0;
        connected=false; masterRequested=false; masterAcknowledged=false;
        insert(QStringLiteral("connected"),false); insert(QStringLiteral("masterEnabled"),false);
        insert(QStringLiteral("masterRequested"),false); insert(QStringLiteral("ready"),false); insert(QStringLiteral("busy"),false);
        insert(QStringLiteral("shotActive"),false);
        sequence=0; lastAccepted=0; optionsSequence=0; wirelessSequence=0; if(!++session) ++session;
    }
    void goodbye() {
        if(leaving) return;
        cancelPending(FORMAL_CANCELLED); send(FORMAL_BYE); leaving=true; timer.stop();
    }
    void receive() {
        for(unsigned n=0;n<32;++n) {
            FormalPacket p; sockaddr_un peer; iovec io={&p,sizeof(p)}; msghdr msg;
            union { cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(ucred))]; } control;
            std::memset(&peer,0,sizeof(peer)); std::memset(&msg,0,sizeof(msg)); std::memset(&control,0,sizeof(control));
            msg.msg_name=&peer; msg.msg_namelen=sizeof(peer); msg.msg_iov=&io; msg.msg_iovlen=1;
            msg.msg_control=control.bytes; msg.msg_controllen=sizeof(control.bytes);
            const ssize_t count=recvmsg(fd,&msg,MSG_DONTWAIT);
            if(count<0) return;
            bool sameUid=false;
            for(cmsghdr *c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c))
                if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_CREDENTIALS && c->cmsg_len==CMSG_LEN(sizeof(ucred))) {
                    ucred credential; std::memcpy(&credential,CMSG_DATA(c),sizeof(credential)); sameUid=credential.uid==geteuid();
                }
            const unsigned base=offsetof(sockaddr_un,sun_path);
            if((msg.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) || !sameUid || peer.sun_family!=AF_UNIX ||
               msg.msg_namelen<=base || msg.msg_namelen>sizeof(peer) ||
               !std::memchr(peer.sun_path,0,msg.msg_namelen-base) || std::strcmp(peer.sun_path,HBL_FORMAL_WORKER_SOCKET) ||
               !formal_packet_valid(&p,unsigned(count)) || p.session!=session || p.sequence>sequence ||
               (p.kind!=FORMAL_STATUS && p.kind!=FORMAL_FLUSH_ACK)) continue;
            const uint64_t now=rf_monotonic_ms(),at=formal_packet_time(&p);
            if(at>now || now-at>=FORMAL_DISCONNECT_MS || p.sequence<lastAccepted) continue;
            lastAccepted=p.sequence; lastReply=now;
            const bool first=!connected; connected=true; insert(QStringLiteral("connected"),true);
            if(first) {
                masterRequested=false; options();
                for(unsigned i=0;i<HBL_FORMAL_GROUPS && connected;++i) groupUpdate(i);
                if(!connected) return;
            }
            if(p.sequence>=wirelessSequence) {
                insert(QStringLiteral("busy"),bool(p.values[FV_BUSY])); insert(QStringLiteral("ready"),bool(p.values[FV_READY]));
                insert(QStringLiteral("channel"),int(p.values[FV_CHANNEL]));insert(QStringLiteral("wirelessId"),int(p.values[FV_ID]));
                insert(QStringLiteral("statusText"),QString::fromUtf8(p.text));
                insert(QStringLiteral("errorText"),p.values[FV_ERROR]!=FORMAL_OK && p.values[FV_ERROR]!=FORMAL_CANCELLED ? QString::fromUtf8(p.text) : QString());
            }
            insert(QStringLiteral("shotActive"),bool(p.values[FV_SHOT_ACTIVE]));
            if(p.sequence>=optionsSequence) {
                if(!p.values[FV_MASTER]) {
                    masterAcknowledged=false;
                    if(masterRequested) { masterRequested=false; insert(QStringLiteral("masterRequested"),false); }
                } else if(masterRequested && (p.values[FV_READY] || (!p.values[FV_POWER] && !p.values[FV_SYNC]))) {
                    masterAcknowledged=true;
                }
                // 开启后正常功率切波形期间继续显示开启；第一次开启须准备已完成。
                insert(QStringLiteral("masterEnabled"),bool(masterRequested && masterAcknowledged && p.values[FV_MASTER]));
            }
            if(p.kind==FORMAL_FLUSH_ACK && p.values[FV_ACK_TOKEN]==pendingToken && pendingToken) {
                const uint32_t token=pendingToken;
                if(now<flushAt || now-flushAt>=6500) { cancelPending(FORMAL_TIMEOUT); continue; }
                pendingToken=0;
                if(p.values[FV_RESULT]==FORMAL_OK) activeToken=token;
                acknowledge(token,p.values[FV_RESULT]);
            }
        }
    }
};
}

extern "C" bool hbl_formal_register(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool hbl_formal_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Register=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Register>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original) return false;
    if(requested() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay)
        overlay=QResource::registerResource(QStringLiteral(HBL_FORMAL_RUNTIME_RCC_PATH));
    return original(version,tree,names,data);
}
extern "C" void hbl_formal_load(QQmlApplicationEngine *,const QUrl &)
    __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void hbl_formal_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Load=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) return;
    if(requested() && overlay && !runtime) {
        runtime=new Runtime(engine);
        if(runtime->usable()) engine->rootContext()->setContextProperty(QStringLiteral("hblNative"),runtime);
        else { delete runtime; runtime=nullptr; }
    }
    original(engine,url);
    if(requested()) {
        if(!overlay) report("resource-overlay-unavailable");
        else if(!runtime) report("formal-adapter-unavailable");
        else if(engine->rootObjects().isEmpty()) report("qml-root-failed");
        else {
#ifdef HBL_FORMAL_EXTRA_QML_COMPONENTS
            const char *components[]={HBL_FORMAL_EXTRA_QML_COMPONENTS};
            for(const char *path:components) {
                QQmlComponent component(engine,QUrl(QString::fromLatin1(path)));
                if(component.isError() || !component.isReady()) {
                    report("combined-qml-component-failed");
                    return;
                }
            }
#endif
            // 仅编译动态页面；不 create，不访问相机，也不因验证准备或发送无线。
            QQmlComponent flashPage(engine,QUrl(QStringLiteral("qrc:/controlscreen/NativeFlashPage.qml")));
            QQmlComponent exposureGate(engine,QUrl(QStringLiteral("qrc:/FormalExposureGate.qml")));
            QQmlComponent controlPage(engine,QUrl(QStringLiteral("qrc:/controlscreen/ControlScreen.qml")));
            if(flashPage.isError() || exposureGate.isError() || controlPage.isError())
                report("formal-qml-component-failed");
            else if(!flashPage.isReady() || !exposureGate.isReady() || !controlPage.isReady())
                report("formal-qml-component-unavailable");
            else report("formal-ui-loaded-default-off");
        }
    }
}
