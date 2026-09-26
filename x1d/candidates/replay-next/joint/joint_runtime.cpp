// 组合专用：唯一 RCC 由协调方注册；这里仅验证最终 main.qml 身份并注入本模块上下文。
#include "joint_policy.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qcryptographichash.h>
#include <QtCore/qfile.h>
#include <QtCore/qpointer.h>
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
        insert(QStringLiteral("resourceReady"),false);
        timer.setInterval(250);
        QObject::connect(&timer,&QTimer::timeout,this,[this]() {
            for(QWindow *w:QGuiApplication::allWindows()) {
                QQuickWindow *quick=qobject_cast<QQuickWindow *>(w);
                if(!quick) continue;
                if(windows.contains(quick)) { if(jointWindowActive()) quick->update(); continue; }
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
        if(key==QStringLiteral("resourceReady") && input.type()==QVariant::Bool && input.toBool()) return true;
        return value(key);
    }
private:
    QTimer timer;
    QSet<QQuickWindow *> windows;
};
QPointer<Runtime> runtime;
QPointer<QQmlApplicationEngine> ownedEngine;
}

// Provider 的工作线程只读原子状态；纹理创建时重新检查该渲染上下文。
extern "C" bool x1d_replay_session_admit(int upload) {
    if(!requested() || !overlayReady.load() || !graphicsReady.load()) return false;
    if(upload) { const Graphics s=queryGraphics(); return gpuAllowed(s.max,s.bgra,s.npot); }
    return true;
}
extern "C" void replay_load(QQmlApplicationEngine *,const QUrl &)
    __asm__("_ZN21QQmlApplicationEngine4loadERK4QUrl");
extern "C" void replay_load(QQmlApplicationEngine *engine,const QUrl &url) {
    using Load=void(*)(QQmlApplicationEngine *,const QUrl &);
    static auto original=reinterpret_cast<Load>(dlsym(RTLD_NEXT,"_ZN21QQmlApplicationEngine4loadERK4QUrl"));
    if(!original) return;
    if(!requested() || url.scheme()!=QStringLiteral("qrc") || url.path()!=QStringLiteral("/main.qml") ||
       !url.authority().isEmpty() || url.hasQuery() || url.hasFragment() || (ownedEngine && ownedEngine!=engine)) {
        original(engine,url);return;
    }
    if(requested() && !runtime && privateDirectory(sessionRoot) && privateDirectory(sessionState) && fixedGui() &&
       fileMatches(":/main.qml",X1D_JOINT_MAIN_SHA256)) {
        runtime=new Runtime(engine);
        ownedEngine=engine;
        QObject::connect(engine,&QObject::destroyed,[]() { overlayReady=false;graphicsReady=false; });
        engine->rootContext()->setContextProperty(QStringLiteral("x1dReplaySession"),runtime);
    }
    original(engine,url);
    if(requested()) {
        bool ok=runtime && runtime->value(QStringLiteral("resourceReady")).toBool() && !engine->rootObjects().isEmpty();
        overlayReady=ok;
        char b[100]; snprintf(b,sizeof(b),"RPU1 %u %d\n",unsigned(getpid()),int(ok));
        atomicText("/tmp/hbl-x1d-combined/replay-state/ui",b);
    }
}
