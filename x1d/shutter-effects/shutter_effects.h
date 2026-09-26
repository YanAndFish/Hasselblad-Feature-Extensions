#ifndef HBL_X1D_SHUTTER_EFFECTS_H
#define HBL_X1D_SHUTTER_EFFECTS_H
#include <QtQml/QQmlPropertyMap>
#include <QtQml/QQmlEngine>
#include <QtQml/QQmlContext>
#include <QtCore/QProcess>
#include <QtCore/QTimer>
#include <QtCore/QFileInfo>
#include <QtCore/QDateTime>
#include <QtCore/QDebug>
#include "persistent_settings_store.h"
#include "audio_route.h"

struct X1dSpeakerIo {
    static const char *path(){return "/sys/bus/i2c/devices/2-0018/force_headset";}
    static const char *levelPath(){return "/sys/bus/i2c/devices/2-0018/sound_level";}
    bool readValue(const char *file,int &value,int maximum) {
        int fd=open(file,O_RDONLY|O_CLOEXEC);if(fd<0)return false;
        char bytes[4]={};ssize_t size=::read(fd,bytes,sizeof(bytes));close(fd);
        if((size!=1 && size!=2) || (size==2 && bytes[1]!='\n') || bytes[0]<'0' || bytes[0]>'0'+maximum)return false;
        value=bytes[0]-'0';return true;
    }
    bool writeValue(const char *file,int value) {
        int fd=open(file,O_WRONLY|O_CLOEXEC);if(fd<0)return false;
        char byte=char('0'+value);bool ok=::write(fd,&byte,1)==1;close(fd);return ok;
    }
    bool read(int &value){return readValue(path(),value,1);}
    bool readLevel(int &value){return readValue(levelPath(),value,3);}
    bool write(int value){return writeValue(path(),value);}
    bool writeLevel(int value){return writeValue(levelPath(),value);}
};

// 使用 X1D 既有设置根和原子写入方式；不修改无线设置二进制格式。
class X1dShutterEffects : public QQmlPropertyMap {
    QProcess player;
    X1dSpeakerIo speakerIo;
    X1dAudioRoute<X1dSpeakerIo> speaker{speakerIo};
    QTimer deadline;
    QByteArray wave;
    QString executable;
    bool lastExposure=false;
    qint64 factoryAudioUntil=0;
    int configuredSoundLevel() const {
        QQmlEngine *engine=qobject_cast<QQmlEngine *>(parent());
        if(!engine)return -1;
        QObject *config=engine->rootContext()->contextProperty(QStringLiteral("configstore")).value<QObject *>();
        if(!config)return -1;
        bool ok=false;int level=config->property("soundLevel").toInt(&ok);
        return ok && level>=0 && level<=3 ? level : -1;
    }
    static X1dShutterEffects *&active() {static X1dShutterEffects *value=nullptr;return value;}
    static bool &customStarting() {static bool value=false;return value;}
    static const char *modePath() {return HBL_SETTINGS_STORE_ROOT "/shutter-effects-mode";}
    bool validFile(const char *path, int expected=-1) {
        int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0)return false;
        uint32_t mode=0,uid=0,links=0;int64_t size=0;
        bool ok=holdFileMetadata(fd,mode,uid,links,size) && S_ISREG(mode) && uid==geteuid() &&
            (mode&0777)==0600 && links==1 && (expected<0 || size==expected);
        close(fd);return ok;
    }
    int loadMode() {
        if(!HblSettingsStore::directoryValid())return 0;
        int fd=open(modePath(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0)return errno==ENOENT ? 2:0;
        uint32_t m=0,u=0,n=0;int64_t z=0;char b[3]={};
        bool ok=holdFileMetadata(fd,m,u,n,z) && S_ISREG(m) && u==geteuid() &&
            (m&0777)==0600 && n==1 && z==2 && read(fd,b,3)==2 && b[0]>='0' && b[0]<='2' && b[1]=='\n';
        close(fd);return ok?b[0]-'0':0;
    }
    QVariant select(const QVariant &input) {
        bool ok=false;int mode=input.toInt(&ok);QVariant old=value("mode");
        if(!ok || mode<0 || mode>2 || input.toDouble()!=mode)return old;
        if(!HblSettingsStore::directoryValid())return old;
        uint32_t m=0,u=0;
        if(!rf_local_stat(modePath(),&m,&u)) {if(!validFile(modePath(),2))return old;}
        else if(errno!=ENOENT)return old;
        QSaveFile file(QString::fromLatin1(modePath()));file.setDirectWriteFallback(false);
        const char bytes[2]={char('0'+mode),'\n'};
        if(!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFileDevice::ReadOwner|QFileDevice::WriteOwner) ||
           file.write(bytes,2)!=2 || !file.flush() || fsync(file.handle()) || !file.commit()) {
            insert("error",QString::fromUtf8("保存失败，原模式保留"));return old;
        }
        int dir=open(HBL_SETTINGS_STORE_ROOT,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        bool durable=dir>=0 && fsync(dir)==0;if(dir>=0)close(dir);
        insert("error",durable?QString():QString::fromUtf8("已写入，持久化确认失败"));
        return mode;
    }
    static unsigned le32(const QByteArray &b,int p) {
        const unsigned char *s=reinterpret_cast<const unsigned char *>(b.constData()+p);
        return s[0]|(unsigned(s[1])<<8)|(unsigned(s[2])<<16)|(unsigned(s[3])<<24);
    }
    bool validWave() {
        if(wave.size()<44 || wave.size()>1024*1024 || wave.left(4)!="RIFF" || wave.mid(8,4)!="WAVE" ||
           le32(wave,4)!=unsigned(wave.size()-8))return false;
        bool fmt=false,data=false;unsigned align=0,rate=0;
        for(unsigned p=12;p+8<=unsigned(wave.size());) {
            unsigned n=le32(wave,int(p+4));if(n>unsigned(wave.size())-p-8)return false;
            QByteArray id=wave.mid(int(p),4);
            if(id=="fmt ") {
                if(fmt || (n!=16 && n!=18))return false;
                const unsigned char *s=reinterpret_cast<const unsigned char *>(wave.constData()+p+8);
                unsigned channels=s[2]|(unsigned(s[3])<<8),bits=s[14]|(unsigned(s[15])<<8);
                rate=le32(wave,int(p+12));align=s[12]|(unsigned(s[13])<<8);
                if((n==18 && (s[16]!=0 || s[17]!=0)) || s[0]!=1 || s[1]!=0 || channels<1 || channels>2 || bits!=16 || align!=channels*2 ||
                   rate<8000 || rate>48000 || le32(wave,int(p+16))!=rate*align)return false;
                fmt=true;
            } else if(id=="data") {
                if(!fmt || data || !n || n%align || n>rate*align*2)return false;
                data=true;
            }
            p+=8+n+(n&1);if(p>unsigned(wave.size()))return false;
        }
        return fmt && data;
    }
    void play() {
        if(value("mode").toInt()!=2)return;
        if(!value("audioReady").toBool()){qWarning("X1D_AUDIO_SKIP unavailable");return;}
        if(QDateTime::currentMSecsSinceEpoch()<factoryAudioUntil){qWarning("X1D_AUDIO_SKIP factory-priority");return;}
        if(player.state()!=QProcess::NotRunning){qWarning("X1D_AUDIO_SKIP playing");return;}
        int level=configuredSoundLevel();
        if(level<0){qWarning("X1D_AUDIO_SKIP volume-unavailable");return;}
        if(!level){qWarning("X1D_AUDIO_SKIP factory-muted");return;}
        if(!speaker.acquire(level)){qWarning("X1D_AUDIO_SKIP speaker-unavailable");return;}
        qWarning("X1D_AUDIO_ROUTE_READY level=%d",level);
        // 不启动 shell，不持有闲置 PCM，不阻塞 GUI，不重试抢占设备。
        customStarting()=true;
        player.start(executable,QStringList()<<"-N"<<"-q"<<"-D"<<"plughw:0,0",QIODevice::ReadWrite);
        customStarting()=false;
    }
protected:
    QVariant updateValue(const QString &key,const QVariant &input) override {
        if(key=="mode")return select(input);
        if(key=="exposing") {
            bool now=input.toBool();if(now && !lastExposure)play();lastExposure=now;return now;
        }
        return value(key);
    }
public:
    static void factorySoundStarting() {
        if(customStarting() || !active())return;
        X1dShutterEffects *self=active();
        self->speaker.yieldToFactory();
        self->factoryAudioUntil=QDateTime::currentMSecsSinceEpoch()+1800;
        if(self->player.state()!=QProcess::NotRunning) {
            qWarning("X1D_AUDIO_STOP factory-priority");
            self->player.kill();self->player.waitForFinished(80);
        }
    }
    explicit X1dShutterEffects(QObject *parent=nullptr):QQmlPropertyMap(this,parent) {
        active()=this;
        insert("mode",loadMode());insert("error",QString());insert("exposing",false);insert("audioReady",false);
        for(const char *p:{"/usr/bin/aplay","/bin/aplay"})if(QFileInfo(QString::fromLatin1(p)).isExecutable()){executable=QString::fromLatin1(p);break;}
        QFile sample(QStringLiteral("/opt/hbl-af-only-v1/ciallo.wav"));
        if(sample.open(QIODevice::ReadOnly) && sample.size()<=1024*1024)wave=sample.readAll();
        if(!validWave())wave.clear();
        insert("audioReady",!wave.isEmpty() && !executable.isEmpty());
        qWarning("X1D_AUDIO_READY mode=%d ready=%d volume=%d device=plughw:0,0",value("mode").toInt(),value("audioReady").toBool(),configuredSoundLevel());
        player.setStandardOutputFile(QProcess::nullDevice());
        // 只记录有界的播放器错误，不转储任何设备或用户信息。
        QObject::connect(&player,&QProcess::readyReadStandardError,this,[this](){
            QByteArray text=player.readAllStandardError().left(180).simplified();
            if(!text.isEmpty())qWarning("X1D_AUDIO_ERROR %s",text.constData());
        });
        deadline.setSingleShot(true);deadline.setInterval(3000);
        QObject::connect(&deadline,&QTimer::timeout,this,[this](){qWarning("X1D_AUDIO_TIMEOUT");player.kill();});
        QObject::connect(&player,&QProcess::started,this,[this](){qWarning("X1D_AUDIO_STARTED");player.write(wave);player.closeWriteChannel();deadline.start();});
        QObject::connect(&player,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),this,
            [this](int code,QProcess::ExitStatus status){deadline.stop();bool restored=speaker.release();qWarning("X1D_AUDIO_FINISHED code=%d status=%d restored=%d",code,int(status),restored);if(code || status!=QProcess::NormalExit || !restored)insert("error",QString::fromUtf8("音效未播放或恢复失败"));else insert("error",QString());});
        QObject::connect(&player,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),this,
            [this](QProcess::ProcessError error){deadline.stop();if(player.state()==QProcess::NotRunning)speaker.release();qWarning("X1D_AUDIO_PROCESS_ERROR code=%d",int(error));insert("error",QString::fromUtf8("音效播放器不可用"));});
    }
    ~X1dShutterEffects() override {if(active()==this)active()=nullptr;if(player.state()!=QProcess::NotRunning){player.kill();player.waitForFinished(80);}speaker.release();}
};
#endif
