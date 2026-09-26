#include "replay_runtime.h"
#include "display_pixels.h"
#include "ready_refresh.h"
#include "preview_cache.h"
#include "replay_budget.h"
#include "replay_retry.h"
#include "replay_catalog.h"
#include "safe_texture.h"
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qmutex.h>
#include <QtCore/qsemaphore.h>
#include <QtCore/qurl.h>
#include <QtQuick/qquickimageprovider.h>
#include <QtQuick/qquickwindow.h>
#include <dlfcn.h>
#include <memory>
#include <cstdlib>

namespace {
bool sessionAdmission(int upload)
{
    const char *enabled=std::getenv("X1D_REPLAY_SESSION");
    if(!enabled || QByteArray(enabled)!="1") return true; // 保留独立核心的离线使用。
    using Admit=bool (*)(int);
    static const auto admit=reinterpret_cast<Admit>(dlsym(RTLD_DEFAULT,"x1d_replay_session_admit"));
    return admit && admit(upload);
}

class BufferLease {
public:
    /* Qt 5.5.1 的 provider 工作线程串行处理请求；不在这里等旧工厂释放。 */
    explicit BufferLease(bool full) : held(full ? X1D::acquireFull() : X1D::FullToken()) {}
    X1D::FullToken take() { X1D::FullToken value; value.swap(held); return value; }
    bool available() const { return bool(held); }
private:
    X1D::FullToken held;
};

class Pixels {
public:
    explicit Pixels(int size) : data(size > 0 ? X1D::codec()->allocate(size) : nullptr) {}
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

/* 一个 owner 对应同一块 CPU 像素。QImage 隐式共享的最后一个引用才归还额度。 */
struct SharedPixels {
    uint8_t *data;
    X1D::FullToken lease;
    explicit SharedPixels(uint8_t *buffer) : data(buffer) {}
    ~SharedPixels() {
        X1D::codec()->release(data);
    }
};

void releasePixels(void *pointer)
{ delete static_cast<SharedPixels *>(pointer); }

class Texture final : public QQuickTextureFactory {
public:
    explicit Texture(const QImage &image,const X1D::FullToken &lease=X1D::FullToken())
        : pixels(image),dimensions(image.size()),fullRequest(bool(lease)),permit(lease) {}
    void setSource(const QString &path) { source=path; }
    QSGTexture *createTexture(QQuickWindow *window) const override {
        if (!window) return nullptr;
        QMutexLocker lock(&mutex);
        const bool full=fullRequest;
        if (!sessionAdmission(1)) {
            if (full) X1D::retryFull(source,X1D::ContextUnavailable);
            return nullptr;
        }
        if (pixels.isNull()) {
            if (full) X1D::retryFull(source,X1D::ContextUnavailable);
            return nullptr;
        }
        QSGTexture *texture=nullptr;
        try { texture=X1D::uploadChecked(pixels,permit); } catch (...) {}
        if (full) {
            // 上传成功后 GPU 接管额度；失败则释放 CPU，保留下层预览。
            pixels=QImage(); permit.reset();
            if (!texture) X1D::retryFull(source,X1D::UploadRejected);
        }
        return texture;
    }
    QSize textureSize() const override { return dimensions; }
    int textureByteCount() const override { return dimensions.width() * dimensions.height() * 4; }
    QImage image() const override { QMutexLocker lock(&mutex); return pixels; }
    const QImage &cpuImage() const { return pixels; }
private:
    // Full 不在 GPU 上传后继续保留另一张 200 MB CPU 副本。上下文重建请求新加载。
    mutable QImage pixels;
    const QSize dimensions;
    const bool fullRequest;
    mutable X1D::FullToken permit;
    mutable QMutex mutex;
    QString source;
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

// File 的传输失败与确实为空分开处理；未知错误不能触发 RAW 读取。
QByteArray completeFile(const QString &path, const QByteArray &first, const QString &source, bool full)
{
    QByteArray bytes=first;
    QElapsedTimer timer; timer.start();
    const int chunkSize=1024*1024;
    bool end=first.size()<chunkSize;
    while (!end) {
        if (timer.elapsed()>15000 || (full && !X1D::currentFullSource(source)) ||
            bytes.size()>=X1D::MaximumJpegBytes) return QByteArray();
        bool ok;
        const QByteArray chunk=X1D::readFile(path,bytes.size(),qMin(chunkSize,X1D::MaximumJpegBytes-bytes.size()),&ok);
        if (!ok) return QByteArray();
        end=chunk.size()<chunkSize;
        bytes.append(chunk);
    }
    // 重读开头以拒绝分块读取过程中常见的同名替换；不声称是存储事务快照。
    bool ok;
    const QByteArray check=X1D::readFile(path,0,qMin(65536,bytes.size()),&ok);
    if (!ok || check!=bytes.left(check.size()) || check.size()!=qMin(65536,bytes.size())) return QByteArray();
    return bytes;
}

Texture *decode(const QByteArray &data, uint32_t orientation, int color, BufferLease &lease, bool full, const QString &path)
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
    if (!full) {
        // 在 TurboJPEG 内部进行 DCT 缩放，分配前确定像素大小。
        // LCD 为 640x480，1/8 的 Full 是 1022x766；无需 200 MB 中间图。
        if (!codec->scaling) return nullptr;
        int factors=0; const XjScalingFactor *scale=codec->scaling(&factors);
        if (!scale || factors<1 || factors>64) return nullptr;
        int chosenW=width,chosenH=height;
        for (int i=0;i<factors;++i) {
            if (scale[i].num<1 || scale[i].denom<1 || scale[i].num>scale[i].denom || scale[i].denom>64) continue;
            const int w=(width*scale[i].num+scale[i].denom-1)/scale[i].denom;
            const int h=(height*scale[i].num+scale[i].denom-1)/scale[i].denom;
            if (w>=qMin(width,640) && h>=qMin(height,480) && w*h<chosenW*chosenH) { chosenW=w; chosenH=h; }
        }
        width=chosenW; height=chosenH;
        if (width*height>1024*1024) return nullptr;
    }
    if (full && !X1D::currentFullSource(path)) return nullptr;
    const uint32_t count = uint32_t(width) * height;
    Pixels pixels(count * 4);
    if (!pixels.data || codec->decompress(decoder.handle, source, data.size(), pixels.data,
                                         width, width * 4, height, 3, 4096) ||
        xj_display_bgra(pixels.data, count * 4, width, height, color)) return nullptr;
    if (full && !X1D::currentFullSource(path)) return nullptr;
    if (orientation != 1) {
        const uint32_t scratchBytes = xj_orient_scratch_bytes(width, height, orientation);
        Pixels visited(scratchBytes);
        if ((scratchBytes && !visited.data) || xj_orient_bgra(pixels.data, count * 4, width, height, orientation,
                                                            visited.data, scratchBytes)) return nullptr;
    }
    if (orientation >= 5) qSwap(width, height);
    std::unique_ptr<SharedPixels> owner(new SharedPixels(pixels.data));
    pixels.take();
    /* 固定 Qt 5.5.1 QImageData::create 的失败路径不接管 cleanupInfo。 */
    QImage image(static_cast<const uchar *>(owner->data), width, height, width * 4,
                 QImage::Format_RGB32, releasePixels, owner.get());
    if (image.isNull()) return nullptr;
    owner->lease = lease.take();
    const X1D::FullToken permit=owner->lease;
    owner.release();
    /* new 失败时 image 的析构仍释放同一像素和额度。 */
    return new Texture(image,permit);
}

class Provider final : public QQuickImageProvider {
public:
    explicit Provider(QQuickImageProvider *provider)
        : QQuickImageProvider(Texture, ForceAsynchronousImageLoading), original(provider) {}
    ~Provider() override { delete original; }
    QQuickTextureFactory *requestTexture(const QString &id, QSize *size, const QSize &requested) override {
        bool jpegObserved=false;
        try {
            int skip=0; bool full=false;
            if (id.startsWith(QLatin1String("preview"))) skip=7;
            else if (id.startsWith(QLatin1String("thumb"))) skip=5;
            else if (id.startsWith(QLatin1String("fullsize"))) { skip=8; full=true; }
            if (skip) {
                if (!sessionAdmission(0)) return nullptr;
                const QString source=id.mid(skip);
                QString path=X1D::pairedJpeg(source);
                if (!path.isEmpty()) {
                    jpegObserved=true; // 未判明为空前，所有异常均禁止转读 RAW。
                    if (full && !X1D::currentFullSource(source)) return nullptr;
                    QString catalogPath;
                    const int catalog=X1D::catalogJpegPath(source,&catalogPath);
                    if (catalog<0) return nullptr;
                    if (catalog>0) path=catalogPath;
                    bool ok;
                    const QByteArray first=X1D::readFile(path,0,1024*1024,&ok);
                    if (!ok) {
                        if (X1D::knownJpegAbsent(source)) return original->requestTexture(id,size,requested);
                        return nullptr;
                    }
                    // 成功返回空字节只证明文件为空，不能证明路径不存在。
                    if (first.isEmpty()) return nullptr;
                    jpegObserved=true;
                    if (jpegObserved) {
                        BufferLease lease(full);
                        if (full && !lease.available()) {
                            X1D::retryFull(source,X1D::ResourceBusy); return nullptr;
                        }
                        const QByteArray jpeg=completeFile(path,first,source,full);
                        XjInfo info;
                        if (jpeg.isEmpty() || xj_inspect(reinterpret_cast<const uint8_t *>(jpeg.constData()),jpeg.size(),&info)) return nullptr;
                        const QByteArray key=X1D::sha256(jpeg);
                        const int color=profileKind(jpeg,info);
                        if (color<0) return nullptr;
                        if (!full) {
                            QImage cached;
                            { QMutexLocker lock(&previewMutex); previews.get(key,&cached); }
                            if (!cached.isNull()) {
                                auto *texture=new ::Texture(cached);
                                if (size) *size=texture->textureSize();
                                return texture;
                            }
                        }
                        std::unique_ptr<::Texture> texture(decode(jpeg,info.orientation,color,lease,full,source));
                        if (!texture) return nullptr;
                        texture->setSource(source);
                        if (!full) {
                            QMutexLocker lock(&previewMutex);
                            previews.put(key,texture->cpuImage(),texture->textureByteCount());
                        }
                        if (size) *size=texture->textureSize();
                        return texture.release();
                    }
                }
            }
        } catch (...) { if (jpegObserved) return nullptr; }
        return original->requestTexture(id,size,requested);
    }
private:
    QQuickImageProvider *original;
    QMutex previewMutex;
    X1D::PreviewCache<QByteArray, QImage> previews;
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
 * 对回放 URL 禁用旧 pixmap 缓存，防止早期 RAW 回退被永久复用。 */
extern "C" void x1d_pixmap_load(void *, QQmlEngine *, const QUrl &, const QSize &, int, int)
    __asm__("_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform");
extern "C" void x1d_pixmap_load(void *pixmap, QQmlEngine *engine, const QUrl &url,
                                 const QSize &size, int options, int transform)
{
    using Load = void (*)(void *, QQmlEngine *, const QUrl &, const QSize &, int, int);
    static const auto original = reinterpret_cast<Load>(dlsym(RTLD_NEXT,
        "_ZN12QQuickPixmap4loadEP10QQmlEngineRK4QUrlRK5QSize6QFlagsINS_6OptionEE13AutoTransform"));
    if (!original) return;
    const quintptr caller = reinterpret_cast<quintptr>(__builtin_return_address(0));
    try {
        static const bool enabled = X1D::runtimeMatches("victory-gui");
        if (enabled && url.scheme() == QLatin1String("image") && url.host() == QLatin1String("imagestore")) {
            X1D::trackPixmap(pixmap, engine, url, caller);
            const QString id = url.path().mid(1);
            const int skip = id.startsWith(QLatin1String("preview")) ? 7 :
                             id.startsWith(QLatin1String("fullsize")) ? 8 :
                             id.startsWith(QLatin1String("thumb")) ? 5 : 0;
            if (skip) options &= ~2; // QQuickPixmap::Cache
        }
    } catch (...) {}
    original(pixmap, engine, url, size, options, transform);
}
