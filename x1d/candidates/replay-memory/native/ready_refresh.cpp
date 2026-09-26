#include "ready_refresh.h"
#include "replay_runtime.h"
#include "replay_retry.h"
#include "replay_catalog.h"
#include <QtQuick/qquickitem.h>
#include <QtCore/qcoreapplication.h>
#include <QtCore/qhash.h>
#include <QtCore/qpointer.h>
#include <QtCore/qthread.h>
#include <QtCore/qtimer.h>
#include <QtQml/qqml.h>
#include <QtQml/qqmlengine.h>
#include <dlfcn.h>
#include <memory>

namespace {
QString sourcePath(const QUrl &url)
{
    if (url.scheme() != QLatin1String("image") || url.host() != QLatin1String("imagestore")) return QString();
    const QString id = url.path().mid(1);
    const int skip = id.startsWith(QLatin1String("preview")) ? 7 :
                     id.startsWith(QLatin1String("fullsize")) ? 8 :
                     id.startsWith(QLatin1String("thumb")) ? 5 : 0;
    const QString path = id.mid(skip);
    return skip && X1D::storagePathValid(path) ? path : QString();
}

struct TrackedImage {
    QPointer<QObject> image;
    QUrl url;
    QString source;
    unsigned readRetries;
    unsigned retries;
};

class ReadyMonitor final : public QObject {
public:
    explicit ReadyMonitor(QQmlEngine *engine) : QObject(engine), engine(engine), timer(this) {
        timer.setInterval(100);
        connect(&timer, &QTimer::timeout, this, [this]() { check(++ticks%10==0); });
    }

    void track(QObject *image, const QUrl &url, const QString &source) {
        prune();
        unsigned attempts=0, reads=0;
        for (int i = tracked.size() - 1; i >= 0; --i)
            if (tracked[i].image == image) {
                if (tracked[i].url==url) { attempts=tracked[i].retries; reads=tracked[i].readRetries; }
                tracked.removeAt(i);
            }
        if (tracked.size() == 64) tracked.removeFirst();
        tracked.append(TrackedImage{QPointer<QObject>(image), url, source, reads,attempts});
        if (!timer.isActive()) timer.start();
    }

private:
    bool current(const TrackedImage &entry) const {
        return entry.image && entry.image->thread() == thread() &&
               qmlEngine(entry.image.data()) == engine && entry.image->property("source").toUrl() == entry.url;
    }

    void prune() {
        for (int i = tracked.size() - 1; i >= 0; --i)
            if (!current(tracked[i])) {
                if (tracked[i].url.path().startsWith(QLatin1String("/fullsize")) &&
                    X1D::currentFullSource(tracked[i].source)) X1D::selectFullSource(QString());
                tracked.removeAt(i);
            }
        if (tracked.isEmpty()) timer.stop();
    }

    void check(bool readTick=true) {
        try {
            prune();
            /* 原 load 会再次进入 hook，并可触发 QML 删除/换源；不跨调用持有迭代器。 */
            const QList<TrackedImage> snapshot = tracked;
            for (const TrackedImage &entry : snapshot) {
                if (!current(entry)) continue;
                bool reload = false;
                auto *item=static_cast<QQuickItem *>(entry.image.data());
                const bool waitingFull=entry.url.path().startsWith(QLatin1String("/fullsize")) &&
                    entry.retries<4 && item->parentItem() && item->parentItem()->isVisible() &&
                    X1D::consumeFullRetry(entry.source);
                for (TrackedImage &live : tracked) {
                    if (live.image == entry.image && live.url == entry.url) {
                        // Qt 5.5.1 Image.Error == 3。只重试可见失败图；Loading/Ready 不读卡。
                        // 每张图同一 source 最多四次、最短一秒；没有完成记录、目录轮询或写入钩子。
                        if (readTick && live.readRetries<4 && item->isVisible() &&
                            item->property("status").toInt()==3) {
                            reload=true; ++live.readRetries;
                        }
                        if (waitingFull) { reload=true; ++live.retries; }
                        break;
                    }
                }
                if (!reload || !current(entry)) continue;
                using LoadImage = void (*)(QObject *);
                static const auto load = reinterpret_cast<LoadImage>(dlsym(RTLD_NEXT, "_ZN15QQuickImageBase4loadEv"));
                /* 原 load 先 clear(this) 断开旧请求，再启动新的 provider 请求。
                 * 保持 source 属性和它的 QML binding；worker 仍重新验证源身份。 */
                if (load) load(entry.image.data());
            }
        } catch (...) { /* 下次通知/有限计时检查可重试，不向 GUI 事件循环抛异常。 */ }
    }

    QQmlEngine *engine;
    QTimer timer;
    QList<TrackedImage> tracked;
    unsigned ticks=0;
};

QHash<QQmlEngine *, ReadyMonitor *> monitors;
}

void X1D::trackPixmap(void *pixmap, QQmlEngine *engine, const QUrl &url, quintptr caller)
{
    /* 固定 5.5.1 load 的返回点相对入口为 +0x1a8；跟随真实库装载偏移。 */
    static const quintptr loadEntry = reinterpret_cast<quintptr>(dlsym(RTLD_NEXT, "_ZN15QQuickImageBase4loadEv"));
    if (!loadEntry || caller != loadEntry + 0x1a8 || !pixmap || !engine || !QCoreApplication::instance() ||
        QThread::currentThread() != engine->thread() ||
        engine->thread() != QCoreApplication::instance()->thread()) return;
    const QString source = sourcePath(url);
    if (source.isEmpty()) return;
    /* 固定原 Qt：load 中 r7 = d + 0xcc；QObjectData::q_ptr 位于 d + 4。
     * 不是按可变路径扫描对象。外围必须已通过全部运行库哈希检查。 */
    auto *privateData = static_cast<unsigned char *>(pixmap) - 0xcc;
    QObject *image = *reinterpret_cast<QObject **>(privateData + 4);
    if (!image || reinterpret_cast<void **>(image)[1] != privateData ||
        !image->inherits("QQuickImage") || image->thread() != engine->thread() ||
        qmlEngine(image) != engine || image->property("source").toUrl() != url) return;
    if (url.path().startsWith(QLatin1String("/fullsize"))) X1D::selectFullSource(source);
    X1D::updateCatalog(engine);
    ReadyMonitor *monitor = monitors.value(engine, nullptr);
    if (!monitor) {
        std::unique_ptr<ReadyMonitor> created(new ReadyMonitor(engine));
        monitor = created.get();
        QObject::connect(engine, &QObject::destroyed, engine, [engine]() { monitors.remove(engine); });
        monitors.insert(engine, monitor);
        created.release();
    }
    monitor->track(image, url, source);
}
