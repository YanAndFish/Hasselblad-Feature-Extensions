#include "replay_runtime.h"
#include <QtCore/qhash.h>
#include <QtCore/qcoreapplication.h>
#include <QtCore/qdatetime.h>
#include <QtCore/qmutex.h>
#include <QtCore/qobject.h>
#include <QtDBus/qdbusmessage.h>
#include <QtDBus/qdbuspendingcall.h>
#include <dlfcn.h>

namespace {
using ImageCall = QDBusPendingCallWatcher *(*)(QObject *, const QString &, int, int);
using WriteCall = QDBusPendingCallWatcher *(*)(QObject *, const QByteArray &, quint64, const QString &);
const char ImageSymbol[] = "_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile";
const char WriteSymbol[] = "_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString";
struct Capture {
    QString source;
    int resolution;
    QString generation;
    Capture() : resolution(0) {}
    Capture(const QString &path, int value, const QString &id) : source(path), resolution(value), generation(id) {}
};
QMutex captureMutex;
QHash<QObject *, Capture> captures;
quint64 generation=0;

QDBusPendingCallWatcher *failed(QObject *parent)
{
    auto *watcher = new QDBusPendingCallWatcher(QDBusPendingCall::fromError(
        QDBusError(QDBusError::Failed, QStringLiteral("X1D JPEG validation unavailable or failed"))), parent);
    /* 原 ConvertCall 忽略返回 watcher，由 Encoder 自行推进队列。
     * 本地拒绝不进入原 DBusProxy::onFinished，故在原线程安排延迟清理。 */
    watcher->deleteLater();
    return watcher;
}

void publish(QDBusPendingCallWatcher *watcher, const QJsonObject &pending)
{
    if (watcher->property("x1dCompleted").toBool()) return;
    watcher->setProperty("x1dCompleted", true);
    const QDBusMessage message = watcher->reply();
    const auto args = message.arguments();
    if (watcher->isError() || message.type() != QDBusMessage::ReplyMessage ||
        args.size() != 1 || args.first().type() != QVariant::String) return;
    const QString actual = args.first().toString();
    const QString raw=pending.value(QStringLiteral("rawPath")).toString();
    const QString wanted=X1D::pairedJpeg(raw);
    if (wanted.isEmpty() || actual.left(actual.size()-4)!=wanted.left(wanted.size()-4) ||
        !actual.endsWith(QLatin1String(".jpg"),Qt::CaseInsensitive)) return;
    QJsonObject latest;
    if (!X1D::loadRecord(raw,&latest) || !latest.value(QStringLiteral("pending")).toBool() ||
        latest.value(QStringLiteral("generation"))!=pending.value(QStringLiteral("generation"))) return;
    QJsonObject ready = pending;
    ready.insert(QStringLiteral("jpegPath"), actual);
    ready.insert(QStringLiteral("closed"), true);
    ready.insert(QStringLiteral("pending"), false);
    /* 各记录独立原子提交；记录写失败不改变已经写好的照片。 */
    X1D::saveRecord(actual, ready);
    X1D::saveRecord(ready.value(QStringLiteral("rawPath")).toString(), ready);
}
}

extern "C" QDBusPendingCallWatcher *x1d_image(QObject *, const QString &, int, int)
    __asm__("_ZN12StorageProxy5imageERK7QString16hblm_resolutions18hblm_color_profile");
extern "C" QDBusPendingCallWatcher *x1d_image(QObject *proxy, const QString &path, int resolution, int color)
{
    static const auto original = reinterpret_cast<ImageCall>(dlsym(RTLD_NEXT, ImageSymbol));
    if (!original) return failed(proxy);
    try {
        static const bool enabled = X1D::runtimeMatches("jpeg-daemon");
        /* 仅原 Encoder::processNextCall 的请求点，不把其他 Image 客户端当拍摄。 */
        if (enabled && reinterpret_cast<quintptr>(__builtin_return_address(0)) == 0x178c8) {
            QMutexLocker locker(&captureMutex);
            const QString id=QString::number(QCoreApplication::applicationPid())+QLatin1Char('-')+
                QString::number(QDateTime::currentMSecsSinceEpoch())+QLatin1Char('-')+QString::number(++generation);
            captures.insert(proxy, Capture{path,resolution,id});
            if (resolution==2 || resolution==0) {
                QJsonObject pending;
                pending.insert(QStringLiteral("version"),4);
                pending.insert(QStringLiteral("pending"),true);
                pending.insert(QStringLiteral("rawPath"),path);
                pending.insert(QStringLiteral("generation"),id);
                X1D::saveRecord(path,pending);
                const QString jpeg=X1D::pairedJpeg(path);
                if (!jpeg.isEmpty()) X1D::saveRecord(jpeg,pending);
            }
        }
    } catch (...) { /* 辅助关联失败时保持原编码调用。 */ }
    return original(proxy, path, resolution, color);
}

extern "C" QDBusPendingCallWatcher *x1d_write(QObject *, const QByteArray &, quint64, const QString &)
    __asm__("_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString");
extern "C" QDBusPendingCallWatcher *x1d_write(QObject *proxy, const QByteArray &input, quint64 offset, const QString &target)
{
    static const auto original = reinterpret_cast<WriteCall>(dlsym(RTLD_NEXT, WriteSymbol));
    if (!original) return failed(proxy);
    QJsonObject pending;
    bool validationRequired=false, structurallyValid=false;
    const quintptr caller=reinterpret_cast<quintptr>(__builtin_return_address(0));
    try {
        static const bool enabled=X1D::runtimeMatches("jpeg-daemon");
        if (enabled && caller==0x1e2e0 && !offset) {
            Capture capture;
            { QMutexLocker lock(&captureMutex); capture=captures.take(proxy); }
            validationRequired=capture.resolution==0 || capture.resolution==2;
            if (validationRequired) {
                XjInfo info;
                structurallyValid=!input.isEmpty() && input.size()<=X1D::MaximumJpegBytes &&
                    !xj_inspect(reinterpret_cast<const uint8_t *>(input.constData()),input.size(),&info) &&
                    info.eoi_end==uint32_t(input.size());
                // 原 jpeg-daemon 的编码失败修正仍是必须配套；这里不再重复熵解码。
                const QString paired=X1D::pairedJpeg(capture.source);
                if (structurallyValid && info.has_unique_id && !paired.isEmpty() &&
                    target.left(target.size()-4)==paired.left(paired.size()-4) &&
                    target.endsWith(QLatin1String(".jpg"),Qt::CaseInsensitive)) {
                    pending.insert(QStringLiteral("version"),4);
                    pending.insert(QStringLiteral("generation"),capture.generation);
                    pending.insert(QStringLiteral("rawPath"),capture.source);
                    pending.insert(QStringLiteral("uidHash"),QString::fromLatin1(X1D::sha256(QByteArray(reinterpret_cast<const char *>(info.unique_id),32))));
                    pending.insert(QStringLiteral("prefixHash"),QString::fromLatin1(X1D::sha256(input.left(info.header_bytes))));
                    pending.insert(QStringLiteral("prefixBytes"),int(info.header_bytes));
                    pending.insert(QStringLiteral("jpegHash"),QString::fromLatin1(X1D::sha256(input)));
                    pending.insert(QStringLiteral("bytes"),input.size());
                    pending.insert(QStringLiteral("orientation"),int(info.orientation));
                }
            }
        }
    } catch (...) { pending=QJsonObject(); }
    if (validationRequired && !structurallyValid) return failed(proxy);
    /* 严格只提交一次。之后的辅助监听异常不得重发原文件覆盖新成片。 */
    QDBusPendingCallWatcher *watcher = original(proxy, input, offset, target);
    if (watcher && !pending.isEmpty()) {
        try {
            if (watcher->isFinished()) publish(watcher, pending);
            else QObject::connect(watcher, &QDBusPendingCallWatcher::finished, watcher,
                                  [pending](QDBusPendingCallWatcher *done) {
                                      try { publish(done, pending); } catch (...) {}
                                  });
        } catch (...) {}
    }
    return watcher;
}
