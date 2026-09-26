#include "ready_refresh.h"
#include "replay_runtime.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qdir.h>
#include <QtCore/qfilesystemwatcher.h>
#include <QtCore/qhash.h>
#include <QtCore/qjsondocument.h>
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

QByteArray revision(const QString &source)
{
    QJsonObject record;
    if (!X1D::loadRecord(source, &record) ||
        (source != record.value(QStringLiteral("rawPath")).toString() &&
         source != record.value(QStringLiteral("jpegPath")).toString())) return QByteArray();
    return X1D::sha256(QJsonDocument(record).toJson(QJsonDocument::Compact));
}

struct TrackedImage {
    QPointer<QObject> image;
    QUrl url;
    QString source;
    QByteArray observed;
};

class ReadyMonitor final : public QObject {
public:
    explicit ReadyMonitor(QQmlEngine *engine) : QObject(engine), engine(engine), watcher(this), timer(this) {
        connect(&watcher, &QFileSystemWatcher::directoryChanged, this,
                [this](const QString &) { check(); });
        /* inotify 目录删除、尚未创建或注册失败时，有限本地检查补足通知。
         * 只看最多 64 个当前源的 8 KiB 记录，不在 GUI 线程查询 Storage。 */
        timer.setInterval(1000);
        connect(&timer, &QTimer::timeout, this, [this]() { check(); });
        armWatch();
    }

    void track(QObject *image, const QUrl &url, const QString &source) {
        prune();
        for (int i = tracked.size() - 1; i >= 0; --i)
            if (tracked[i].image == image) tracked.removeAt(i);
        if (tracked.size() == 64) tracked.removeFirst();
        tracked.append(TrackedImage{QPointer<QObject>(image), url, source, revision(source)});
        if (!timer.isActive()) timer.start();
    }

private:
    bool current(const TrackedImage &entry) const {
        return entry.image && entry.image->thread() == thread() &&
               qmlEngine(entry.image.data()) == engine && entry.image->property("source").toUrl() == entry.url;
    }

    void prune() {
        for (int i = tracked.size() - 1; i >= 0; --i)
            if (!current(tracked[i])) tracked.removeAt(i);
        if (tracked.isEmpty()) timer.stop();
    }

    void armWatch() {
        const QStringList wanted = {QStringLiteral("/media"), QStringLiteral("/media/data"), X1D::recordDirectory()};
        const QStringList existing = watcher.directories();
        for (const QString &path : wanted)
            if (!existing.contains(path) && QDir(path).exists()) watcher.addPath(path);
    }

    void check() {
        try {
            armWatch();
            prune();
            /* 原 load 会再次进入 hook，并可触发 QML 删除/换源；不跨调用持有迭代器。 */
            const QList<TrackedImage> snapshot = tracked;
            for (const TrackedImage &entry : snapshot) {
                if (!current(entry)) continue;
                const QByteArray next = revision(entry.source);
                bool reload = false;
                for (TrackedImage &live : tracked) {
                    if (live.image == entry.image && live.url == entry.url) {
                        reload = !next.isEmpty() && next != live.observed;
                        live.observed = next;
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
    QFileSystemWatcher watcher;
    QTimer timer;
    QList<TrackedImage> tracked;
};

QHash<QQmlEngine *, ReadyMonitor *> monitors;
}

void X1D::trackPixmap(void *pixmap, QQmlEngine *engine, const QUrl &url, quintptr caller)
{
    if (caller != 0x4be613cc || !pixmap || !engine || !QCoreApplication::instance() ||
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
