#include "session_policy.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qthread.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusextratypes.h>

struct Snapshot { int system=-1,suc=-1,farm=-1,pwr=-1,power=-1; unsigned pid=0; };
static bool active(const Snapshot &s) { return s.system==2 && s.suc==0 && s.farm==0 && s.pwr==0 && s.power==0 && s.pid; }
static bool parseReply(const QDBusMessage &r,int &value) {
    if(r.type()!=QDBusMessage::ReplyMessage || r.arguments().size()!=1 || r.arguments().at(0).userType()!=qMetaTypeId<QDBusVariant>()) return false;
    QVariant v=qvariant_cast<QDBusVariant>(r.arguments().at(0)).variant();
    if(v.type()!=QVariant::Int) return false;
    value=v.toInt(); return true;
}
static bool property(QDBusConnection &bus,const char *service,const char *path,const char *iface,const char *name,int &value,unsigned *pid=nullptr) {
    auto owner=bus.interface()->serviceOwner(QString::fromLatin1(service));
    if(!owner.isValid() || owner.value().isEmpty()) return false;
    QDBusMessage call=QDBusMessage::createMethodCall(owner.value(),QString::fromLatin1(path),QStringLiteral("org.freedesktop.DBus.Properties"),QStringLiteral("Get"));
    call.setAutoStartService(false); call << QString::fromLatin1(iface) << QString::fromLatin1(name);
    if(!parseReply(bus.call(call,QDBus::Block,1000),value)) return false;
    if(pid) { auto p=bus.interface()->servicePid(owner.value()); if(!p.isValid() || !p.value()) return false; *pid=p.value(); }
    auto after=bus.interface()->serviceOwner(QString::fromLatin1(service));
    return after.isValid() && after.value()==owner.value();
}
static bool snapshot(QDBusConnection &b,Snapshot &s) {
    return b.isConnected() && b.interface() &&
        property(b,"com.hasselblad.systemmanager","/","com.hasselblad.systemmanager","system_state",s.system) &&
        property(b,"com.hasselblad.suc","/suc","com.hasselblad.linkstatus","status",s.suc) &&
        property(b,"com.hasselblad.farm","/farm","com.hasselblad.linkstatus","status",s.farm) &&
        property(b,"com.hasselblad.pwrctrl","/pwrctrl","com.hasselblad.linkstatus","status",s.pwr) &&
        property(b,"com.hasselblad.ui","/power","com.hasselblad.powerclient","state",s.power,&s.pid);
}
static bool held(const Snapshot &s) {
    char b[160],extra; unsigned pid=0; unsigned long long deadline=0,pulse=0;
    return !released() && privateRead(pulsePath,b,sizeof(b)) &&
        sscanf(b,"RPP1 %u %llu %llu %c",&pid,&deadline,&pulse,&extra)==3 &&
        deadline==deadlineValue() && fresh(nowMs(),deadline,pulse,pid,s.pid);
}
static bool gpuReady(const Snapshot &s) {
    char b[160],extra; unsigned pid=0; unsigned long long pulse=0; int max=0,bgra=0,npot=0;
    uint64_t now=nowMs();
    return privateRead(gpuPath,b,sizeof(b)) && sscanf(b,"RPG1 %u %llu %d %d %d %c",&pid,&pulse,&max,&bgra,&npot,&extra)==5 &&
        pid==s.pid && pulse && now>=pulse && now-pulse<=2000 && bgra==1 && npot==1 && gpuAllowed(max,true,true);
}
static bool selfCheck() {
    Snapshot s; s.system=2;s.suc=s.farm=s.pwr=s.power=0;s.pid=1;
    if(!active(s)) return false;
    for(int *p:{&s.system,&s.suc,&s.farm,&s.pwr,&s.power}) { int old=*p;*p=-1;if(active(s)) return false;*p=old; }
    if(!fresh(10000,20000,9999,10,10) || fresh(10000,20000,7999,10,10) || fresh(10000,20000,10001,10,10) ||
       fresh(10000,10000,9999,10,10) || fresh(10000,20000,9999,9,10) || holdWindow(10000,1210001)) return false;
    if(!gpuAllowed(8192,true,true) || gpuAllowed(4096,true,true) || gpuAllowed(8192,false,true) || gpuAllowed(8192,true,false)) return false;
    int n=-1; QDBusMessage request=QDBusMessage::createMethodCall("a.b","/","a.b","c");
    if(!parseReply(request.createReply(QVariant::fromValue(QDBusVariant(2))),n) || n!=2 || parseReply(request.createReply(2),n)) return false;
    if(parseReply(request.createReply(QVariant::fromValue(QDBusVariant(QStringLiteral("2")))),n)) return false;
    puts("replay-check-selftest-pass"); return true;
}
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(argc==5 && !strcmp(argv[1],"--owners")) {
        const char *services[]={"com.hasselblad.config","com.hasselblad.jpeg","com.hasselblad.storage"};
        QDBusConnection bus=QDBusConnection::systemBus();
        if(!bus.isConnected() || !bus.interface()) return 65;
        for(int i=0;i<3;++i) {
            char *end=nullptr; unsigned long expected=strtoul(argv[i+2],&end,10);
            if(!expected || expected>2147483647 || !end || *end) return 59;
            auto owner=bus.interface()->serviceOwner(QString::fromLatin1(services[i]));
            if(!owner.isValid() || owner.value().isEmpty()) return 65;
            auto pid=bus.interface()->servicePid(owner.value());
            auto after=bus.interface()->serviceOwner(QString::fromLatin1(services[i]));
            if(!pid.isValid() || pid.value()!=expected || !after.isValid() || owner.value()!=after.value()) return 66;
        }
        puts("replay-service-owners-match"); return 0;
    }
    if(argc!=2) return 59;
    if(!strcmp(argv[1],"--selftest")) return selfCheck()?0:64;
    bool begin=!strcmp(argv[1],"--begin"), hold=!strcmp(argv[1],"--hold"), gpu=!strcmp(argv[1],"--gpu"), normal=!strcmp(argv[1],"--active");
    if(!begin && !hold && !gpu && !normal) return 59;
    if(geteuid()!=0 || !privateDirectory(sessionRoot) || (!normal && !privateDirectory(sessionState))) return 60;
    QDBusConnection bus=QDBusConnection::systemBus(); Snapshot s;
    unsigned prior=0;
    for(unsigned i=0;i<3;++i) {
        if(!snapshot(bus,s)) { puts("replay-system-properties-unavailable"); return 65; }
        if(!active(s) || (prior && prior!=s.pid) || ((hold||gpu) && !held(s)) || (gpu && !gpuReady(s))) {
            puts("replay-system-hold-or-gpu-not-ready"); return 66;
        }
        prior=s.pid; if(i<2) QThread::msleep(500);
    }
    if(begin) {
        if(released()) return 67;
        int fd=open(deadlinePath,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600); if(fd<0) return 67;
        char b[96]; int n=snprintf(b,sizeof(b),"RPD1 %llu\n",(unsigned long long)(nowMs()+maximumHoldMs));
        bool ok=write(fd,b,size_t(n))==n; if(close(fd)) ok=false; if(!ok) return 67;
    }
    printf("replay-system-active hold=%d gpu=%d\n",held(s)?1:0,gpuReady(s)?1:0);
    return 0;
}
