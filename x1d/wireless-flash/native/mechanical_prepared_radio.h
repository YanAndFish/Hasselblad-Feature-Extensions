#ifndef HBL_PREPARED_RADIO_H
#define HBL_PREPARED_RADIO_H
#include "mechanical_netlink_radio.h"

// 只在设置阶段生成/校验波形。就绪期间保持本模块的 MAC 占用，发射入口只读复用波形。
class Radio : public QObject {
public:
    explicit Radio(QObject *parent) : QObject(parent), channel(this) {
        QProcessEnvironment env=QProcessEnvironment::systemEnvironment();
        env.remove(QStringLiteral("LD_PRELOAD"));
        env.remove(QStringLiteral("HBL_RF_ENABLE_PLUGIN"));
        process.setProcessEnvironment(env);
        watchdog.setSingleShot(true);
        QObject::connect(&process,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),
                         this,[this](int code,QProcess::ExitStatus exitStatus) { finished(code,exitStatus); });
        QObject::connect(&process,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),
                         this,[this](QProcess::ProcessError error) {
            if (error==QProcess::FailedToStart) finished(-1,QProcess::CrashExit);
        });
        QObject::connect(&watchdog,&QTimer::timeout,this,[this]() { process.kill(); });
        channel.prepared=[this](bool ok) {
            if (operation!=Preparing) return;
            if (!ok) { fail(channel.error,false); return; }
            operation=Idle; preparedPower=activePower;
            ready=wanted && desiredPower==activePower && held;
            publish();
            if (ready && prepared) prepared(true);
            later();
        };
        channel.fired=[this](bool ok) {
            if (operation!=Firing) return;
            if (!ok) { fail(channel.error,true); return; }
            operation=Idle;
            ready=wanted && held && desiredPower==preparedPower;
            publish();
            if (completed) completed(true,true);
            later();
        };
    }
    ~Radio() override {
        completed=nullptr; prepared=nullptr; changed=nullptr;
        watchdog.stop();
        if (process.state()!=QProcess::NotRunning) {
            process.kill(); process.waitForFinished(200);
        }
        if (held) {
            QProcess cleanup;
            cleanup.setProcessEnvironment(process.processEnvironment());
            cleanup.start(QStringLiteral("/usr/bin/wl"),QStringList()<<QStringLiteral("phyreg")
                          <<QStringLiteral("27")<<QStringLiteral("b"));
            cleanup.waitForFinished(500);
        }
    }
    bool prepare(int power) {
        if (power<10 || power>100) return false;
        cleanupFailed=false;
        wanted=true; desiredPower=power;
        if (!(ready && preparedPower==power)) ready=false;
        publish(); reconcile(); return true;
    }
    bool fire(int power) {
        if (busy || !ready || !held || preparedPower!=power || !wanted) return false;
        operation=Firing; ready=false;
        // 发射先提交到已经打开的正常驱动通道；此处不启动程序或写诊断文件。
        if (!channel.fire()) { fail(channel.error,true); return false; }
        publish();
        return true;
    }
    void cancel() {
        wanted=false; ready=false;
        publish(); reconcile();
    }
    bool busy=false,ready=false;
    QString errorStep;
    std::function<void(bool,bool)> completed;
    std::function<void(bool)> prepared;
    std::function<void()> changed;
private:
    enum Operation { Idle,Preparing,Firing,Releasing } operation=Idle;
    QProcess process;
    NetlinkRadio channel;
    QTimer watchdog;
    int stage=0,desiredPower=10,activePower=10,preparedPower=10;
    bool wanted=false,held=false,cleanupFailed=false;

    void publish() {
        busy=operation!=Idle;
        if (changed) changed();
    }
    void later() { QTimer::singleShot(0,this,[this]() { reconcile(); }); }
    void start(const QStringList &args) {
        process.setProcessChannelMode(QProcess::SeparateChannels);
        watchdog.start(1000);
        process.start(QStringLiteral("/usr/bin/wl"),args);
    }
    void reconcile() {
        if (operation!=Idle) return;
        if (!wanted) {
            ready=false;
            channel.invalidate();
            if (held && !cleanupFailed) {
                operation=Releasing; publish();
                start(QStringList()<<QStringLiteral("phyreg")<<QStringLiteral("27")<<QStringLiteral("b"));
            } else publish();
            return;
        }
        if (ready && preparedPower==desiredPower) return;
        operation=Preparing; activePower=desiredPower; stage=0; ready=false; errorStep.clear();
        publish(); nextPreparation();
    }
    void nextPreparation() {
        if (!wanted || desiredPower!=activePower) {
            operation=Idle; publish(); later(); return;
        }
        if (stage==8) {
            if (!channel.prepare()) fail(channel.error,false);
            return;
        }
        static const int selectors[]={0,27,0,0,26,14,15,16};
        QStringList args;
        if (stage==2) args<<QStringLiteral("phy_txpwrindex")<<QString::number(activePower)<<QString::number(activePower);
        else if (stage==3) args<<QStringLiteral("phy_txpwrindex");
        else args<<QStringLiteral("phyreg")<<QString::number(selectors[stage])<<QStringLiteral("b");
        if (stage==4) held=true; // 任何 hold 尝试都安排对应释放。
        start(args);
    }
    void fail(const QString &step,bool wasFiring) {
        errorStep=step; wanted=false; ready=false; operation=Idle;
        publish();
        if (wasFiring) { if (completed) completed(false,false); }
        else if (prepared) prepared(false);
        later();
    }
    void finished(int code,QProcess::ExitStatus exitStatus) {
        if (operation==Idle) return;
        watchdog.stop();
        const QByteArray out=process.readAllStandardOutput().trimmed();
        process.readAllStandardError();
        bool parsed=false; const uint value=out.toUInt(&parsed,16);
        const bool exited=code==0 && exitStatus==QProcess::NormalExit;
        if (operation==Releasing) {
            // 即使释放失败，也不在此形成重试循环；保留 held 供退出清理再处理。
            const bool released=exited && parsed && value==1;
            if (released) held=false;
            operation=Idle; publish();
            if (!released) {
                cleanupFailed=true;
                errorStep=QStringLiteral("释放无线");
                if (prepared) prepared(false);
            } else later();
            return;
        }
        static const uint expected[]={0x584e,1,0,0,1,1,0xbe41,0x0e77};
        bool correct=parsed && value==expected[stage];
        if (stage==2) correct=out.isEmpty();
        if (stage==3) {
            const QByteArray prefix("txpwrindex for core{0...3}:");
            const QList<QByteArray> fields=out.mid(prefix.size()).simplified().split(' ');
            correct=out.startsWith(prefix) && fields.size()==4 &&
                    fields[0]==QByteArray::number(activePower) && fields[1]==QByteArray::number(activePower) &&
                    fields[2]=="0" && fields[3]=="0";
        }
        if (!exited || !correct) {
            static const char *labels[]={"补丁状态","清除旧准备","功率设置","功率读回","占用无线","生成波形","波形校验一","波形校验二"};
            fail(QString::fromUtf8(labels[stage]),false); return;
        }
        if (stage==1) held=false;
        ++stage; nextPreparation();
    }
};
#endif
