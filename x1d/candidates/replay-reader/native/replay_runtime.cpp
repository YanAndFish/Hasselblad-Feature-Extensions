#include "replay_runtime.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qcryptographichash.h>
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qfile.h>
#include <QtCore/qfileinfo.h>
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
    const char *wanted = name == QLatin1String("victory-gui") ? X1D_GUI_SHA256 : "";
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
    if (!storagePathValid(path) || !path.endsWith(QLatin1String(".jpg"), Qt::CaseInsensitive) || count < 1 || count > 1024 * 1024 ||
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

const XjCodec *codec()
{
    static const XjCodec api = []() {
        XjCodec c = {};
        c.size = sizeof(c); c.version = 1;
        /* 使用绑定版本公共导出；不调用设备 VPU 初始化或额外硬件入口。 */
        void *lib = dlopen("libturbojpeg.so.0", RTLD_NOW | RTLD_LOCAL);
        if (!lib) return XjCodec{};
#define X1D_TJ(field, name) c.field = reinterpret_cast<decltype(c.field)>(dlsym(lib, name))
        X1D_TJ(init_decompress, "tjInitDecompress");
        X1D_TJ(destroy, "tjDestroy"); X1D_TJ(allocate, "tjAlloc"); X1D_TJ(release, "tjFree");
        X1D_TJ(header, "tjDecompressHeader3"); X1D_TJ(scaling, "tjGetScalingFactors");
        X1D_TJ(decompress, "tjDecompress2");
#undef X1D_TJ
        return c;
    }();
    return &api;
}
}
