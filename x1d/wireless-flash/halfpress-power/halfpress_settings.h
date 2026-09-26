#ifndef HBL_HALF_PRESS_SETTINGS_H
#define HBL_HALF_PRESS_SETTINGS_H
#include <QtQml/QQmlPropertyMap>
#include "persistent_settings_store.h"

// 独立字段，旧版 settings.bin 不变；缺失或损坏均默认关闭。
class HblHalfPressSettings : public QQmlPropertyMap {
    static const char *path(){return HBL_SETTINGS_STORE_ROOT "/halfpress-power";}
    static bool read(bool &enabled) {
        if(!HblSettingsStore::directoryValid())return false;
        int fd=open(path(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0){enabled=false;return errno==ENOENT;}
        uint32_t mode=0,uid=0,links=0;int64_t size=0;char bytes[3]={};
        bool ok=holdFileMetadata(fd,mode,uid,links,size)&&S_ISREG(mode)&&uid==geteuid()&&
            (mode&0777)==0600&&links==1&&size==2&&::read(fd,bytes,3)==2&&
            (bytes[0]=='0'||bytes[0]=='1')&&bytes[1]=='\n';
        close(fd);enabled=ok&&bytes[0]=='1';return ok;
    }
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key!=QStringLiteral("enabled")||input.type()!=QVariant::Bool)return value(key);
        bool previous=false;
        if(!read(previous)){insert("error",QString::fromUtf8("设置文件不可用"));return value(key);}
        QSaveFile file(QString::fromLatin1(path()));file.setDirectWriteFallback(false);
        const char bytes[2]={input.toBool()?'1':'0','\n'};
        if(!file.open(QIODevice::WriteOnly)||!file.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner)||
           file.write(bytes,2)!=2||!file.flush()||fsync(file.handle())||!file.commit()) {
            insert("error",QString::fromUtf8("保存失败，原设置保留"));return value(key);
        }
        int fd=open(HBL_SETTINGS_STORE_ROOT,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        bool durable=fd>=0&&fsync(fd)==0;if(fd>=0)close(fd);
        insert("error",durable?QString():QString::fromUtf8("已写入，持久化确认失败"));
        return input;
    }
public:
    explicit HblHalfPressSettings(QObject *parent):QQmlPropertyMap(parent) {
        bool enabled=false;bool ok=read(enabled);
        insert("enabled",enabled);insert("error",ok?QString():QString::fromUtf8("设置文件不可用"));
    }
};
#endif
