#include "formal_install_hold.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qthread.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusextratypes.h>

#ifndef HBL_CHECK_PACKAGE_ROOT
#define HBL_CHECK_PACKAGE_ROOT "/tmp/hbl-wireless-flash"
#endif
#ifndef HBL_CHECK_FILE_FIXTURE
#define HBL_CHECK_FILE_FIXTURE HBL_CHECK_PACKAGE_ROOT "/formal-hold.check"
#endif

struct Snapshot { int system=-1,suc=-1,farm=-1,pwr=-1,power=-1; unsigned pid=0; };
static bool active(const Snapshot &s) { return s.system==2 && s.suc==0 && s.farm==0 && s.pwr==0 && s.power==0 && s.pid; }
// 原厂 main.qml 初次进入 main 状态会 setState(Idle), setState(Active)。
// UI 首阶段可从全部连接已恢复的稳定 Standby 开始；FARM 阶段仍只允许 Active。
static bool uiStageReady(const Snapshot &s) { return active(s) || (s.system==4 && s.suc==0 && s.farm==0 && s.pwr==0 && s.power==1 && s.pid); }
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
    QDBusMessage reply=bus.call(call,QDBus::Block,1000);
    if(!parseReply(reply,value)) return false;
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
static bool held(const Snapshot &s,uint64_t minimumRemaining=0) {
    char b[128],extra; unsigned pid=0; unsigned long long deadline=0,pulse=0;
    if(holdReleased() || !holdRead(holdPulsePath,b,sizeof(b)) ||
       sscanf(b,"HPI1 %u %llu %llu %c",&pid,&deadline,&pulse,&extra)!=3 || deadline!=holdReadDeadline()) return false;
    const uint64_t now=holdNow();
    return holdFresh(now,deadline,pulse,pid,s.pid) && deadline-now>=minimumRemaining;
}
static bool check() {
    Snapshot s; s.system=2;s.suc=s.farm=s.pwr=s.power=0;s.pid=10;
    if(!active(s)) return false;
    s.system=4;s.power=1;
    if(active(s) || !uiStageReady(s)) return false;
    s.farm=3;if(uiStageReady(s)) return false;
    s.farm=0;s.system=6;if(uiStageReady(s)) return false;
    s.system=2;s.power=0;
    for(int *p:{&s.system,&s.suc,&s.farm,&s.pwr,&s.power}) { int old=*p;*p=-1;if(active(s)) return false;*p=old; }
    if(!holdFresh(10000,20000,9999,10,10) || holdFresh(10000,20000,7999,10,10) || holdFresh(10000,20000,10001,10,10) ||
       holdFresh(10000,10000,9999,10,10) || holdFresh(10000,20000,9999,9,10) || holdWindow(10000,1210001)) return false;
    int n=-1;
    QDBusMessage request=QDBusMessage::createMethodCall("a.b","/","a.b","c");
    if(!parseReply(request.createReply(QVariant::fromValue(QDBusVariant(2))),n) || n!=2) return false;
    if(parseReply(request.createReply(2),n) || parseReply(request.createReply(QVariant::fromValue(QDBusVariant(QStringLiteral("2")))),n)) return false;
    puts("formal-system-check-offline-pass"); return true;
}
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(argc!=2 && argc!=3) return 59;
    if(argc==2 && !strcmp(argv[1],"--check")) return check()?0:64;
    if(argc==2 && !strcmp(argv[1],"--check-files")) {
        char text[64];
        if(!holdDirectorySafe(HBL_CHECK_PACKAGE_ROOT) || !holdRead(HBL_CHECK_FILE_FIXTURE,text,sizeof(text)) || strcmp(text,"HBL hold file ABI check\n")) return 68;
        struct stat s;errno=0;int result=stat(HBL_CHECK_PACKAGE_ROOT,&s);int error=errno;
        printf("formal-hold-file-abi-pass native-stat=%d native-errno=%d\n",result,error);
        return 0;
    }
    bool begin=!strcmp(argv[1],"--begin-hold"), requireHeld=!strcmp(argv[1],"--require-held"), requireActive=!strcmp(argv[1],"--require-active"), snap=!strcmp(argv[1],"--snapshot"), stage=!strcmp(argv[1],"--require-ui-stage");
    uint64_t minimum=0;
    if(!strcmp(argv[1],"--require-held-min-ms")) {
        if(argc!=3 || !argv[2][0] || strspn(argv[2],"0123456789")!=strlen(argv[2]) || strlen(argv[2])>7) return 59;
        unsigned long long v=0; if(sscanf(argv[2],"%llu",&v)!=1 || !v || v>holdMaximumMs) return 59;
        minimum=v;requireHeld=true;
    } else if(argc!=2) return 59;
    if(!begin && !requireHeld && !requireActive && !snap && !stage) return 59;
    QDBusConnection bus=QDBusConnection::systemBus(); Snapshot s;
    unsigned prior=0;
    for(unsigned i=0;i<(snap?1u:3u);++i) {
        if(!snapshot(bus,s)) { puts("system-properties-unavailable"); return 65; }
        if(!snap && (!(begin || stage ? uiStageReady(s) : active(s)) || (prior && prior!=s.pid) || (requireHeld && !held(s,minimum)))) { puts("system-active-hold-not-ready"); return 66; }
        prior=s.pid;
        if(!snap && i<2) QThread::msleep(500);
    }
    if(begin) {
        if(geteuid()!=0 || !holdDirectorySafe(holdStateDirectory) || holdReleased()) return 67;
        int fd=open(holdDeadlinePath,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600); if(fd<0) return 67;
        char b[96]; int n=snprintf(b,sizeof(b),"HHD1 %llu\n",(unsigned long long)(holdNow()+holdMaximumMs));
        bool ok=write(fd,b,size_t(n))==n; if(close(fd)) ok=false; if(!ok) return 67;
    }
    printf("system=%d suc=%d farm=%d pwr=%d ui-power=%d hold=%d\n",s.system,s.suc,s.farm,s.pwr,s.power,held(s)?1:0);
    return 0;
}
