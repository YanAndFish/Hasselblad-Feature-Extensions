#ifndef HBL_PERSISTENT_SETTINGS_STORE_H
#define HBL_PERSISTENT_SETTINGS_STORE_H
#include "persistent_settings.h"
#include "formal_install_hold.h"
#include <QtCore/qfile.h>
#include <QtCore/qsavefile.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

namespace HblSettingsStore {
#ifndef HBL_SETTINGS_STORE_ROOT
#define HBL_SETTINGS_STORE_ROOT "/media/data/hbl-four-module"
#endif
static const char *directory=HBL_SETTINGS_STORE_ROOT;
static const char *path=HBL_SETTINGS_STORE_ROOT "/settings.bin";
inline bool directoryValid() {
    return holdDirectorySafe(directory);
}
// 0=无记录，1=有效记录，-1=读取/内容异常；异常不会覆盖既有文件。
inline int load(HblPersistentSettings *out) {
    if(!directoryValid())return -1;
    const int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return errno==ENOENT ? 0:-1;
    uint32_t mode=0,uid=0,links=0;int64_t size=0;
    if(!holdFileMetadata(fd,mode,uid,links,size) || !S_ISREG(mode) || uid!=geteuid() ||
       (mode&0777)!=0600 || links!=1 || size!=HblPersistentSettings::Bytes){close(fd);return -1;}
    QFile f;if(!f.open(fd,QIODevice::ReadOnly,QFileDevice::AutoCloseHandle)){close(fd);return -1;}
    const QByteArray bytes=f.read(HblPersistentSettings::Bytes+1);
    return HblPersistentSettings::decode(reinterpret_cast<const uint8_t *>(bytes.constData()),size_t(bytes.size()),out) ? 1:-1;
}
inline bool save(const HblPersistentSettings &s) {
    uint8_t bytes[HblPersistentSettings::Bytes];
    if(!directoryValid() || !s.encode(bytes,sizeof(bytes)))return false;
    uint32_t mode=0,uid=0;
    if(!rf_local_stat(path,&mode,&uid)) {
        if(!S_ISREG(mode) || uid!=geteuid() || (mode&0777)!=0600)return false;
    } else if(errno!=ENOENT)return false;
    QSaveFile f(QString::fromLatin1(path));f.setDirectWriteFallback(false);
    if(!f.open(QIODevice::WriteOnly))return false;
    if(!f.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner) ||
       f.write(reinterpret_cast<const char *>(bytes),sizeof(bytes))!=sizeof(bytes) || !f.flush() || fsync(f.handle()))return false;
    if(!f.commit())return false;
    const int fd=open(directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return false;
    const bool durable=fsync(fd)==0;close(fd);return durable;
}
}
#endif
