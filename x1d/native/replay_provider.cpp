#include "replay_runtime.h"
#include "display_pixels.h"
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qsemaphore.h>
#include <QtCore/qurl.h>
#include <QtQuick/qquickimageprovider.h>
#include <QtQuick/qquickwindow.h>
#include <dlfcn.h>

namespace {
QSemaphore fullBuffers(1);

class BufferLease {
public:
    explicit BufferLease(bool full) : held(full && fullBuffers.tryAcquire(1, 1500)) {}
    ~BufferLease() { if (held) fullBuffers.release(); }
    bool take() { const bool value = held; held = false; return value; }
    bool available() const { return held; }
private:
    bool held;
};

class Pixels {
public:
    explicit Pixels(int size) : data(X1D::codec()->allocate(size)) {}
    ~Pixels() { if (data) X1D::codec()->release(data); }
    uint8_t *take() { uint8_t *result = data; data = nullptr; return result; }
    uint8_t *data;
};

class Decoder {
public:
    Decoder() : handle(X1D::codec()->init_decompress()) {}
    ~Decoder() { if (handle) X1D::codec()->destroy(handle); }
    void *handle;
};

void releasePixels(void *pointer)
{ X1D::codec()->release(static_cast<uint8_t *>(pointer)); }

class Texture final : public QQuickTextureFactory {
public:
    Texture(const QImage &image, bool ownsFullLease) : pixels(image), dimensions(image.size()), lease(ownsFullLease) {}
    ~Texture() override { pixels = QImage(); release(); }
    void adoptLease(bool value) { lease = value; }
    QSGTexture *createTexture(QQuickWindow *window) const override {
        QSGTexture *result = window->createTextureFromImage(pixels);
        pixels = QImage();
        release();
        return result;
    }
    QSize textureSize() const override { return dimensions; }
    int textureByteCount() const override { return dimensions.width() * dimensions.height() * 4; }
private:
    void release() const { if (lease) { lease = false; fullBuffers.release(); } }
    mutable QImage pixels;
    QSize dimensions;
    mutable bool lease;
};

int profileKind(const QByteArray &header, const XjInfo &info)
{
    if (!info.icc_bytes) return 0;
    const auto *data = reinterpret_cast<const uint8_t *>(header.constData());
    uint32_t at = 2;
    while (at + 4 < uint32_t(header.size())) {
        if (data[at++] != 255) return -1;
        while (at < uint32_t(header.size()) && data[at] == 255) ++at;
        if (at + 3 >= uint32_t(header.size())) return -1;
        const uint8_t marker = data[at++];
        const uint32_t length = (uint32_t(data[at]) << 8) | data[at + 1];
        if (length < 2 || at + length > uint32_t(header.size())) return -1;
        if (marker == 0xe2 && length == 576 && info.icc_bytes == 578 &&
            header.mid(at + 2, 14) == QByteArray("ICC_PROFILE\0\1\1", 14)) {
            return X1D::sha256(header.mid(at + 16, 560)) ==
                QByteArray("304f569a83c1e5eddaddac54e99ed03339333db013738bb499ab64f049887e28") ? 1 : -1;
        }
        if (marker == 0xda) return -1;
        at += length;
    }
    return -1;
}

bool headerMatches(const QByteArray &header, const QJsonObject &record, XjInfo *info)
{
    if (header.size() != record.value(QStringLiteral("prefixBytes")).toInt() ||
        X1D::sha256(header) != record.value(QStringLiteral("prefixHash")).toString().toLatin1() ||
        xj_preview_info(reinterpret_cast<const uint8_t *>(header.constData()), header.size(), info) ||
        info->width != 8176 || info->height != 6128 || !info->has_unique_id || info->preview_kind != 1 ||
        int(info->header_bytes) != header.size() ||
        int(info->orientation) != record.value(QStringLiteral("orientation")).toInt()) return false;
    return X1D::sha256(QByteArray(reinterpret_cast<const char *>(info->unique_id), 32)) ==
           record.value(QStringLiteral("uidHash")).toString().toLatin1();
}

QByteArray completeFile(const QString &path, const QByteArray &header, const QJsonObject &record)
{
    const int expected = record.value(QStringLiteral("bytes")).toInt();
    QByteArray bytes = header;
    bytes.reserve(expected);
    QElapsedTimer timer;
    timer.start();
    while (bytes.size() < expected) {
        if (timer.elapsed() > 15000) return QByteArray();
        const int count = qMin(1024 * 1024, expected - bytes.size());
        bool ok;
        const QByteArray chunk = X1D::readFile(path, bytes.size(), count, &ok);
        if (!ok || chunk.size() != count) return QByteArray();
        bytes.append(chunk);
    }
    XjInfo info;
    if (X1D::sha256(bytes) != record.value(QStringLiteral("jpegHash")).toString().toLatin1() ||
        xj_inspect(reinterpret_cast<const uint8_t *>(bytes.constData()), bytes.size(), &info)) return QByteArray();
    return bytes;
}

QByteArray embeddedPreview(const QByteArray &header)
{
    const auto *source = reinterpret_cast<const uint8_t *>(header.constData());
    uint32_t needed = 0;
    if (xj_extract_preview(source, header.size(), nullptr, 0, &needed) != XJ_NEED_OUTPUT ||
        needed > XJ_PREVIEW_MAX_BYTES) return QByteArray();
    QByteArray preview(needed, '\0');
    if (xj_extract_preview(source, header.size(), reinterpret_cast<uint8_t *>(preview.data()), preview.size(), &needed))
        return QByteArray();
    preview.resize(needed);
    return preview;
}

Texture *decode(const QByteArray &data, uint32_t orientation, int color, BufferLease &lease)
{
    const XjCodec *codec = X1D::codec();
    if (!codec->init_decompress || !codec->destroy || !codec->allocate || !codec->release ||
        !codec->header || !codec->decompress) return nullptr;
    Decoder decoder;
    if (!decoder.handle) return nullptr;
    int width, height, sampling, colorspace;
    auto *source = reinterpret_cast<uint8_t *>(const_cast<char *>(data.constData()));
    if (codec->header(decoder.handle, source, data.size(), &width, &height, &sampling, &colorspace) ||
        width < 1 || height < 1 || width > 8176 || height > 6128 || (colorspace != 0 && colorspace != 1)) return nullptr;
    const uint32_t count = uint32_t(width) * height;
    Pixels pixels(count * 4);
    if (!pixels.data || codec->decompress(decoder.handle, source, data.size(), pixels.data,
                                         width, width * 4, height, 3, 4096) ||
        xj_display_bgra(pixels.data, count * 4, width, height, color)) return nullptr;
    if (orientation != 1) {
        Pixels visited((count + 7) / 8);
        if (!visited.data || xj_orient_bgra(pixels.data, count * 4, width, height, orientation,
                                           visited.data, (count + 7) / 8)) return nullptr;
    }
    if (orientation >= 5) qSwap(width, height);
    QImage image(pixels.data, width, height, width * 4, QImage::Format_RGB32, releasePixels, pixels.data);
    if (image.isNull()) return nullptr;
    pixels.take();
    /* 分配成功后才移交令牌；异常由调用方释放。 */
    Texture *texture = new Texture(image, false);
    texture->adoptLease(lease.take());
    return texture;
}

class Provider final : public QQuickImageProvider {
public:
    explicit Provider(QQuickImageProvider *provider)
        : QQuickImageProvider(Texture, ForceAsynchronousImageLoading), original(provider) {}
    ~Provider() override { delete original; }
    QQuickTextureFactory *requestTexture(const QString &id, QSize *size, const QSize &requested) override {
        try {
            int skip = 0;
            bool full = false;
            if (id.startsWith(QLatin1String("preview"))) skip = 7;
            else if (id.startsWith(QLatin1String("thumb"))) skip = 5;
            else if (id.startsWith(QLatin1String("fullsize"))) { skip = 8; full = true; }
            if (skip) {
                const QString source = id.mid(skip);
                QJsonObject record;
                if (X1D::loadRecord(source, &record) && X1D::sameSource(source, record)) {
                    BufferLease lease(full);
                    if (full && !lease.available()) return original->requestTexture(id, size, requested);
                    const QString path = record.value(QStringLiteral("jpegPath")).toString();
                    bool ok;
                    const QByteArray header = X1D::readPrefix(path, record.value(QStringLiteral("prefixBytes")).toInt(), &ok);
                    XjInfo info;
                    if (ok && headerMatches(header, record, &info)) {
                        const int color = profileKind(header, info);
                        const int bytes = record.value(QStringLiteral("bytes")).toInt();
                        /* 快速浏览仍核对本次写入的末尾存在；不为浏览读取完整主图。 */
                        const QByteArray tail = X1D::readFile(path, bytes - 2, 2, &ok);
                        if (color >= 0 && ok && tail == QByteArray("\xff\xd9", 2)) {
                            const QByteArray jpeg = full ? completeFile(path, header, record) :
                                embeddedPreview(header);
                            if (!jpeg.isEmpty()) {
                                ::Texture *texture = decode(jpeg, info.orientation, color, lease);
                                if (texture) {
                                    if (size) *size = texture->textureSize();
                                    return texture;
                                }
                            }
                        }
                    }
                }
            }
        } catch (...) { /* 所有文件、分配和解析失败均返回原 provider。 */ }
        return original->requestTexture(id, size, requested);
    }
private:
    QQuickImageProvider *original;
};
}

extern "C" void x1d_add_provider(QQmlEngine *, const QString &, QQmlImageProviderBase *)
    __asm__("_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase");
extern "C" void x1d_add_provider(QQmlEngine *engine, const QString &id, QQmlImageProviderBase *base)
{
    using Add = void (*)(QQmlEngine *, const QString &, QQmlImageProviderBase *);
    static const auto original = reinterpret_cast<Add>(dlsym(RTLD_NEXT,
        "_ZN10QQmlEngine16addImageProviderERK7QStringP21QQmlImageProviderBase"));
    if (!original) return;
    try {
        static const bool enabled = X1D::runtimeMatches("victory-gui");
        if (enabled && reinterpret_cast<quintptr>(__builtin_return_address(0)) == 0x26e80 &&
            id == QLatin1String("imagestore") && base && base->imageType() == QQmlImageProviderBase::Texture) {
            auto *provider = static_cast<QQuickImageProvider *>(base);
            base = new Provider(provider);
        }
    } catch (...) {}
    original(engine, id, base);
}

/* Qt 5.5.1 的 QQuickImageBase::load 确实经 PLT 调用此重载。
 * 对已有增强完成记录的 URL 禁用旧 pixmap 缓存，防止早期 RAW 回退被永久复用。
 * 没有对应记录的 RAW-only URL 保持原 options。 */
extern "C" void x1d_pixmap_load(void *, QQmlEngine *, const QUrl &, const QSize &, int, int)
    __asm__("_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform");
extern "C" void x1d_pixmap_load(void *pixmap, QQmlEngine *engine, const QUrl &url,
                                 const QSize &size, int options, int transform)
{
    using Load = void (*)(void *, QQmlEngine *, const QUrl &, const QSize &, int, int);
    static const auto original = reinterpret_cast<Load>(dlsym(RTLD_NEXT,
        "_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform"));
    if (!original) return;
    try {
        static const bool enabled = X1D::runtimeMatches("victory-gui");
        if (enabled && url.scheme() == QLatin1String("image") && url.host() == QLatin1String("imagestore")) {
            const QString id = url.path().mid(1);
            const int skip = id.startsWith(QLatin1String("preview")) ? 7 :
                             id.startsWith(QLatin1String("fullsize")) ? 8 :
                             id.startsWith(QLatin1String("thumb")) ? 5 : 0;
            QJsonObject record;
            if (skip && X1D::loadRecord(id.mid(skip), &record)) options &= ~2; // QQuickPixmap::Cache
        }
    } catch (...) {}
    original(pixmap, engine, url, size, options, transform);
}
