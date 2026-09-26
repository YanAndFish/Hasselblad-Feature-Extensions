#include "rf_local_socket.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlpropertymap.h>
#include <dlfcn.h>
#include <cstdlib>
#include <cstring>

namespace {
bool requested() {
    const char *v=std::getenv("HBL_RF_ENABLE_PLUGIN");
    return v && !std::strcmp(v,"1");
}
class Runtime;
Runtime *runtime=nullptr;
bool overlay=false;
void report(const char *value) {
    QFile file(QStringLiteral("/tmp/hbl-wireless-flash/runtime.status"));
    if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        file.write(value); file.write("\n"); file.close();
    }
}
class Runtime : public QQmlPropertyMap {
public:
    explicit Runtime(QQmlApplicationEngine *engine) : QQmlPropertyMap(engine) {
        session=uint32_t(rf_monotonic_ms()) ^ (uint32_t(getpid())<<16);
        if (!session) session=1;
        insert(QStringLiteral("command"),QString());
        insert(QStringLiteral("enabled"),false); insert(QStringLiteral("source"),0);
        insert(QStringLiteral("progressThreshold"),0);
        insert(QStringLiteral("delayMs"),0); insert(QStringLiteral("powerIndex"),10);
        insert(QStringLiteral("radioBusy"),false); insert(QStringLiteral("radioReady"),false);
        insert(QStringLiteral("availableMask"),7);
        for (const char *key : {"manualClicks","fpgaSamples","fpgaSynced","fpgaSkipped","automaticQueued","sentRequests","radioFailures","cancelledRequests","busySkips"})
            insert(QString::fromLatin1(key),0);
        status(QStringLiteral("正在连接常驻接收程序"));
        fd=rf_local_bind(RF_UI_SOCKET);
        if (fd<0) { status(QStringLiteral("无法连接常驻程序")); return; }
        auto notifier=new QSocketNotifier(fd,QSocketNotifier::Read,this);
        QObject::connect(notifier,&QSocketNotifier::activated,this,[this](int) { receive(); });
        heartbeat.setInterval(500);
        QObject::connect(&heartbeat,&QTimer::timeout,this,[this]() {
            const uint64_t now=rf_monotonic_ms();
            if (connected && (now<lastReply || now-lastReply>2000)) {
                connected=false; on=false; revision=0; pendingKind=0;
                if (!++session) ++session;
                insert(QStringLiteral("enabled"),false); insert(QStringLiteral("radioReady"),false);
                status(QStringLiteral("常驻程序连接中断；自动引闪关闭"));
            }
            if (!connected) send(RF_UI_HELLO,0);
            else if (pendingKind==RF_UI_CONFIG || pendingKind==RF_UI_ARM) send(pendingKind,revision);
            else send(RF_UI_QUERY,revision);
        });
        heartbeat.start();
        QObject::connect(QCoreApplication::instance(),&QCoreApplication::aboutToQuit,this,[this]() { goodbye(); });
        QTimer::singleShot(0,this,[this]() { send(RF_UI_HELLO,0); });
    }
    ~Runtime() override {
        goodbye();
        if (fd>=0) { close(fd); unlink(RF_UI_SOCKET); }
        if (runtime==this) runtime=nullptr;
    }
    bool usable() const { return fd>=0; }
protected:
    QVariant updateValue(const QString &key,const QVariant &value) override {
        if (key!=QStringLiteral("command")) return this->value(key);
        const QString command=value.toString();
        unsigned kind=RF_UI_CONFIG;
        if (command==QStringLiteral("cancel")) { on=false; page=false; }
        else if (command==QStringLiteral("prepare")) page=true;
        else if (command==QStringLiteral("pageclosed")) page=false;
        else if (command==QStringLiteral("test")) kind=RF_UI_TEST;
        else if (command.startsWith(QStringLiteral("power "))) {
            bool valid=false; const uint next=command.mid(6).toUInt(&valid);
            if (!valid || next<10 || next>100) return QVariant();
            power=next; insert(QStringLiteral("powerIndex"),int(power));
        } else {
            const QStringList fields=command.split(QLatin1Char(' '));
            if (fields.size()!=5 || fields[0]!=QStringLiteral("configure")) return QVariant();
            bool a=false,b=false,c=false,d=false;
            const uint nextOn=fields[1].toUInt(&a),nextSource=fields[2].toUInt(&b),nextDelay=fields[3].toUInt(&c);
            const uint nextProgress=fields[4].toUInt(&d);
            if (!a || !b || !c || !d || nextOn>1 || nextSource>=3 || nextDelay>5000 || nextProgress>100) return QVariant();
            if (bool(nextOn)!=on) kind=RF_UI_ARM;
            on=nextOn; source=nextSource; delay=nextDelay; progress=nextProgress;
        }
        if (!connected) {
            on=false; status(QStringLiteral("常驻程序尚未连接")); return QVariant();
        }
        issue(kind); return QVariant();
    }
private:
    int fd=-1;
    uint32_t session=0,revision=0,pendingKind=0;
    uint64_t lastReply=0,issuedAt=0;
    uint32_t power=10,delay=0,source=0,progress=0;
    bool on=false,page=false,connected=false,leaving=false;
    QTimer heartbeat;
    void status(const QString &text) { insert(QStringLiteral("status"),text); }
    bool send(unsigned kind,uint32_t seq) {
        RfBridgePacket packet;
        rf_bridge_init(&packet,kind,session,seq,rf_monotonic_ms());
        packet.values[RV_ON]=on; packet.values[RV_DELAY]=delay;
        packet.values[RV_SOURCE]=source;
        packet.values[RV_PROGRESS]=progress;
        packet.values[RV_POWER]=power; packet.values[RV_PAGE]=page;
        return rf_local_send(fd,RF_WORKER_SOCKET,&packet);
    }
    void issue(unsigned kind) {
        if (revision==UINT32_MAX) { goodbye(); status(QStringLiteral("会话计数耗尽，请重新进入界面")); return; }
        ++revision; pendingKind=kind; issuedAt=rf_monotonic_ms();
        insert(QStringLiteral("radioReady"),false);
        insert(QStringLiteral("enabled"),on); insert(QStringLiteral("delayMs"),int(delay));
        insert(QStringLiteral("source"),int(source));
        insert(QStringLiteral("progressThreshold"),int(progress));
        status(QStringLiteral("正在应用设置"));
        if (!send(kind,revision)) status(QStringLiteral("请求尚未送达；单次试闪不会自动重试"));
    }
    void goodbye() {
        if (leaving) return;
        leaving=true; on=false; page=false;
        if (revision<UINT32_MAX) send(RF_UI_BYE,++revision);
    }
    void receive() {
        for (unsigned n=0;n<32;++n) {
            RfBridgePacket packet; char peer[108];
            const int result=rf_local_receive(fd,&packet,peer,sizeof(peer));
            if (!result) return;
            if (result<0 || std::strcmp(peer,RF_WORKER_SOCKET) || packet.kind!=RF_BRIDGE_STATUS ||
                packet.session!=session || packet.sequence>revision || !rf_bridge_settings_valid(&packet) ||
                packet.values[RV_BUSY]>1 || packet.values[RV_ARMED]>1 || packet.values[RV_EVENT_ALIVE]>1 ||
                !memchr(packet.text,0,sizeof(packet.text))) continue;
            const uint64_t now=rf_monotonic_ms(),at=rf_bridge_time(&packet);
            if (!at || at>now || now-at>2000) continue;
            lastReply=now;
            const bool first=!connected; connected=true;
            const char *keys[]={"manualClicks","fpgaSamples","fpgaSynced","fpgaSkipped","automaticQueued","sentRequests","radioFailures","cancelledRequests","busySkips"};
            for (unsigned i=0;i<9;++i) insert(QString::fromLatin1(keys[i]),int(qMin(packet.values[RV_CLICKS+i],uint32_t(INT32_MAX))));
            insert(QStringLiteral("radioBusy"),bool(packet.values[RV_BUSY]));
            if (packet.sequence==revision) {
                pendingKind=0; on=packet.values[RV_ON];
                source=packet.values[RV_SOURCE]; delay=packet.values[RV_DELAY];
                progress=packet.values[RV_PROGRESS];
                insert(QStringLiteral("progressThreshold"),int(progress));
                insert(QStringLiteral("source"),int(source));
                insert(QStringLiteral("delayMs"),int(delay));
                insert(QStringLiteral("enabled"),on);
                insert(QStringLiteral("radioReady"),bool(packet.values[RV_ARMED] && packet.values[RV_EVENT_ALIVE]));
                status(QString::fromUtf8(packet.text));
            } else if (pendingKind==RF_UI_TEST && now-issuedAt>1500) {
                pendingKind=0; on=packet.values[RV_ON];
                insert(QStringLiteral("enabled"),on);
                status(QStringLiteral("本次按键未获确认，不会补发"));
            }
            if (first && page) issue(RF_UI_CONFIG);
        }
    }
};
}

extern "C" bool hbl_register(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool hbl_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Register=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Register>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if (!original) return false;
    if (requested() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay)
        overlay=QResource::registerResource(QStringLiteral("/tmp/hbl-wireless-flash/ui.rcc"));
    return original(version,tree,names,data);
}
extern "C" void hbl_load(QQmlApplicationEngine *,const QUrl &)
    __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void hbl_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Load=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if (!original) return;
    if (requested() && !overlay) report("resource-overlay-unavailable");
    if (requested() && overlay && !runtime) {
        runtime=new Runtime(engine);
        if (runtime->usable()) engine->rootContext()->setContextProperty(QStringLiteral("hblNative"),runtime);
        else { delete runtime; runtime=nullptr; }
    }
    original(engine,url);
    if (requested() && overlay) {
        if (engine->rootObjects().isEmpty()) report("qml-root-failed");
        else if (!runtime) report("event-adapter-unavailable");
        else {
            QQmlComponent settings(engine,QUrl(QStringLiteral("qrc:/settings/SettingsGeneric.qml")));
            report(settings.isError() ? "qml-settings-failed" : "ui-loaded-worker-default-off");
        }
    }
}
