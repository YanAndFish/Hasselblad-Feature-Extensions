#include "replay_runtime.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qcryptographichash.h>
#include <QtCore/qdir.h>
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qfile.h>
#include <QtCore/qfileinfo.h>
#include <QtCore/qjsondocument.h>
#include <QtCore/qsavefile.h>
#include <QtDBus/qdbusmessage.h>
#include <dlfcn.h>

namespace X1D {
QByteArray sha256(const QByteArray &data)
{ return QCryptographicHash::hash(data, QCryptographicHash::Sha256).toHex(); }

static QByteArray fileHash(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 16 * 1024 * 1024) return QByteArray();
    return sha256(file.readAll());
}

bool runtimeMatches(const char *role)
{
    /* 从调用点进入时核对真正正在运行的文件；不读取配置、连接硬件或猜版本。 */
    static const QString name = QFileInfo(QCoreApplication::applicationFilePath()).fileName();
    if (name != QString::fromLatin1(role)) return false;
    // 两个 GUI hook 共用一次固定文件校验；后续会话准入仍分别检查现场状态。
    static const bool verified=[]() {
    const char *wanted = name == QLatin1String("jpeg-daemon") ? X1D_JPEG_SHA256 :
                         name == QLatin1String("victory-gui") ? X1D_GUI_SHA256 : "";
    if (fileHash(QStringLiteral("/proc/self/exe")) != QByteArray(wanted)) return false;
    const struct { const char *path; const char *hash; } libs[] = {
        {"/usr/lib/libappscommon.so.1.0.0", X1D_APPS_SHA256},
        {"/usr/lib/libQt5Core.so.5.5.1", X1D_QTCORE_SHA256},
        {"/usr/lib/libQt5DBus.so.5.5.1", X1D_QTDBUS_SHA256},
        {"/usr/lib/libturbojpeg.so.0.1.0", X1D_TURBO_SHA256}
    };
    for (const auto &lib : libs)
        if (fileHash(QString::fromLatin1(lib.path)) != QByteArray(lib.hash)) return false;
    if (name == QLatin1String("victory-gui")) {
        if (fileHash(QStringLiteral("/usr/lib/libQt5Gui.so.5.5.1")) != QByteArray(X1D_QTGUI_SHA256) ||
            fileHash(QStringLiteral("/usr/lib/libQt5Quick.so.5.5.1")) != QByteArray(X1D_QTQUICK_SHA256) ||
            fileHash(QStringLiteral("/usr/lib/libQt5Qml.so.5.5.1")) != QByteArray(X1D_QTQML_SHA256) ||
            fileHash(QStringLiteral("/usr/lib/libGLESv2.so.2.0.0")) != QByteArray(X1D_GLES_SHA256)) return false;
    }
    return true;
    }();
    return verified;
}

bool storagePathValid(const QString &path)
{
    if (path.isEmpty() || path.size() > 1024 || !path.startsWith(QLatin1Char('/')) ||
        path.contains(QChar(0)) || path.contains(QLatin1Char('\\'))) return false;
    for (const auto &part : path.split(QLatin1Char('/')))
        if (part == QLatin1String("..") || part == QLatin1String(".")) return false;
    return true;
}

QString pairedJpeg(const QString &source)
{
    if (!storagePathValid(source) || source.contains(QLatin1String("//"))) return QString();
    if (source.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive)) return source;
    if (!source.endsWith(QLatin1String(".3fr"), Qt::CaseInsensitive)) return QString();
    return source.left(source.size()-4)+QStringLiteral(".jpg");
}

QByteArray readFile(const QString &path, quint64 offset, int count, bool *ok)
{
    *ok = false;
    if (!storagePathValid(path) || count < 1 || count > 1024 * 1024 ||
        offset > quint64(MaximumJpegBytes)) return QByteArray();
    QDBusMessage request = QDBusMessage::createMethodCall(Bus::storageService(), Bus::storagePath(),
                                                        Bus::storageInterface(), QStringLiteral("File"));
    request << path << QVariant::fromValue<qulonglong>(offset) << count;
    const QDBusMessage reply = Bus::bus().call(request, QDBus::Block, 1500);
    const auto args = reply.arguments();
    if (reply.type() != QDBusMessage::ReplyMessage || args.size() != 1 ||
        args.first().type() != QVariant::ByteArray) return QByteArray();
    QByteArray data = args.first().toByteArray();
    if (data.size() > count) return QByteArray();
    *ok = true;
    return data;
}

QByteArray readPrefix(const QString &path, int count, bool *ok)
{
    *ok = false;
    if (count < 1 || count > int(XJ_PREFIX_MAX_BYTES)) return QByteArray();
    QByteArray result;
    result.reserve(count);
    QElapsedTimer elapsed;
    elapsed.start();
    while (result.size() < count) {
        if (elapsed.elapsed() > 6000) return QByteArray();
        const int needed = qMin(count - result.size(), 1024 * 1024);
        bool success;
        const QByteArray part = readFile(path, result.size(), needed, &success);
        if (!success || part.size() != needed) return QByteArray();
        result.append(part);
    }
    *ok = true;
    return result;
}

bool persistentVolumeReady()
{
    QFile mounts(QStringLiteral("/proc/self/mountinfo"));
    if (!mounts.open(QIODevice::ReadOnly)) return false;
    const QByteArray content = mounts.read(256 * 1024);
    if (!mounts.atEnd()) return false;
    for (const auto &line : content.split('\n')) {
        const auto parts = line.split(' ');
        if (parts.size() > 8 && parts[4] == "/media/data" && line.contains(" - ext4 ") &&
            parts[5].split(',').contains("rw")) return true;
    }
    return false;
}

QString recordDirectory()
{ return QStringLiteral("/media/data/x1d-replay-v3"); }

static QString recordName(const QString &source)
{ return recordDirectory() + QLatin1Char('/') + QString::fromLatin1(sha256(source.toUtf8())) + QStringLiteral(".json"); }

static QString pendingDirectory() { return QStringLiteral("/tmp/x1d-replay-pending-v4"); }
static QString pendingName(const QString &source)
{ return pendingDirectory()+QLatin1Char('/')+QString::fromLatin1(sha256(source.toUtf8()))+QStringLiteral(".json"); }

void invalidateRecord(const QString &source)
{
    if (storagePathValid(source) && persistentVolumeReady()) QFile::remove(recordName(source));
}

bool saveRecord(const QString &source, const QJsonObject &record)
{
    if (!storagePathValid(source) || !persistentVolumeReady()) return false;
    const bool pending=record.value(QStringLiteral("pending")).toBool();
    const QString dir = pending ? pendingDirectory() : recordDirectory();
    if (!QDir().mkpath(dir)) return false;
    QFile::setPermissions(dir, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner);
    const QByteArray bytes = QJsonDocument(record).toJson(QJsonDocument::Compact);
    if (bytes.size() > 8192) return false;
    QSaveFile file(pending ? pendingName(source) : recordName(source));
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly)) return false;
    file.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
    const bool saved=file.write(bytes) == bytes.size() && file.commit();
    if (saved && !pending) QFile::remove(pendingName(source));
    return saved;
}

bool loadRecord(const QString &source, QJsonObject *record)
{
    if (!storagePathValid(source) || !persistentVolumeReady()) return false;
    QFile file(QFile::exists(pendingName(source)) ? pendingName(source) : recordName(source));
    if (!file.open(QIODevice::ReadOnly) || file.size() < 1 || file.size() > 8192) return false;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    if (!doc.isObject()) return false;
    const QJsonObject r = doc.object();
    if (!recordValid(r)) return false;
    *record = r;
    return true;
}

bool recordValid(const QJsonObject &r)
{
    const int version=r.value(QStringLiteral("version")).toInt();
    if (version==4 && r.value(QStringLiteral("pending")).toBool())
        return storagePathValid(r.value(QStringLiteral("rawPath")).toString()) &&
            r.value(QStringLiteral("rawPath")).toString().endsWith(QLatin1String(".3fr"),Qt::CaseInsensitive) &&
            !r.value(QStringLiteral("generation")).toString().isEmpty() &&
            r.value(QStringLiteral("generation")).toString().size()<=128;
    if ((version != 3 && version != 4) ||
        r.value(QStringLiteral("closed")).toBool() != true ||
        !storagePathValid(r.value(QStringLiteral("jpegPath")).toString()) ||
        !r.value(QStringLiteral("jpegPath")).toString().endsWith(QLatin1String(".jpg"),Qt::CaseInsensitive) ||
        r.value(QStringLiteral("bytes")).toInt() < 4 ||
        r.value(QStringLiteral("bytes")).toInt() > MaximumJpegBytes) return false;
    const int prefixBytes = r.value(QStringLiteral("prefixBytes")).toInt();
    if (prefixBytes < 1 || prefixBytes > int(XJ_PREFIX_MAX_BYTES) ||
        prefixBytes > r.value(QStringLiteral("bytes")).toInt() - 2) return false;
    for (const char *field : {"rawHash", "uidHash", "prefixHash", "jpegHash"}) {
        if (version==4 && QByteArray(field)=="rawHash") continue;
        const QString value = r.value(QString::fromLatin1(field)).toString();
        if (value.size() != 64) return false;
        for (const QChar ch : value)
            if (!((ch >= QLatin1Char('0') && ch <= QLatin1Char('9')) ||
                  (ch >= QLatin1Char('a') && ch <= QLatin1Char('f')))) return false;
    }
    return true;
}

bool sameSource(const QString &source, const QJsonObject &record)
{
    const QString path=pairedJpeg(source);
    const QString jpeg=record.value(QStringLiteral("jpegPath")).toString();
    return !path.isEmpty() && storagePathValid(jpeg) && jpeg.endsWith(QLatin1String(".jpg"),Qt::CaseInsensitive) &&
        path.left(path.size()-4)==jpeg.left(jpeg.size()-4) &&
        (source==record.value(QStringLiteral("rawPath")).toString() ||
         source==record.value(QStringLiteral("jpegPath")).toString());
}

const XjCodec *codec()
{
    static const XjCodec api = []() {
        XjCodec c = {};
        c.size = sizeof(c); c.version = 1;
        /* 使用绑定版本公共导出；不调用设备 VPU 初始化或额外硬件入口。 */
        void *lib = dlopen("libturbojpeg.so.0", RTLD_NOW | RTLD_LOCAL);
        if (!lib) return XjCodec{};
#define X1D_TJ(field, name) c.field = reinterpret_cast<decltype(c.field)>(dlsym(lib, name))
        X1D_TJ(init_decompress, "tjInitDecompress"); X1D_TJ(init_compress, "tjInitCompress");
        X1D_TJ(destroy, "tjDestroy"); X1D_TJ(allocate, "tjAlloc"); X1D_TJ(release, "tjFree");
        X1D_TJ(header, "tjDecompressHeader3"); X1D_TJ(scaling, "tjGetScalingFactors");
        X1D_TJ(decompress, "tjDecompress2"); X1D_TJ(buffer_size, "tjBufSize"); X1D_TJ(compress, "tjCompress2");
#undef X1D_TJ
        return c;
    }();
    return &api;
}
}
