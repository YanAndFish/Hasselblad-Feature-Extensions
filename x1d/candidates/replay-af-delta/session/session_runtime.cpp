#include "session_policy.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qresource.h>
#include <QtCore/qtimer.h>
#include <QtCore/qset.h>
#include <QtGui/qguiapplication.h>
#include <QtGui/qopenglcontext.h>
#include <QtGui/qopenglfunctions.h>
#include <QtQuick/qquickwindow.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qqmlcontext.h>
#include <QtQml/qqmlpropertymap.h>
#include <atomic>
#include <dlfcn.h>

namespace {
std::atomic<bool> graphicsReady(false);
std::atomic<bool> overlayReady(false);
bool requested() { const char *v=getenv("X1D_REPLAY_SESSION"); return v && !strcmp(v,"1"); }
bool fileMatches(const char *path,const char *hash) {
    QFile f(QString::fromLatin1(path));
    return f.open(QIODevice::ReadOnly) && f.size()>0 && f.size()<16*1024*1024 &&
        QCryptographicHash::hash(f.readAll(),QCryptographicHash::Sha256).toHex()==hash;
}
bool fixedGui() {
    return fileMatches("/proc/self/exe",X1D_GUI_SHA256) &&
        fileMatches("/usr/lib/libQt5Core.so.5.5.1",X1D_QTCORE_SHA256) &&
        fileMatches("/usr/lib/libQt5Gui.so.5.5.1",X1D_QTGUI_SHA256) &&
        fileMatches("/usr/lib/libQt5Quick.so.5.5.1",X1D_QTQUICK_SHA256) &&
        fileMatches("/usr/lib/libQt5Qml.so.5.5.1",X1D_QTQML_SHA256);
}
struct Graphics { int max=0; bool bgra=false,npot=false; };
Graphics queryGraphics() {
    Graphics s;
    QOpenGLContext *c=QOpenGLContext::currentContext();
    if(!c || !c->isValid()) return s;
    QOpenGLFunctions *f=c->functions();
    if(!f) return s;
    f->glGetIntegerv(GL_MAX_TEXTURE_SIZE,&s.max);
    s.bgra=c->hasExtension(QByteArrayLiteral("GL_EXT_bgra")) ||
        c->hasExtension(QByteArrayLiteral("GL_EXT_texture_format_BGRA8888")) ||
        c->hasExtension(QByteArrayLiteral("GL_IMG_texture_format_BGRA8888"));
    s.npot=f->hasOpenGLFeature(QOpenGLFunctions::NPOTTextures);
    return s;
}
class Runtime : public QQmlPropertyMap {
public:
    explicit Runtime(QQmlApplicationEngine *engine):QQmlPropertyMap(engine) {
        deadline=deadlineValue();
        insert(QStringLiteral("installationHold"),holdWindow(nowMs(),deadline) && !released());
        insert(QStringLiteral("installPulse"),false);
        timer.setInterval(250);
        QObject::connect(&timer,&QTimer::timeout,this,[this]() {
            if(released() || !holdWindow(nowMs(),deadline)) { deadline=0; insert(QStringLiteral("installationHold"),false); }
            for(QWindow *w:QGuiApplication::allWindows()) {
                QQuickWindow *quick=qobject_cast<QQuickWindow *>(w);
                if(!quick) continue;
                if(windows.contains(quick)) { if(deadline) quick->update(); continue; }
                windows.insert(quick);
                QObject::connect(quick,&QObject::destroyed,this,[this,quick]() { windows.remove(quick); graphicsReady=false; });
                QObject::connect(quick,&QQuickWindow::sceneGraphInvalidated,this,[]() { graphicsReady=false; },Qt::DirectConnection);
                QObject::connect(quick,&QQuickWindow::beforeRendering,this,[]() {
                    const Graphics s=queryGraphics();
                    const bool ok=gpuAllowed(s.max,s.bgra,s.npot);
                    graphicsReady=ok;
                    char b[160]; snprintf(b,sizeof(b),"RPG1 %u %llu %d %d %d\n",unsigned(getpid()),
                        (unsigned long long)nowMs(),s.max,int(s.bgra),int(s.npot));
                    atomicText(gpuPath,b);
                },Qt::DirectConnection);
                quick->update();
            }
        });
        timer.start();
    }
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key!=QStringLiteral("installPulse")) return value(key);
        if(!released() && holdWindow(nowMs(),deadline)) {
            if(!writePulse(unsigned(getpid()),deadline,input.type()==QVariant::Bool && input.toBool() ? nowMs() : 0)) {
                deadline=0; insert(QStringLiteral("installationHold"),false);
            }
        }
        return false;
    }
private:
    uint64_t deadline=0;
    QTimer timer;
    QSet<QQuickWindow *> windows;
};
Runtime *runtime=nullptr;
bool overlay=false;
}

// Provider 的工作线程只读原子状态；纹理创建时重新检查该渲染上下文。
extern "C" bool x1d_replay_session_admit(int upload) {
    if(!requested() || !overlayReady.load() || !graphicsReady.load()) return false;
    if(upload) { const Graphics s=queryGraphics(); return gpuAllowed(s.max,s.bgra,s.npot); }
    return true;
}
// 仅重定向当前已安装 AF 的固定文件；唯一合成 RCC 在新目录，不覆盖 AF 文件。
extern "C" bool replay_register(const QString &,const QString &)
    __asm__("_ZN9QResource16registerResourceERK7QStringS2_");
extern "C" bool replay_register(const QString &file,const QString &root) {
    using Register=bool(*)(const QString &,const QString &);
    static auto original=reinterpret_cast<Register>(dlsym(RTLD_NEXT,"_ZN9QResource16registerResourceERK7QStringS2_"));
    if(!original) return false;
    if(!requested() || file!=QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc")) return original(file,root);
    const char *v=getenv("HBL_AF_UI_R4_ENABLE");
    if(!root.isEmpty() || !v || strcmp(v,"0") || !privateDirectory(sessionRoot) ||
       !privateDirectory(sessionState) || !fixedGui() ||
       !fileMatches("/tmp/hbl-x1d-combined/libhbl-af-only.so",X1D_AF_HOST_SHA256) ||
       !fileMatches("/tmp/hbl-x1d-combined/af/libhbl-af-ui.so",X1D_AF_UI_SHA256) ||
       !fileMatches("/tmp/hbl-x1d-combined/af-only-ui.rcc",X1D_AF_RCC_SHA256) ||
       !fileMatches("/tmp/hbl-x1d-rpa/replay-ui.rcc",X1D_SESSION_RCC_SHA256)) return false;
    if(overlay) return true;
    overlay=original(QStringLiteral("/tmp/hbl-x1d-rpa/replay-ui.rcc"),root);
    return overlay;
}
extern "C" void replay_load(QQmlApplicationEngine *,const QUrl &)
    __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void replay_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Load=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) return;
    if(requested() && overlay && !runtime) {
        runtime=new Runtime(engine);
        engine->rootContext()->setContextProperty(QStringLiteral("x1dReplaySession"),runtime);
    }
    original(engine,url);
    if(requested()) {
        bool ok=overlay && runtime && !engine->rootObjects().isEmpty();
        overlayReady=ok;
        char b[100]; snprintf(b,sizeof(b),"RPU1 %u %d\n",unsigned(getpid()),int(ok));
        atomicText("/tmp/hbl-x1d-rpa/state/ui",b);
    }
}
