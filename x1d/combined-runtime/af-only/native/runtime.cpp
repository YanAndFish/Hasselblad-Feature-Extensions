// AF 独立资源注册和一次性安装保持；不包含引闪协议、worker、曝光拦截或回放。
#include "../../native/install_window.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcomponent.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlerror.h>
#include <QtQml/qqmlpropertymap.h>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <dlfcn.h>

namespace {
bool requested() { const char *value=std::getenv("HBL_AF_ONLY_ENABLE");return value && !std::strcmp(value,"1"); }
bool overlay=false;
void report(const char *text) {
    QFile file(QStringLiteral("/tmp/hbl-x1d-combined/ui.status"));
    if(file.open(QIODevice::WriteOnly|QIODevice::Truncate)) { file.write(text);file.write("\n"); }
}
class Hold : public QQmlPropertyMap {
public:
    explicit Hold(QQmlApplicationEngine *engine):QQmlPropertyMap(engine) {
        const char *enabled=std::getenv("HBL_AF_ONLY_HOLD");
        deadline=enabled && !std::strcmp(enabled,"1") ? holdReadDeadline() : 0;
        insert(QStringLiteral("installationHold"),holdWindow(holdNow(),deadline) && !holdReleased());
        insert(QStringLiteral("installPulse"),false);
        timer.setInterval(250);
        QObject::connect(&timer,&QTimer::timeout,this,[this]() { update(); });
        timer.start();
    }
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key!=QStringLiteral("installPulse")) return value(key);
        update();
        if(value(QStringLiteral("installationHold")).toBool() &&
           !holdAtomicPulse(unsigned(getpid()),deadline,input.type()==QVariant::Bool && input.toBool() ? holdNow() : 0)) {
            deadline=0;insert(QStringLiteral("installationHold"),false);
        }
        return false;
    }
private:
    uint64_t deadline=0;
    QTimer timer;
    void update() {
        if(!holdWindow(holdNow(),deadline) || holdReleased()) {
            deadline=0;insert(QStringLiteral("installationHold"),false);timer.stop();
        }
    }
};
Hold *runtime=nullptr;
}

extern "C" bool af_only_register(int,const unsigned char *,const unsigned char *,const unsigned char *)
    __asm__("_Z21qRegisterResourceDataiPKhS0_S0_");
extern "C" bool af_only_register(int version,const unsigned char *tree,const unsigned char *names,const unsigned char *data) {
    using Register=bool(*)(int,const unsigned char *,const unsigned char *,const unsigned char *);
    static auto original=reinterpret_cast<Register>(dlsym(RTLD_NEXT,"_Z21qRegisterResourceDataiPKhS0_S0_"));
    if(!original) return false;
    if(requested() && version==1 && reinterpret_cast<quintptr>(tree)==0x1ec7f0 && !overlay)
        overlay=QResource::registerResource(QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc"));
    return original(version,tree,names,data);
}
extern "C" void af_only_load(QQmlApplicationEngine *,const QUrl &) __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void af_only_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Load=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) return;
    if(requested() && overlay && !runtime) {
        runtime=new Hold(engine);
        engine->rootContext()->setContextProperty(QStringLiteral("hblAfInstall"),runtime);
    }
    original(engine,url);
    if(!requested()) return;
    if(!overlay || !runtime) { report("af-only-resource-unavailable");return; }
    if(engine->rootObjects().isEmpty()) { report("af-only-root-failed");return; }
    for(const char *path:{"qrc:/af-settings/SettingsPage.qml","qrc:/af-settings/AfSettingsHost.qml","qrc:/settings/SettingsGeneric.qml","qrc:/af-settings/AfQuickEntry.qml","qrc:/controlscreen/ControlScreen.qml"}) {
        QQmlComponent component(engine,QUrl(QString::fromLatin1(path)));
        if(component.isError() || !component.isReady()) {
            std::fprintf(stderr,"AF component failed: %s\n",path);
            for(const QQmlError &error:component.errors()) std::fprintf(stderr,"%s\n",error.toString().toUtf8().constData());
            report("af-only-component-failed");return;
        }
    }
    report("af-only-ui-ready");
}
