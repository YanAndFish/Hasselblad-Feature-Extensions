// 只读 D-Bus 属性，禁止自动启动服务；不创建安装保持、不发送状态改变。
#include <QtCore/qcoreapplication.h>
#include <QtCore/qthread.h>
#include <QtDBus/qdbusconnection.h>
#include <QtDBus/qdbusconnectioninterface.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbusreply.h>
#include <QtDBus/qdbusextratypes.h>
#include <cstdio>
#include <cstring>
#include <unistd.h>
struct Snapshot { int system=-1,suc=-1,farm=-1,pwr=-1,power=-1;unsigned pid=0; };
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
static bool get(QDBusConnection &b,const char *service,const char *path,const char *iface,const char *key,int &value,unsigned *pid=nullptr) {
    auto owner=b.interface()->serviceOwner(QString::fromLatin1(service));
    if(!owner.isValid() || owner.value().isEmpty()) return false;
    auto call=QDBusMessage::createMethodCall(owner.value(),QString::fromLatin1(path),QStringLiteral("org.freedesktop.DBus.Properties"),QStringLiteral("Get"));
    call.setAutoStartService(false);call << QString::fromLatin1(iface) << QString::fromLatin1(key);
    if(!parse(b.call(call,QDBus::Block,1000),value)) return false;
    if(pid) { auto p=b.interface()->servicePid(owner.value());if(!p.isValid() || !p.value()) return false;*pid=p.value(); }
    auto after=b.interface()->serviceOwner(QString::fromLatin1(service));
    return after.isValid() && after.value()==owner.value();
}
static bool snapshot(QDBusConnection &b,Snapshot &s) {
    return b.isConnected() && b.interface() &&
        get(b,"com.hasselblad.systemmanager","/","com.hasselblad.systemmanager","system_state",s.system) &&
        get(b,"com.hasselblad.suc","/suc","com.hasselblad.linkstatus","status",s.suc) &&
        get(b,"com.hasselblad.farm","/farm","com.hasselblad.linkstatus","status",s.farm) &&
        get(b,"com.hasselblad.pwrctrl","/pwrctrl","com.hasselblad.linkstatus","status",s.pwr) &&
        get(b,"com.hasselblad.ui","/power","com.hasselblad.powerclient","state",s.power,&s.pid);
}
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(argc!=2) return 59;
    if(!std::strcmp(argv[1],"--self-test")) {
        Snapshot s;s.system=2;s.power=0;s.suc=s.farm=s.pwr=0;s.pid=1;
        if(!ready(s)) return 64;
        s.system=4;s.power=1;if(!ready(s)) return 64;
        s.farm=1;if(ready(s)) return 64;
        int v=-1;auto request=QDBusMessage::createMethodCall("a.b","/","a.b","c");
        if(!parse(request.createReply(QVariant::fromValue(QDBusVariant(2))),v) || v!=2 || parse(request.createReply(2),v)) return 64;
        puts("ui-health-self-test-pass");return 0;
    }
    if(std::strcmp(argv[1],"--require-ready")) return 59;
    // 总超时覆盖 D-Bus owner 查询；进程只读，超时由脚本判为不健康。
    alarm(8);
    QDBusConnection b=QDBusConnection::systemBus();unsigned previous=0;Snapshot s;
    if(!b.isConnected() || !b.interface()) return 65;
    b.interface()->setTimeout(1000);
    for(unsigned i=0;i<3;++i) {
        if(!snapshot(b,s) || !ready(s) || (previous && previous!=s.pid)) return 65;
        previous=s.pid;if(i<2) QThread::msleep(500);
    }
    printf("ui-health-ready pid=%u system=%d power=%d\n",s.pid,s.system,s.power);return 0;
}
