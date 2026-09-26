#include "replay_catalog.h"
#include "replay_runtime.h"
#include <QtCore/qabstractitemmodel.h>
#include <QtCore/qelapsedtimer.h>
#include <QtCore/qmutex.h>
#include <QtCore/qpointer.h>
#include <QtCore/qset.h>
#include <QtCore/qhash.h>
#include <QtCore/qurl.h>
#include <QtQml/qqmlapplicationengine.h>
#include <QtQml/qjsvalue.h>

namespace {
QMutex mutex;
QSet<QString> absent;
QHash<QString,QString> present;
QElapsedTimer fresh;
QPointer<QAbstractItemModel> watched;
QString watchedPath;
bool dirty=true;

QString parentPath(const QString &path) { return path.left(path.lastIndexOf(QLatin1Char('/'))); }
QString key(const QString &path) {
    const QString pair=X1D::pairedJpeg(path);
    return pair.isEmpty() ? QString() : pair.left(pair.size()-4)+QStringLiteral(".jpg");
}
}

void X1D::invalidateCatalog() {
    QMutexLocker lock(&mutex);
    absent.clear(); present.clear(); fresh.invalidate(); dirty=true;
}

void X1D::replaceCatalog(const QString &directory,const QStringList &raw,const QStringList &jpeg,bool complete) {
    QSet<QString> result;
    QHash<QString,QString> images;
    if (complete && storagePathValid(directory) && raw.size()+jpeg.size()<=4096) {
        for (const QString &path:jpeg) {
            if (parentPath(path)!=directory || !path.endsWith(QLatin1String(".jpg"),Qt::CaseInsensitive) || key(path).isEmpty()) { complete=false; break; }
            const QString k=key(path);
            images.insert(k,images.contains(k) ? QString() : path);
        }
        for (const QString &path:raw) {
            if (parentPath(path)!=directory || !path.endsWith(QLatin1String(".3fr"),Qt::CaseInsensitive) || key(path).isEmpty()) { complete=false; break; }
            if (!images.contains(key(path))) result.insert(path);
        }
    } else complete=false;
    QMutexLocker lock(&mutex);
    absent=complete ? result : QSet<QString>();
    present=complete ? images : QHash<QString,QString>();
    fresh.start(); dirty=false;
}

int X1D::catalogJpegPath(const QString &source,QString *path) {
    QMutexLocker lock(&mutex);
    if (!fresh.isValid() || fresh.hasExpired(1500)) return 0;
    const auto found=present.constFind(key(source));
    if (found==present.constEnd()) return 0;
    if (found.value().isEmpty()) return -1;
    *path=found.value(); return 1;
}

bool X1D::knownJpegAbsent(const QString &source) {
    QMutexLocker lock(&mutex);
    // 只接受本次 GUI 请求刚读过的完整模型；卡/目录/列表变化使此判断失效。
    return fresh.isValid() && !fresh.hasExpired(1500) && absent.contains(source);
}

void X1D::updateCatalog(QQmlEngine *engine) {
    auto *application=qobject_cast<QQmlApplicationEngine *>(engine);
    if (!application || application->rootObjects().isEmpty()) { invalidateCatalog(); return; }
    const QVariant value=application->rootObjects().first()->property("replayCatalogModel");
    QObject *object=value.value<QObject *>();
    if (!object && value.userType()==qMetaTypeId<QJSValue>()) object=value.value<QJSValue>().toQObject();
    auto *model=qobject_cast<QAbstractItemModel *>(object);
    if (!model || !model->inherits("ContentModel") || model->thread()!=engine->thread()) { invalidateCatalog(); return; }
    if (watched!=model) {
        invalidateCatalog(); watched=model;
        QObject::connect(model,&QAbstractItemModel::modelAboutToBeReset,engine,[](){ X1D::invalidateCatalog(); });
        QObject::connect(model,&QAbstractItemModel::rowsAboutToBeInserted,engine,[](){ X1D::invalidateCatalog(); });
        QObject::connect(model,&QAbstractItemModel::rowsAboutToBeRemoved,engine,[](){ X1D::invalidateCatalog(); });
        QObject::connect(model,&QAbstractItemModel::dataChanged,engine,[](){ X1D::invalidateCatalog(); });
        QObject::connect(model,&QObject::destroyed,engine,[](){ X1D::invalidateCatalog(); });
    }
    const QVariant browsing=model->property("isBrowsing"), possible=model->property("isBrowsingPossible");
    const QString directory=model->property("path").toString();
    const int volume=model->property("browseVolume").toInt();
    const int status=model->property(volume==0 ? "card0Status" : "card1Status").toInt();
    if (browsing.type()!=QVariant::Bool || browsing.toBool() || possible.type()!=QVariant::Bool || !possible.toBool() ||
        model->property("isDeleting").toBool() || model->property("pathType").toInt()!=2 ||
        (volume!=0 && volume!=1) || status==2 || status==3 || model->canFetchMore(QModelIndex()) || !storagePathValid(directory)) {
        invalidateCatalog(); return;
    }
    {
        QMutexLocker lock(&mutex);
        if (!dirty && watchedPath==directory) { fresh.start(); return; }
    }
    QStringList raw,jpeg;
    const int count=model->rowCount();
    if (count<0 || count>4096) { invalidateCatalog(); return; }
    bool complete=true;
    for (int i=0;i<count;++i) {
        const QModelIndex index=model->index(i,0);
        const int type=model->data(index,259).toInt(); // 固定 ContentModel::TypeRole
        if (type!=1 && type!=8) continue;
        // 固定 data(DisplayRole) 从当前行 QVariantMap 的 tagName 取值；
        // ImageRole 对 JPEG 类型返回空值，不能用来构造目录清单。
        const QString name=model->data(index,0).toString();
        if (name.isEmpty() || name.contains(QLatin1Char('/')) || name.contains(QLatin1Char('\\'))) { complete=false; break; }
        const QString source=directory+QLatin1Char('/')+name;
        if (type==1) raw.append(source); else jpeg.append(source);
    }
    watchedPath=directory;
    replaceCatalog(directory,raw,jpeg,complete);
}
