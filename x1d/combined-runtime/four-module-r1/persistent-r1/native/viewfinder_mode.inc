// 三态取景偏好独立存储，不改写原厂布尔项或无线设置。
void viewfinderInitialize() {
    int mode=-1;
    const char *path=HBL_SETTINGS_STORE_ROOT "/viewfinder-mode";
    if(persistence && HblSettingsStore::directoryValid()) {
        const int f=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(f>=0) {
            uint32_t permissions=0,uid=0,links=0;int64_t size=0;char bytes[3]={0,0,0};
            if(holdFileMetadata(f,permissions,uid,links,size) && S_ISREG(permissions) && uid==geteuid() &&
               (permissions&0777)==0600 && links==1 && size==2 &&
               read(f,bytes,3)==2 && bytes[0]>='0' && bytes[0]<='2' && bytes[1]=='\n')
                mode=bytes[0]-'0';
            close(f);
        }
    }
    insert(QStringLiteral("viewfinderMode"),mode);
    insert(QStringLiteral("viewfinderModeError"),QString());
}
QVariant viewfinderSelect(const QVariant &input) {
    bool ok=false; const int mode=input.toInt(&ok);
    const QVariant old=value(QStringLiteral("viewfinderMode"));
    if(!ok || mode<0 || mode>2 || input.toDouble()!=double(mode))return old;
    if(!persistence || !HblSettingsStore::directoryValid()) {
        insert(QStringLiteral("viewfinderModeError"),QStringLiteral("取景模式未保存，请重新启动后再试"));
        return old;
    }
    const char *path=HBL_SETTINGS_STORE_ROOT "/viewfinder-mode";
    uint32_t permissions=0,uid=0;
    if(!rf_local_stat(path,&permissions,&uid)) {
        if(!S_ISREG(permissions) || uid!=geteuid() || (permissions&0777)!=0600)return old;
    } else if(errno!=ENOENT)return old;
    QSaveFile f(QString::fromLatin1(path));f.setDirectWriteFallback(false);
    const char bytes[2]={char('0'+mode),'\n'};
    if(!f.open(QIODevice::WriteOnly) || !f.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner) ||
       f.write(bytes,2)!=2 || !f.flush() || fsync(f.handle()) || !f.commit()) {
        insert(QStringLiteral("viewfinderModeError"),QStringLiteral("取景模式保存失败，原模式保留"));
        return old;
    }
    const int dir=open(HBL_SETTINGS_STORE_ROOT,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    const bool durable=dir>=0 && fsync(dir)==0;
    if(dir>=0)close(dir);
    insert(QStringLiteral("viewfinderModeError"),durable ? QString() : QStringLiteral("取景模式已写入，持久化确认失败"));
    return mode;
}
