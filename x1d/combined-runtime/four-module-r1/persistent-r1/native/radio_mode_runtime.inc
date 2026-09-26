// 嵌入已绑定版本的 Runtime 私有区；不会自行触发拍摄或对焦。
RadioModePolicy radioMode;
QProcess modeProcess;
bool modeInitialized=false, modeBoot=false, modeFailed=false;
uint32_t modeTicket=0;
uint64_t modeBootDeadline=0;

void publishMode() {
    insert(QStringLiteral("radioMode"),int(radioMode.current));
    insert(QStringLiteral("radioModeBusy"),modeBoot || radioMode.busy());
    insert(QStringLiteral("radioModeVerified"),modeInitialized && radioMode.verified);
    if(radioMode.phase==RadioModePolicy::Failed || modeFailed)
        insert(QStringLiteral("radioModeError"),QStringLiteral("无线切换未完成，请重启后重试"));
}
void modeStartProcess(const QString &argument) {
    modeTicket=radioMode.transaction;
    modeProcess.start(QStringLiteral("/bin/sh"),QStringList()<<QStringLiteral("/opt/hbl-af-only-v1/radio-mode.sh")<<argument);
}
void modeApply(RadioModePolicy::Action action) {
    using P=RadioModePolicy;
    if(action==P::None) return;
    if(action==P::DisableFlash) {
        masterRequested=false;masterAcknowledged=false;
        insert(QStringLiteral("masterRequested"),false);insert(QStringLiteral("masterEnabled"),false);
        cancelPending(FORMAL_CANCELLED);
        if(connected)options();
    } else if(action==P::EnableFlash) {
        if(!connected){radioMode.phase=P::Failed;return;}
        masterRequested=true;masterAcknowledged=false;
        insert(QStringLiteral("masterRequested"),true);options();
    } else {
        modeStartProcess(QString::number(action==P::SetWifi?1:action==P::SetFlash?2:0));
    }
    publishMode();
}
void modeRequest(unsigned wanted) {
    if(!modeInitialized || modeFailed || !connected || restoreStage || modeBoot) return;
    insert(QStringLiteral("radioModeError"),QString());
    modeApply(radioMode.request(wanted,rf_monotonic_ms(),value(QStringLiteral("shotActive")).toBool()));
}
void modeReply(const FormalPacket &packet) {
    if(!modeInitialized || modeFailed || packet.sequence<optionsSequence) return;
    // worker 的 FV_BUSY 包含持有尚未释放和异步 close。
    modeApply(radioMode.stopped(radioMode.transaction,rf_monotonic_ms(),packet.values[FV_MASTER],false,packet.values[FV_BUSY]));
    radioMode.flashReady(radioMode.transaction,masterRequested && masterAcknowledged && packet.values[FV_MASTER] && packet.values[FV_READY]);
    publishMode();
}
void modeProcessDone(int code,QProcess::ExitStatus status) {
    const QByteArray answer=modeProcess.readAllStandardOutput().trimmed();
    const bool success=code==0 && status==QProcess::NormalExit;
    if(modeBoot) {
        modeBoot=false;
        if(success && (answer=="radio-mode-ready:0" || answer=="radio-mode-ready:1")) {
            radioMode.current=answer.endsWith('1')?RadioModePolicy::Wifi:RadioModePolicy::Off;
            radioMode.target=radioMode.current;radioMode.verified=true;modeInitialized=true;
        } else modeFailed=true;
    } else {
        const QByteArray expected="radio-mode-ready:"+QByteArray::number(int(radioMode.target));
        modeApply(radioMode.hardwareDone(modeTicket,rf_monotonic_ms(),success && answer==expected));
        if(radioMode.phase==RadioModePolicy::Failed)modeFailed=true;
    }
    publishMode();
}
void modeInitialize() {
    insert(QStringLiteral("radioMode"),0);insert(QStringLiteral("radioModeBusy"),true);
    insert(QStringLiteral("radioModeVerified"),false);insert(QStringLiteral("radioModeError"),QString());
    QProcessEnvironment env=QProcessEnvironment::systemEnvironment();
    env.remove(QStringLiteral("LD_PRELOAD"));
    modeProcess.setProcessEnvironment(env);modeProcess.setProcessChannelMode(QProcess::SeparateChannels);
    QObject::connect(&modeProcess,static_cast<void(QProcess::*)(int,QProcess::ExitStatus)>(&QProcess::finished),this,
        [this](int code,QProcess::ExitStatus status){modeProcessDone(code,status);});
    QObject::connect(&modeProcess,static_cast<void(QProcess::*)(QProcess::ProcessError)>(&QProcess::error),this,
        [this](QProcess::ProcessError error){if(error==QProcess::FailedToStart)modeProcessDone(-1,QProcess::CrashExit);});
}
void modeTick(uint64_t now) {
    if(!modeInitialized && !modeBoot && !modeFailed && connected && !restoreStage &&
       QFile::exists(QStringLiteral("/run/hbl-four-module/boot.ready"))) {
        modeBoot=true;modeBootDeadline=now+35000;modeStartProcess(QStringLiteral("boot"));publishMode();
    }
    if(modeBoot && now>=modeBootDeadline){modeFailed=true;modeBoot=false;modeProcess.kill();publishMode();}
    const auto action=radioMode.tick(now);
    if(action!=RadioModePolicy::None){modeFailed=true;modeProcess.kill();modeApply(action);publishMode();}
}
