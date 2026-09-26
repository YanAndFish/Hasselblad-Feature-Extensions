// 机内离线自检；只创建自己的 /tmp 测试文件，不连接 FARM 或无线接口。
#define HBL_SETTINGS_STORE_ROOT "/tmp/hbl-persistent-store-selfcheck"
#include "persistent_settings_store.h"
#include "boot_loader.h"
#include "../build/boot-data/af_relocation_data.h"
#include <QtCore/qcryptographichash.h>
#include <QtCore/qcoreapplication.h>
#include <cstdio>
#include <cstring>

int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    if(argc!=2)return 59;
    if(!std::strcmp(argv[1],"--relocation")) {
        const uint32_t bases[]={0x2bace0,0x39cec0,0x6b2c80};
        const char *hashes[]={"532115d6b37a5e234d81a22fa1116faeb8690730e1e6f2889a7641823a90ecb6",
            "e1a28a4e2393bb268cfc073652707d623e0e21984cd2b8c3e83b09bb60d0bf62",
            "2808a1b480d58a9b2911956c503a24c1d3aa1fbca6d3ae488b04a22a528166e2"};
        uint32_t words[sizeof(hbl_af_words)/4];
        for(unsigned i=0;i<3;++i) {
            if(!hbl_relocate_af(bases[i],words,sizeof(words)/4))return 60;
            const QByteArray bytes(reinterpret_cast<const char *>(words),sizeof(words));
            if(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex()!=hashes[i])return 61;
        }
        puts("persistent-relocation-selftest links=3 hardware=0");return 0;
    }
    if(std::strcmp(argv[1],"--store"))return 59;
    if(geteuid()!=0 || mkdir(HblSettingsStore::directory,0700))return 62;
    HblPersistentSettings wanted=HblPersistentSettings::defaults(),actual;
    if(HblSettingsStore::load(&actual)!=0)return 63;
    wanted.channel=7;wanted.id=19;wanted.visible=7;wanted.calibration[2]=6320;
    if(!HblSettingsStore::save(wanted) || HblSettingsStore::load(&actual)!=1)return 64;
    uint8_t a[HblPersistentSettings::Bytes],b[HblPersistentSettings::Bytes];
    if(!wanted.encode(a,sizeof(a)) || !actual.encode(b,sizeof(b)) || std::memcmp(a,b,sizeof(a)))return 65;
    wanted.channel=0;
    if(HblSettingsStore::save(wanted))return 66;
    if(HblSettingsStore::load(&actual)!=1 || !actual.encode(b,sizeof(b)) || std::memcmp(a,b,sizeof(a)))return 67;
    QFile file(QString::fromLatin1(HblSettingsStore::path));
    if(!file.open(QIODevice::Append) || file.write("x",1)!=1)return 68;
    file.close();
    if(HblSettingsStore::load(&actual)!=-1)return 69;
    if(unlink(HblSettingsStore::path) || symlink("/dev/null",HblSettingsStore::path))return 70;
    if(HblSettingsStore::load(&actual)!=-1 || HblSettingsStore::save(HblPersistentSettings::defaults()))return 71;
    if(unlink(HblSettingsStore::path) || rmdir(HblSettingsStore::directory))return 72;
    puts("persistent-store-selftest roundtrip=1 invalid=1 truncated=1 symlink=1 hardware=0");return 0;
}
