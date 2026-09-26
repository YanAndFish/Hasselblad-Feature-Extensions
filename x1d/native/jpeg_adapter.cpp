#include "replay_runtime.h"
#include <QtCore/qhash.h>
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
struct Capture { QString source; int resolution; };
QMutex captureMutex;
QHash<QObject *, Capture> captures;

QDBusPendingCallWatcher *failed(QObject *parent)
{
    return new QDBusPendingCallWatcher(QDBusPendingCall::fromError(
        QDBusError(QDBusError::Failed, QStringLiteral("X1D JPEG adapter unavailable"))), parent);
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
    if (!X1D::storagePathValid(actual) || !actual.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive)) return;
    QJsonObject ready = pending;
    ready.insert(QStringLiteral("jpegPath"), actual);
    ready.insert(QStringLiteral("closed"), true);
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
            captures.insert(proxy, Capture{path, resolution});
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
    QByteArray enhanced;
    QJsonObject pending;
    const quintptr caller = reinterpret_cast<quintptr>(__builtin_return_address(0));
    try {
        const auto prepare = [&]() {
        static const bool enabled = X1D::runtimeMatches("jpeg-daemon");
        if (!enabled || caller != 0x1e2e0 || offset)
            return;
        Capture capture;
        {
            QMutexLocker locker(&captureMutex);
            capture = captures.take(proxy);
        }
        X1D::invalidateRecord(capture.source);
        X1D::invalidateRecord(target);
        XjInfo info;
        const uint8_t *source = reinterpret_cast<const uint8_t *>(input.constData());
        if (capture.resolution != 2 || !X1D::storagePathValid(capture.source) ||
            !target.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive) ||
            xj_inspect(source, input.size(), &info) || !info.has_unique_id || input.size() > X1D::MaximumJpegBytes)
            return;
        QByteArray preview(XJ_PREVIEW_MAX_BYTES, '\0');
        XjPreviewResult result;
        if (xj_make_preview(source, input.size(), reinterpret_cast<uint8_t *>(preview.data()),
                            preview.size(), &result, X1D::codec())) return;
        preview.resize(result.bytes);
        uint32_t bytes = 0;
        if (xj_embed_preview(source, input.size(), reinterpret_cast<const uint8_t *>(preview.constData()),
                             preview.size(), nullptr, 0, &bytes) != XJ_NEED_OUTPUT || bytes > X1D::MaximumJpegBytes)
            return;
        enhanced.resize(bytes);
        if (xj_embed_preview(source, input.size(), reinterpret_cast<const uint8_t *>(preview.constData()),
                             preview.size(), reinterpret_cast<uint8_t *>(enhanced.data()), enhanced.size(), &bytes))
            return;
        XjInfo combined;
        if (xj_inspect(reinterpret_cast<const uint8_t *>(enhanced.constData()), enhanced.size(), &combined))
            return;
        enhanced.resize(combined.eoi_end);
        bool ok;
        const QByteArray raw = X1D::readFile(capture.source, 0, X1D::PrefixBytes, &ok);
        uint8_t rawId[32];
        if (ok && raw.size() == X1D::PrefixBytes &&
            !xj_tiff_unique_id(reinterpret_cast<const uint8_t *>(raw.constData()), raw.size(), rawId) &&
            QByteArray(reinterpret_cast<const char *>(rawId), 32) == QByteArray(reinterpret_cast<const char *>(info.unique_id), 32)) {
            pending.insert(QStringLiteral("version"), 2);
            pending.insert(QStringLiteral("rawPath"), capture.source);
            pending.insert(QStringLiteral("rawHash"), QString::fromLatin1(X1D::sha256(raw)));
            pending.insert(QStringLiteral("uidHash"), QString::fromLatin1(X1D::sha256(QByteArray(reinterpret_cast<const char *>(rawId), 32))));
            pending.insert(QStringLiteral("prefixHash"), QString::fromLatin1(X1D::sha256(enhanced.left(combined.header_bytes))));
            pending.insert(QStringLiteral("prefixBytes"), int(combined.header_bytes));
            pending.insert(QStringLiteral("jpegHash"), QString::fromLatin1(X1D::sha256(enhanced)));
            pending.insert(QStringLiteral("bytes"), enhanced.size());
            pending.insert(QStringLiteral("orientation"), int(info.orientation));
        }
        };
        prepare();
    } catch (...) {
        enhanced.clear(); pending = QJsonObject();
    }
    /* 严格只提交一次。之后的辅助监听异常不得重发原文件覆盖新成片。 */
    QDBusPendingCallWatcher *watcher = original(proxy, enhanced.isEmpty() ? input : enhanced, offset, target);
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
