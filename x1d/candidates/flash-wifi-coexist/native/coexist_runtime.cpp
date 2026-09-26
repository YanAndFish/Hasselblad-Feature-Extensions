#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "formal_bridge.h"
#include "coexist_core.h"
#include "wpa_monitor.h"
#include "network_handoff.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qfile.h>
#include <QtCore/qsavefile.h>
#include <QtCore/qjsondocument.h>
#include <QtCore/qjsonobject.h>
#include <QtCore/qresource.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlpropertymap.h>
#include <cmath>
#include <cstdlib>
#include <dlfcn.h>

namespace {
bool enabledByEnvironment() {const char *value=getenv("HBL_COEXIST_ENABLE_PLUGIN");return value && !strcmp(value,"1");}
bool overlay=false;
bool integer(const QJsonObject &object,const char *key,uint64_t limit,uint64_t *out) {
    const QJsonValue value=object.value(QString::fromLatin1(key));
    if(!value.isDouble())return false;
    const double number=value.toDouble();
    if(!std::isfinite(number) || number<0 || number>double(limit) || floor(number)!=number)return false;
    *out=uint64_t(number);return true;
}
class Runtime : public QQmlPropertyMap {
public:
    explicit Runtime(QQmlApplicationEngine *engine):QQmlPropertyMap(engine),monitor(this),network(this),core(12000) {
        session=uint32_t(rf_monotonic_ms())^(uint32_t(getpid())<<16);if(!session)session=1;
        insert(QStringLiteral("command"),QString());
        insert(QStringLiteral("enabled"),false);insert(QStringLiteral("connected"),false);
        insert(QStringLiteral("networkReady"),false);insert(QStringLiteral("ready"),false);
        insert(QStringLiteral("busy"),false);insert(QStringLiteral("continueToken"),0);
        insert(QStringLiteral("cancelToken"),0);insert(QStringLiteral("lastToken"),0);
        insert(QStringLiteral("statusText"),QStringLiteral("Wi-Fi test: off"));
        fd=rf_local_bind(HBL_FORMAL_UI_SOCKET);int pass=1;
        if(fd<0 || setsockopt(fd,SOL_SOCKET,SO_PASSCRED,&pass,sizeof(pass)))return;
        notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int){receive();});
        network.finished=[this](coexist::NetworkHandoff::Operation operation,bool ok){networkDone(operation,ok);};
        monitor.changed=[this](){
            core.networkStatus(monitor.ready());
            if(waitingRecovery && monitor.ready())finishRecovery(true);
            publish();
        };
        heartbeat.setInterval(100);
        QObject::connect(&heartbeat,&QTimer::timeout,this,[this](){tick();});heartbeat.start();
        QObject::connect(QCoreApplication::instance(),&QCoreApplication::aboutToQuit,this,[this](){goodbye();});
        QTimer::singleShot(0,this,[this](){send(FORMAL_HELLO);});
    }
    ~Runtime() override {
        goodbye();network.finished=nullptr;monitor.changed=nullptr;
        if(fd>=0) {::close(fd);::unlink(HBL_FORMAL_UI_SOCKET);}
    }
    bool usable() const {return fd>=0;}
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key!=QStringLiteral("command"))return value(key);
        const QByteArray bytes=input.toString().toUtf8();if(bytes.size()>512 || leaving)return QVariant();
        QJsonParseError error;const QJsonDocument document=QJsonDocument::fromJson(bytes,&error);
        if(error.error!=QJsonParseError::NoError || !document.isObject())return QVariant();
        const QJsonObject object=document.object();const QString op=object.value(QStringLiteral("op")).toString();
        if(op==QStringLiteral("enable") && object.size()==2 && object.value("on").isBool()) {
            const bool on=object.value("on").toBool();
            if(on && (!connected || !released || !monitor.ready() || !installReady))return QVariant();
            core.enable(on);pump();publish();return QVariant();
        }
        uint64_t token=0;
        if(!integer(object,"token",INT32_MAX,&token) || !token)return QVariant();
        if(op==QStringLiteral("begin")) {
            uint64_t exposure=0;
            if(object.size()!=4 || !integer(object,"exposureUs",UINT64_C(86400000000),&exposure) ||
               !exposure || !object.value("electronic").isBool() || !connected || !released || !installReady)return QVariant();
            if(core.press(uint32_t(token),rf_monotonic_ms())) {
                exposureUs=exposure;electronic=object.value("electronic").toBool();
                insert(QStringLiteral("lastToken"),int(token));pump();
            } else insert(QStringLiteral("cancelToken"),int(token));
        } else if(op==QStringLiteral("continueAck")) {
            if(object.size()!=3 || !object.value("ok").isBool() || command.action!=coexist::Action::ContinueExposure || token!=command.token)return QVariant();
            complete(object.value("ok").toBool());
        } else if(op==QStringLiteral("cancel") && object.size()==2 && token==core.token) {
            core.cancel(rf_monotonic_ms());pump();
        } else if(op==QStringLiteral("shotEnd") && object.size()==2) {
            core.shotEnded(uint32_t(token),rf_monotonic_ms());pump();
        }
        publish();return QVariant();
    }
private:
    coexist::WpaMonitor monitor;coexist::NetworkHandoff network;coexist::Core core;
    coexist::Command command;
    int fd=-1;QSocketNotifier *notifier=nullptr;QTimer heartbeat;
    uint32_t session=0,sequence=0,lastAccepted=0,workerPid=0,barrier=0,flushSequence=0;
    uint64_t lastReply=0,lastSent=0,exposureUs=0,recoveryAt=0,lastReport=0;
    bool connected=false,released=false,installReady=false,leaving=false,electronic=false;
    bool waitingOpen=false,waitingClose=false,waitingPower=false,waitingRecovery=false;
    bool pumping=false;
    void init(FormalPacket &packet,unsigned kind) {
        formal_packet_init(&packet,kind,session,kind==FORMAL_HELLO ? 0 : ++sequence,rf_monotonic_ms());
    }
    bool transmit(const FormalPacket &packet) {
        if(fd<0 || sequence==UINT32_MAX || !formal_packet_valid(&packet,sizeof(packet)))return false;
        sockaddr_un target={};const int length=rf_local_address(&target,HBL_FORMAL_WORKER_SOCKET);
        return length && sendto(fd,&packet,sizeof(packet),MSG_DONTWAIT|MSG_NOSIGNAL,
            reinterpret_cast<sockaddr *>(&target),socklen_t(length))==ssize_t(sizeof(packet));
    }
    bool send(unsigned kind) {FormalPacket packet;init(packet,kind);return transmit(packet);}
    bool options(bool on) {
        FormalPacket packet;init(packet,FORMAL_OPTIONS);barrier=packet.sequence;
        packet.values[FV_MASTER]=on;packet.values[FV_POWER]=1;packet.values[FV_SYNC]=1;
        return transmit(packet);
    }
    bool shotMessage(unsigned kind) {
        FormalPacket packet;init(packet,kind);packet.values[FV_TOKEN]=core.token;return transmit(packet);
    }
    bool flush() {
        FormalPacket packet;init(packet,FORMAL_FLUSH);flushSequence=packet.sequence;
        packet.values[FV_TOKEN]=core.token;packet.values[FV_ELECTRONIC]=electronic;
        packet.values[FV_EXPOSURE_LO]=uint32_t(exposureUs);packet.values[FV_EXPOSURE_HI]=uint32_t(exposureUs>>32);
        // 同步所有组的开关，防止灯端遗留的其他组参与本次广播引闪。
        for(unsigned i=0;i<HBL_FORMAL_GROUPS;++i) {
            packet.values[FV_GROUP_A_ACTIVE+2*i]=i==coexist::GroupD;
            packet.values[FV_GROUP_A_TENTHS+2*i]=coexist::PowerTenths;
        }
        return transmit(packet);
    }
    void complete(bool ok) {
        const coexist::Command done=command;command=coexist::Command();
        core.complete(done,ok,rf_monotonic_ms());pump();publish();
    }
    void pump() {
        if(pumping)return;pumping=true;
        for(unsigned count=0;count<8;++count) {
            if(command.action!=coexist::Action::None)break;
            command=core.take();if(command.action==coexist::Action::None)break;
            bool accepted=true;
            switch(command.action) {
            case coexist::Action::SaveNetwork:accepted=monitor.ready() && network.start(coexist::NetworkHandoff::Save);break;
            case coexist::Action::OpenFlash:accepted=monitor.beginWindow() && network.start(coexist::NetworkHandoff::Suspend);break;
            case coexist::Action::SendPower:waitingPower=true;accepted=flush();break;
            case coexist::Action::ContinueExposure:insert(QStringLiteral("continueToken"),int(core.token));break;
            case coexist::Action::CancelShot:
                // 仅出现在尚未获 QML 续拍确认的路径；不发送 Camera.stopExposing。
                insert(QStringLiteral("cancelToken"),int(core.token));shotMessage(FORMAL_CANCEL);
                {const auto done=command;command=coexist::Command();core.complete(done,true,rf_monotonic_ms());}continue;
            case coexist::Action::CloseFlash:
                insert(QStringLiteral("cancelToken"),int(core.token));
                waitingOpen=waitingPower=false;waitingClose=true;
                accepted=shotMessage(FORMAL_SHOT_END) && options(false);break;
            case coexist::Action::RestoreNetwork:accepted=network.start(coexist::NetworkHandoff::Restore);break;
            default:accepted=false;break;
            }
            if(accepted)break;
            waitingOpen=waitingPower=waitingClose=false;
            const auto done=command;command=coexist::Command();core.complete(done,false,rf_monotonic_ms());
        }
        pumping=false;
    }
    void networkDone(coexist::NetworkHandoff::Operation operation,bool ok) {
        if(operation==coexist::NetworkHandoff::Save && command.action==coexist::Action::SaveNetwork) {
            complete(ok && monitor.ready());return;
        }
        if(operation==coexist::NetworkHandoff::Suspend && command.action==coexist::Action::OpenFlash) {
            if(!ok) {complete(false);return;}
            waitingOpen=true;
            if(!options(true)) {waitingOpen=false;complete(false);}return;
        }
        if(operation==coexist::NetworkHandoff::Restore && command.action==coexist::Action::RestoreNetwork) {
            if(!ok) {finishRecovery(false);return;}
            waitingRecovery=true;recoveryAt=rf_monotonic_ms();
            if(monitor.ready())finishRecovery(true);
        }
    }
    void finishRecovery(bool ok) {
        waitingRecovery=false;
        if(ok)ok=monitor.finishWindow();
        writeTrial(ok);complete(ok);
    }
    void writeTrial(bool restored) {
        const coexist::Evidence &e=monitor.evidence;
        QJsonObject result;
        result["token"]=int(core.token);result["networkRestored"]=restored;
        result["disconnectEvents"]=int(e.disconnects);result["connectEvents"]=int(e.connects);
        result["associationFailures"]=int(e.associationFailures);result["observationGap"]=e.gap;
        result["noDisconnectEventObserved"]=e.noObservedDisconnect();
        result["addressUnchanged"]=monitor.addressUnchanged();result["peerUnchanged"]=monitor.peerUnchanged();
        result["roundTripMs"]=e.returnAt>=e.awayAt ? double(e.returnAt-e.awayAt) : -1.;
        result["physicalFlashVerified"]=false;result["printsSent"]=0;result["photosRead"]=0;
        QSaveFile file(QStringLiteral("/tmp/hbl-flash-wifi-coexist/trial-")+QString::number(core.token)+QStringLiteral(".json"));
        if(file.open(QIODevice::WriteOnly)) {file.write(QJsonDocument(result).toJson(QJsonDocument::Compact));file.write("\n");file.commit();}
    }
    void publish() {
        const bool idle=core.phase==coexist::Phase::Network || core.phase==coexist::Phase::Disabled;
        insert(QStringLiteral("enabled"),core.enabled);insert(QStringLiteral("connected"),connected);
        insert(QStringLiteral("networkReady"),monitor.ready());
        insert(QStringLiteral("ready"),core.enabled && idle && connected && released && installReady && monitor.ready());
        insert(QStringLiteral("busy"),!idle);
        QString text;
        if(core.phase==coexist::Phase::Fault)text=QStringLiteral("Wi-Fi test: stopped; inspect result");
        else if(!idle)text=QStringLiteral("Wi-Fi / flash handoff");
        else if(!connected || !installReady)text=QStringLiteral("Wi-Fi test: flash unavailable");
        else if(!monitor.ready())text=QStringLiteral("Wi-Fi test: hotspot unavailable");
        else text=core.enabled ? QStringLiteral("CH5 ID5 D 1/8 | ready") : QStringLiteral("Wi-Fi test: off");
        insert(QStringLiteral("statusText"),text);
    }
    void tick() {
        const uint64_t now=rf_monotonic_ms();
        if(connected && (now<lastReply || now-lastReply>=FORMAL_DISCONNECT_MS)) {
            connected=false;released=false;installReady=false;
            core.cancel(now);
            // 丢失 worker 进程后不接纳另一个进程的状态来证明这次释放成功。
        }
        if(core.tick(now))insert(QStringLiteral("cancelToken"),int(core.token));
        if(waitingRecovery && now-recoveryAt>=10000)finishRecovery(false);
        if(!lastSent || now-lastSent>=FORMAL_HEARTBEAT_MS) {send(workerPid ? FORMAL_HEARTBEAT : FORMAL_HELLO);lastSent=now;}
        pump();publish();
        if(!lastReport || now-lastReport>=1000) {
            QSaveFile file(QStringLiteral("/tmp/hbl-flash-wifi-coexist/coexist-state.json"));
            QJsonObject state;state["monotonicMs"]=double(now);state["enabled"]=core.enabled;
            state["phase"]=int(core.phase);state["error"]=int(core.error);state["networkReady"]=monitor.ready();
            state["workerConnected"]=connected;state["radioReleased"]=released;state["token"]=int(core.token);
            if(file.open(QIODevice::WriteOnly)) {file.write(QJsonDocument(state).toJson(QJsonDocument::Compact));file.write("\n");file.commit();}
            lastReport=now;
        }
    }
    void receive() {
        for(unsigned n=0;n<32;++n) {
            FormalPacket packet={};sockaddr_un peer={};iovec body={&packet,sizeof(packet)};
            union {cmsghdr align;char bytes[CMSG_SPACE(sizeof(ucred))];} control={};
            msghdr msg={};msg.msg_name=&peer;msg.msg_namelen=sizeof(peer);msg.msg_iov=&body;msg.msg_iovlen=1;
            msg.msg_control=control.bytes;msg.msg_controllen=sizeof(control.bytes);
            const ssize_t bytes=recvmsg(fd,&msg,MSG_DONTWAIT);if(bytes<0)return;
            const ucred *credential=nullptr;bool duplicate=false;
            for(cmsghdr *c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c)) {
                if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_CREDENTIALS && c->cmsg_len==CMSG_LEN(sizeof(ucred))) {
                    if(credential)duplicate=true;credential=reinterpret_cast<const ucred *>(CMSG_DATA(c));
                }
            }
            const unsigned base=offsetof(sockaddr_un,sun_path);
            if((msg.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) || duplicate || !credential || credential->uid!=geteuid() || credential->pid<=0 ||
               peer.sun_family!=AF_UNIX || msg.msg_namelen<base+sizeof(HBL_FORMAL_WORKER_SOCKET) || msg.msg_namelen>sizeof(peer) ||
               memcmp(peer.sun_path,HBL_FORMAL_WORKER_SOCKET,sizeof(HBL_FORMAL_WORKER_SOCKET)) ||
               !formal_packet_valid(&packet,unsigned(bytes)) || packet.session!=session || packet.sequence>sequence ||
               packet.sequence<lastAccepted || (packet.kind!=FORMAL_STATUS && packet.kind!=FORMAL_FLUSH_ACK))continue;
            const uint64_t now=rf_monotonic_ms(),at=formal_packet_time(&packet);
            if(at>now || now-at>=FORMAL_DISCONNECT_MS || (workerPid && workerPid!=uint32_t(credential->pid)))continue;
            const bool first=!workerPid;workerPid=uint32_t(credential->pid);connected=true;lastReply=now;lastAccepted=packet.sequence;
            released=packet.values[FV_RELEASED];installReady=packet.values[FV_INSTALL_READY];
            if(first)options(false);
            if(waitingOpen && packet.sequence>=barrier) {
                if(packet.values[FV_MASTER] && packet.values[FV_READY] && !packet.values[FV_BUSY]) {waitingOpen=false;complete(true);}
                else if(packet.values[FV_ERROR]!=FORMAL_OK && packet.values[FV_ERROR]!=FORMAL_CANCELLED) {waitingOpen=false;complete(false);}
            }
            if(waitingClose && packet.sequence>=barrier && !packet.values[FV_MASTER] && !packet.values[FV_BUSY]) {
                if(released || packet.values[FV_RELEASE_FAILED]) {waitingClose=false;complete(released && !packet.values[FV_RELEASE_FAILED]);}
            }
            if(waitingPower && packet.kind==FORMAL_FLUSH_ACK && packet.sequence>=flushSequence && packet.values[FV_ACK_TOKEN]==core.token) {
                waitingPower=false;complete(packet.values[FV_RESULT]==FORMAL_OK && packet.values[FV_READY]);
            }
            publish();
        }
    }
    void goodbye() {
        if(leaving)return;leaving=true;heartbeat.stop();
        if(core.token)shotMessage(FORMAL_CANCEL);options(false);send(FORMAL_BYE);
    }
};
Runtime *runtime=nullptr;
void report(const char *message) {
    QFile file(QStringLiteral("/tmp/hbl-flash-wifi-coexist/coexist-runtime.status"));
    if(file.open(QIODevice::WriteOnly|QIODevice::Truncate)) {file.write(message);file.write("\n");}
}
}
extern "C" bool coexistRegister(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool coexistRegister(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Function=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original)return false;
    if(enabledByEnvironment() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay)
        overlay=QResource::registerResource(QStringLiteral("/tmp/hbl-flash-wifi-coexist/coexist-ui.rcc"));
    return original(version,tree,names,data);
}
extern "C" void coexistLoad(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void coexistLoad(QQmlApplicationEngine *engine,const QUrl &url) {
    using Function=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Function>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original)return;
    if(enabledByEnvironment() && overlay && !runtime) {
        runtime=new Runtime(engine);
        if(runtime->usable())engine->rootContext()->setContextProperty(QStringLiteral("hblCoexist"),runtime);
        else {delete runtime;runtime=nullptr;}
    }
    original(engine,url);
    if(enabledByEnvironment()) {
        if(!overlay || !runtime || engine->rootObjects().isEmpty())report("coexist-ui-unavailable");
        else {
            QQmlComponent gate(engine,QUrl(QStringLiteral("qrc:/CoexistExposureGate.qml")));
            report(gate.isReady() && !gate.isError() ? "coexist-ui-loaded-default-off" : "coexist-gate-unavailable");
        }
    }
}
