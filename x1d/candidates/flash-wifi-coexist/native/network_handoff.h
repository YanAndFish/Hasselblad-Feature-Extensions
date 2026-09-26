#ifndef HBL_COEXIST_NETWORK_HANDOFF_H
#define HBL_COEXIST_NETWORK_HANDOFF_H
#include <QtCore/qobject.h>
#include <QtCore/qprocess.h>
#include <QtCore/qtimer.h>
#include <QtCore/qregexp.h>
#include <functional>

namespace coexist {
// 只调用已命名的 wl 子命令；不经过 shell。原响应不进入日志。
class NetworkHandoff : public QObject {
public:
    enum Operation { Save, Suspend, Restore };
    explicit NetworkHandoff(QObject *parent=nullptr):QObject(parent) {
        QProcessEnvironment env=QProcessEnvironment::systemEnvironment();
        env.remove(QStringLiteral("LD_PRELOAD"));process.setProcessEnvironment(env);
        process.setProcessChannelMode(QProcess::SeparateChannels);
        watchdog.setSingleShot(true);
        QObject::connect(&watchdog,&QTimer::timeout,this,[this](){timedOut=true;process.kill();});
        QObject::connect(&process,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),
            this,[this](int code,QProcess::ExitStatus status){done(code==0 && status==QProcess::NormalExit && !timedOut);});
        QObject::connect(&process,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),
            this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart)done(false);});
    }
    ~NetworkHandoff() override {
        finished=nullptr;watchdog.stop();
        if(process.state()!=QProcess::NotRunning) {process.kill();process.waitForFinished(200);}
    }
    std::function<void(Operation,bool)> finished;
    bool busy=false,saved=false;
    bool start(Operation next) {
        if(busy || (next!=Save && !saved)) return false;
        operation=next;step=0;busy=true;allOk=true;
        if(next==Save) {saved=false;channel.clear();rawChannel=0;}
        QTimer::singleShot(0,this,[this](){run();});return true;
    }
private:
    QProcess process;QTimer watchdog;
    Operation operation=Save;
    unsigned step=0,scanSuppressed=0,rawChannel=0;
    QString channel;
    bool timedOut=false,allOk=true;
    static bool parseChannel(const QByteArray &bytes,QString *text,unsigned *raw) {
        // X1D 旧 wl 的人类可读频道表达式与括号中的编码必须同时存在。
        QRegExp pattern(QStringLiteral("^([0-9]{1,3}(?:[ab])?(?:/(?:20|40|80|160))?(?:[ul])?) \\(0x([0-9a-fA-F]{4})\\)$"));
        if(!pattern.exactMatch(QString::fromLatin1(bytes))) return false;
        bool ok=false;const unsigned value=pattern.cap(2).toUInt(&ok,16);
        if(!ok || (value&0xc000)!=0xc000) return false;
        *text=pattern.cap(1);*raw=value;return true;
    }
    static bool scalar(const QByteArray &bytes,unsigned *value) {
        if(bytes!="0" && bytes!="1") return false;
        *value=bytes=="1";return true;
    }
    void run() {
        QStringList args;
        if(operation==Save) {
            if(step==0)args<<QStringLiteral("chanspec");
            else if(step==1)args<<QStringLiteral("phy_txpwrctrl");
            else if(step==2)args<<QStringLiteral("scansuppress");
            else {saved=allOk;finish(allOk);return;}
        } else if(operation==Suspend) {
            if(step==0)args<<QStringLiteral("scansuppress")<<QStringLiteral("1");
            else if(step==1)args<<QStringLiteral("scansuppress");
            else {finish(allOk);return;}
        } else {
            if(step==0)args<<QStringLiteral("chanspec")<<channel;
            else if(step==1)args<<QStringLiteral("phy_txpwrctrl")<<QStringLiteral("1");
            else if(step==2)args<<QStringLiteral("scansuppress")<<QString::number(scanSuppressed);
            else if(step==3)args<<QStringLiteral("chanspec");
            else if(step==4)args<<QStringLiteral("phy_txpwrctrl");
            else if(step==5)args<<QStringLiteral("scansuppress");
            else {finish(allOk);return;}
        }
        timedOut=false;watchdog.start(1500);process.start(QStringLiteral("/usr/bin/wl"),args);
    }
    void done(bool ok) {
        if(!busy) return;
        watchdog.stop();const QByteArray bytes=process.readAllStandardOutput().trimmed();process.readAllStandardError();
        if(bytes.size()>1024)ok=false;
        unsigned value=0;
        if(ok && operation==Save) {
            if(step==0)ok=parseChannel(bytes,&channel,&rawChannel);
            // 自动发射功率控制是本轮网络基线前置条件；固定增益状态不猜测恢复。
            if(step==1)ok=scalar(bytes,&value) && value==1;
            if(step==2)ok=scalar(bytes,&scanSuppressed);
        } else if(ok && operation==Suspend) {
            ok=step==0 ? bytes.isEmpty() : scalar(bytes,&value) && value==1;
        } else if(ok && operation==Restore) {
            if(step==0) {
                const QByteArray prefix("Chanspec set to ");bool parsed=false;
                value=bytes.mid(prefix.size()).toUInt(&parsed,16);
                ok=bytes.isEmpty() || (bytes.startsWith(prefix) && parsed && value==rawChannel);
            } else if(step<3)ok=bytes.isEmpty();
            else if(step==3) {QString restored;ok=parseChannel(bytes,&restored,&value) && value==rawChannel;}
            else if(step==4)ok=scalar(bytes,&value) && value==1;
            else ok=scalar(bytes,&value) && value==scanSuppressed;
        }
        allOk=allOk && ok;
        // 恢复中某项失败仍尝试恢复功率控制和扫描；不尝试继续拍摄。
        if(!ok && operation!=Restore) {finish(false);return;}
        ++step;QTimer::singleShot(0,this,[this](){run();});
    }
    void finish(bool ok) {busy=false;const auto callback=finished;if(callback)callback(operation,ok);}
};
}
#endif
