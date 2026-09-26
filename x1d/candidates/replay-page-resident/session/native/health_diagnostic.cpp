// 下一版只读健康诊断候选；不属于已冻结 8d960d... 包。
#include <QtCore/qcoreapplication.h>
#include <QtCore/qthread.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusextratypes.h>
#include <cstdio>
#include <cstring>
#include <signal.h>
#include <unistd.h>
struct Snapshot { int system=-1,suc=-1,farm=-1,pwr=-1,power=-1;unsigned pid=0; };
static void timed_out(int) {
    static const char text[]="replay-health-diagnostic-failed reason=timeout\n";
    write(2,text,sizeof(text)-1);_exit(65);
}
static bool ready(const Snapshot &s) {
    return s.suc==0 && s.farm==0 && s.pwr==0 && s.pid &&
        ((s.system==2 && s.power==0) || (s.system==4 && s.power==1));
}
static bool parse(const QDBusMessage &r,int &value) {
    if(r.type()!=QDBusMessage::ReplyMessage || r.arguments().size()!=1 || r.arguments().at(0).userType()!=qMetaTypeId<QDBusVariant>()) return false;
    QVariant v=qvariant_cast<QDBusVariant>(r.arguments().at(0)).variant();
    if(v.type()!=QVariant::Int) return false;
    value=v.toInt();return true;
}
static bool get(QDBusConnection &b,const char *service,const char *path,const char *iface,const char *key,
                const char *label,unsigned sample,int &value,unsigned *pid=nullptr) {
    auto owner=b.interface()->serviceOwner(QString::fromLatin1(service));
    if(!owner.isValid() || owner.value().isEmpty()) {
        std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u field=%s reason=owner\n",sample,label);return false;
    }
    auto call=QDBusMessage::createMethodCall(owner.value(),QString::fromLatin1(path),QStringLiteral("org.freedesktop.DBus.Properties"),QStringLiteral("Get"));
    call.setAutoStartService(false);call << QString::fromLatin1(iface) << QString::fromLatin1(key);
    if(!parse(b.call(call,QDBus::Block,1000),value)) {
        std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u field=%s reason=reply\n",sample,label);return false;
    }
    if(pid) {
        auto p=b.interface()->servicePid(owner.value());
        if(!p.isValid() || !p.value()) {
            std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u field=%s reason=pid\n",sample,label);return false;
        }
        *pid=p.value();
    }
    auto after=b.interface()->serviceOwner(QString::fromLatin1(service));
    if(!after.isValid() || after.value()!=owner.value()) {
        std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u field=%s reason=owner-changed\n",sample,label);return false;
    }
    return true;
}
static bool snapshot(QDBusConnection &b,Snapshot &s,unsigned sample) {
    return b.isConnected() && b.interface() &&
        get(b,"com.hasselblad.systemmanager","/","com.hasselblad.systemmanager","system_state","system_state",sample,s.system) &&
        get(b,"com.hasselblad.suc","/suc","com.hasselblad.linkstatus","status","suc.status",sample,s.suc) &&
        get(b,"com.hasselblad.farm","/farm","com.hasselblad.linkstatus","status","farm.status",sample,s.farm) &&
        get(b,"com.hasselblad.pwrctrl","/pwrctrl","com.hasselblad.linkstatus","status","pwrctrl.status",sample,s.pwr) &&
        get(b,"com.hasselblad.ui","/power","com.hasselblad.powerclient","state","ui.power",sample,s.power,&s.pid);
}
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(argc!=2 || std::strcmp(argv[1],"--require-ready")) return 59;
    signal(SIGALRM,timed_out);alarm(8);
    QDBusConnection b=QDBusConnection::systemBus();
    if(!b.isConnected() || !b.interface()) {
        std::fprintf(stderr,"replay-health-diagnostic-failed reason=system-bus\n");return 65;
    }
    b.interface()->setTimeout(1000);unsigned previous=0;Snapshot last;
    for(unsigned sample=1;sample<=3;++sample) {
        Snapshot s;
        if(!snapshot(b,s,sample)) return 65;
        if(!ready(s)) {
            std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u reason=not-ready system=%d suc=%d farm=%d pwr=%d power=%d pid=%u\n",
                sample,s.system,s.suc,s.farm,s.pwr,s.power,s.pid);return 65;
        }
        if(previous && previous!=s.pid) {
            std::fprintf(stderr,"replay-health-diagnostic-failed sample=%u reason=ui-pid-changed previous=%u pid=%u\n",sample,previous,s.pid);return 65;
        }
        previous=s.pid;last=s;if(sample<3) QThread::msleep(500);
    }
    std::printf("replay-health-ready pid=%u system=%d power=%d\n",previous,last.system,last.power);
    return 0;
}
