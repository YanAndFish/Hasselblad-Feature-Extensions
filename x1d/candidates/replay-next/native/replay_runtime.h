#ifndef X1D_REPLAY_RUNTIME_H
#define X1D_REPLAY_RUNTIME_H

#include <QtCore/qbytearray.h>
#include <QtCore/qjsonobject.h>
#include <QtCore/qstring.h>
#include <QtDBus/qdbusconnection.h>
#include "jpeg_preview.h"

/* 返回值约定已按 1.25.0 ARM 调用核对；不重建任何专有对象布局。 */
class Bus {
public:
    static QDBusConnection bus();
    static const QString &storageService();
    static const QString &storagePath();
    static const QString &storageInterface();
};

namespace X1D {
const int PrefixBytes = 128 * 1024;
const int MaximumJpegBytes = 128 * 1024 * 1024;
bool runtimeMatches(const char *role);
QByteArray sha256(const QByteArray &data);
bool storagePathValid(const QString &path);
QByteArray readFile(const QString &path, quint64 offset, int count, bool *ok);
QByteArray readPrefix(const QString &path, int count, bool *ok);
bool persistentVolumeReady();
QString recordDirectory();
bool loadRecord(const QString &source, QJsonObject *record);
bool recordValid(const QJsonObject &record);
bool saveRecord(const QString &source, const QJsonObject &record);
void invalidateRecord(const QString &source);
bool sameSource(const QString &source, const QJsonObject &record);
const XjCodec *codec();
}
#endif
