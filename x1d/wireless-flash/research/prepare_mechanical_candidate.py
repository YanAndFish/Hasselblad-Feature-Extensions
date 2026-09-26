"""从已审查的传输骨架生成独立机械候选；不改电子快门源文件，不访问设备。"""
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]

def once(text,old,new):
    if text.count(old)!=1:
        raise RuntimeError('候选生成锚点不唯一: '+old[:80])
    return text.replace(old,new)

def prepare():
    assert Path.cwd().resolve()==HERE.parents[1]
    native=HERE/'native'
    bridge=(native/'rf_bridge.h').read_text(encoding='utf-8')
    bridge=bridge.replace('0x32425248','0x32424d48')
    bridge=bridge.replace('p->values[RV_DELAY]<=5000','p->values[RV_DELAY]<=5000000 && p->values[RV_DELAY]%10==0')
    bridge=bridge.replace('p->values[RV_SOURCE]<3','p->values[RV_SOURCE]<7')
    # 保持原头文件的 guard，先加载本候选后，原 socket helper 不再引入旧协议。
    (native/'mechanical_rf_bridge.h').write_text(bridge,encoding='utf-8')
    runtime=(native/'wireless_runtime.cpp').read_text(encoding='utf-8')
    runtime='#include "mechanical_rf_bridge.h"\n'+runtime
    runtime=runtime.replace('nextSource>=3','nextSource>=7').replace('delay=0,source=0,progress=0','delay=0,source=3,progress=0')
    runtime=runtime.replace('insert(QStringLiteral("source"),0)','insert(QStringLiteral("source"),3)')
    runtime=runtime.replace('nextDelay>5000','nextDelay>5000000 || nextDelay%10').replace('"delayMs"','"delayUs"')
    runtime=once(runtime,'            report(settings.isError() ? "qml-settings-failed" : "ui-loaded-worker-default-off");',
                 '            QQmlComponent flashPage(engine,QUrl(QStringLiteral("qrc:/controlscreen/MechanicalFlashPage.qml")));\n            QQmlComponent controlPage(engine,QUrl(QStringLiteral("qrc:/controlscreen/ControlScreen.qml")));\n            report(settings.isError() || flashPage.isError() || controlPage.isError() ? "qml-settings-failed" : "ui-loaded-worker-default-off");')
    (native/'mechanical_wireless_runtime.cpp').write_text(runtime,encoding='utf-8')
    worker=(native/'wireless_worker.cpp').read_text(encoding='utf-8')
    worker=worker.replace('#include "rf_core.h"','#include "mechanical_rf_core.h"\n#include "mechanical_rf_bridge.h"')
    worker=worker.replace('#include "rf_es_timing.h"\n','').replace('#include "farm_sync_wire.h"','#include "mechanical_sync_wire.h"')
    worker=worker.replace('HBL_SYNC_SOCKET','HBL_MECH_SOCKET').replace('HblFarmSync','HblMechanicalSync').replace('hbl_parse_sync_ipc','hbl_parse_mech_ipc').replace('sample.shot','sample.trial')
    start=worker.index('            const unsigned source=hbl_sync_source(sample.flags);')
    end=worker.index('\n        }\n    }\n    void receive()',start)
    worker=worker[:start]+'''            if (sample.trial<lastSyncShot) continue;
            const bool newTrial=sample.trial>lastSyncShot;
            if (newTrial) {
                cancelPending(QStringLiteral("新的采集请求撤销旧延迟"));
                mechanical_rf_begin(&core,sample.trial);
                lastSyncShot=sample.trial; syncPhases=0;
            }
            const unsigned events=(sample.clear_flags>>8)&HBL_MECH_EVENT_MASK;
            if (!newTrial && !(events&~syncPhases) && !(sample.clear_flags&HBL_MECH_DONE)) continue;
            syncPhases|=events;
            increment(RV_STARTS);
            QByteArray raw="trial="+QByteArray::number(sample.trial)+" flags="+QByteArray::number(sample.clear_flags,16)+
                " before="+QByteArray::number(sample.cleared_status,16)+" status="+QByteArray::number(sample.sync_status,16)+
                " timer_low="+QByteArray::number(sample.timer_low)+" timer_high="+QByteArray::number(sample.timer_high)+
                " timer_control="+QByteArray::number(sample.timer_control)+" mode="+QByteArray::number(sample.mode)+
                " arrival_ms="+QByteArray::number(at)+"\\n";
            mechanicalHistory.append(raw);
            if (mechanicalHistory.size()>128) mechanicalHistory.removeFirst();
            if (hbl_mech_confirmed(&sample,core.source)) increment(RV_ENDS);
            else increment(RV_READY_EVENTS);
            if (mechanical_rf_accept(&core,&sample,at,now,armedAt)) {
                increment(RV_QUEUED);
                if (core.deadline_ms>now) {
                    timer.start(int(core.deadline_ms-now));
                    message=QStringLiteral("本次信号已确认；等待 %1 ms").arg(core.delay_ms);
                } else due();
            } else if (!core.enabled) message=QStringLiteral("已记录 FPGA 状态；本次引闪关闭");
            else if (!core.consumed) message=QStringLiteral("已记录状态；等待本次所选信号");
            if (sample.clear_flags&HBL_MECH_DONE) {
                cancelPending(QStringLiteral("采集已结束；待发延迟已取消"));
                if (core.enabled) message=QStringLiteral("引闪保持开启；等待下一次拍摄");
            }
            changed();'''+worker[end:]
    worker=once(worker,'    QString message;','    QString message;\n    QList<QByteArray> mechanicalHistory;')
    worker=once(worker,'            syncEpoch=lastSyncShot=0;',
                '            syncEpoch=lastSyncShot=0; core.trial=0;')
    worker=once(worker,'                syncEpoch=epoch; lastSyncShot=sample.trial; continue;',
                '                core.trial=sample.trial;\n                syncEpoch=epoch; lastSyncShot=sample.trial; continue;')
    worker=once(worker,'            if (different) cancelPending(QStringLiteral("设置变化撤销待发引闪"));',
                '            const bool triggerChanged=core.enabled!=nextOn || core.source!=packet.values[RV_SOURCE] ||\n                                      core.delay_ms!=packet.values[RV_DELAY] || power!=int(packet.values[RV_POWER]);\n            if (triggerChanged) { armedAt=now; cancelPending(QStringLiteral("设置变化撤销待发引闪")); }')
    worker=once(worker,'                                 power!=int(packet.values[RV_POWER]) || page!=bool(packet.values[RV_PAGE]);',
                '                                 core.source!=packet.values[RV_SOURCE] || core.delay_ms!=packet.values[RV_DELAY] ||\n                                 power!=int(packet.values[RV_POWER]) || page!=bool(packet.values[RV_PAGE]);')
    worker=once(worker,'rf_configure(&core,nextOn,0,0);','rf_configure(&core,nextOn,packet.values[RV_SOURCE],packet.values[RV_DELAY]);')
    worker=once(worker,'increment(RV_CLICKS); cancelPending(QStringLiteral("单次试闪撤销待发延迟"));',
                'increment(RV_CLICKS); cancelPending(QStringLiteral("单次试闪撤销待发延迟"));')
    worker=worker.replace('已就绪；等待 FPGA 同步','已就绪；引闪保持开启').replace('已就绪；可单次试闪，自动关闭','已就绪；自动引闪关闭').replace('已提交一次引闪请求','已提交一次引闪请求；开关保持当前状态')
    worker=once(worker,'        data+="pending="+QByteArray::number(core.pending)+"\\n";',
                '        data+="pending="+QByteArray::number(core.pending)+"\\n";\n        QSaveFile history(QStringLiteral("/tmp/hbl-wireless-flash/mechanical-samples"));\n        if (history.open(QIODevice::WriteOnly)) { for (const auto &line:mechanicalHistory) history.write(line); history.commit(); }')
    worker=worker.replace('core.delay_ms','core.delay_us').replace('core.deadline_ms','core.deadline_us')
    worker=once(worker,'#include "mechanical_rf_core.h"','#include "mechanical_rf_core.h"\n#include "mechanical_deadline.h"')
    worker=once(worker,'QObject(parent),radio(this),bus(QDBusConnection::systemBus())','QObject(parent),radio(this),bus(QDBusConnection::systemBus()),timer(this)')
    worker=once(worker,'        rf_init(&core,1);','        rf_init(&core,1);\n        if (!timer.valid()) { record("worker-timerfd-failed"); return; }')
    worker=once(worker,'        timer.setSingleShot(true); timer.setTimerType(Qt::PreciseTimer);\n        QObject::connect(&timer,&QTimer::timeout,this,[this]() { due(); });',
                '        timer.expired=[this]() { due(); };\n        timer.failed=[this]() { disable(QStringLiteral("高分辨定时器读取失败")); };')
    worker=once(worker,'    QTimer timer,publishTimer,heartbeat;','    MechanicalDeadline timer;\n    QTimer publishTimer,heartbeat;')
    worker=once(worker,'rf_due(&core,rf_monotonic_ms())','rf_due(&core,mechanical_monotonic_us())')
    worker=once(worker,'const uint64_t now=rf_monotonic_ms(),at=arrival/1000000u;\n            if (!at || at>now || now-at>2000)',
                'const uint64_t now=mechanical_monotonic_us(),at=arrival/1000u;\n            if (!at || at>now || now-at>2000000)')
    worker=worker.replace('armedAt=now','armedAt=mechanical_monotonic_us()')
    worker=once(worker,'timer.start(int(core.deadline_us-now));',
                'if (!timer.start(core.deadline_us)) { disable(QStringLiteral("高分辨定时器设置失败")); continue; }')
    worker=worker.replace('等待 %1 ms','等待 %1 us').replace('arrival_ms=','arrival_us=')
    worker=once(worker,'    QString message;','    QString message,lastOffReason;')
    worker=once(worker,'    void disable(const QString &why) {','    void disable(const QString &why) {\n        if (core.enabled) lastOffReason=why;')
    worker=once(worker,'const QByteArray utf8=message.toUtf8();',
                'const QByteArray utf8=(!core.enabled && !lastOffReason.isEmpty() ? QStringLiteral("上次关闭：")+lastOffReason : message).toUtf8();')
    worker=once(worker,'        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/diagnostics"));',
                '        QSaveFile why(QStringLiteral("/tmp/hbl-wireless-flash/last-off-reason"));\n        if (why.open(QIODevice::WriteOnly)) { why.write(lastOffReason.toUtf8()); why.write("\\n"); why.commit(); }\n        QSaveFile file(QStringLiteral("/tmp/hbl-wireless-flash/diagnostics"));')
    worker=worker.replace('"on","delay","gain"','"on","delay_us","gain"')
    worker=once(worker,'    if (argc!=1) return 64;', '''    if (argc==2 && !std::strcmp(argv[1],"--check-timer")) {
        MechanicalDeadline check(&application);
        if (!check.valid()) return 23;
        unsigned count=0; uint64_t target=mechanical_monotonic_us()+10;
        check.failed=[&]() { application.exit(24); };
        check.expired=[&]() {
            if (mechanical_monotonic_us()<target) { application.exit(25); return; }
            if (++count==3) { std::puts("timerfd-check=3 units=us hardware-requests=0"); application.quit(); return; }
            target=mechanical_monotonic_us()+10;
            if (!check.start(target)) application.exit(26);
        };
        QTimer::singleShot(1000,&application,[&]() { application.exit(27); });
        if (!check.start(target)) return 26;
        return application.exec();
    }
    if (argc!=1) return 64;''')
    observer=(native/'farm_sync_observer.cpp').read_text(encoding='utf-8')
    replacements={'farm_sync_wire.h':'mechanical_sync_wire.h','HblFarmSync':'HblMechanicalSync',
                  'HBL_SYNC_SOCKET':'HBL_MECH_SOCKET','HBL_SYNC_MAGIC':'HBL_MECH_MAGIC',
                  'hbl_parse_sync_message':'hbl_parse_mech_message','hbl_pack_sync_ipc':'hbl_pack_mech_ipc',
                  'hbl_sync_u32':'hbl_mech_u32','sample.shot':'sample.trial',
                  'HBL_FARM_SYNC':'HBL_MECHANICAL_SYNC','sync-observer.status':'mechanical-observer.status',
                  'GFS1':'GMS1','hbl_farm_sync_test_status':'hbl_mechanical_sync_test_status'}
    for old,new in replacements.items(): observer=observer.replace(old,new)
    from prepare_mechanical_fastpath import prepare as fastpath
    worker,observer=fastpath(worker,observer)
    (native/'mechanical_wireless_worker.cpp').write_text(worker,encoding='utf-8')
    (native/'mechanical_sync_observer.cpp').write_text(observer,encoding='utf-8')
    check=(native/'farm_sync_hook_check.cpp').read_text(encoding='utf-8')
    for old,new in replacements.items(): check=check.replace(old,new)
    check=check.replace('hbl_sync_put32','hbl_mech_put32')
    check=once(check,'HblMechanicalSync sample={HBL_MECH_MAGIC,3,7,7,0x3334,0x3734,100,7,1,250000,0};',
               'HblMechanicalSync sample={HBL_MECH_MAGIC,1,7,0x0f07,0x3001,0x3c04,100,7,1,0,3};')
    check=once(check,'{uint32_t(7),uint32_t(5),uint32_t(4),uint32_t(0x107),uint32_t(0x207)}',
               '{uint32_t(7),uint32_t(5),uint32_t(4),uint32_t(0x0f07),uint32_t(0x8007)}')
    (native/'mechanical_sync_hook_check.cpp').write_text(check,encoding='utf-8')
    main=(HERE/'ui/main_additions.qml.inc').read_text(encoding='utf-8')
    main=once(main,'        source = 0; delay = 0; progress = 0;',
              '        source = source === undefined ? hblRfSource : source;\n        delay = delay === undefined ? hblRfDelayMs : delay;\n        progress = 0;')
    main=main.replace('hblNative.source : 0','hblNative.source : 3')
    main=once(main,'    property int hblRfStepMs: 10',
              '    property int hblRfStepMs: 1\n    property var hblRfSourceDelays: [0,0,0,0,0,0,0]\n    function hblRfSelectSource(source) {\n        hblRfConfigure(hblRfEnabled,hblRfSourceDelays[source],source);\n    }\n    function hblRfAdjustDelay(delay) {\n        delay=Math.max(0,Math.min(5000,delay));\n        var next=hblRfSourceDelays.slice(0); next[hblRfSource]=delay; hblRfSourceDelays=next;\n        hblRfConfigure(hblRfEnabled,delay,hblRfSource);\n    }')
    main=main.replace('hblRfDelayMs','hblRfDelayUs').replace('hblRfStepMs','hblRfStepUs').replace('hblNative.delayMs','hblNative.delayUs')
    main=main.replace('property int hblRfStepUs: 1','property int hblRfStepUs: 10')
    main=main.replace('delay=Math.max(0,Math.min(5000,delay));','delay=Math.max(0,Math.min(5000000,Math.round(delay/10)*10));')
    (HERE/'ui/mechanical_main_additions.qml.inc').write_text(main,encoding='utf-8')
    settings=(HERE/'ui/settings_additions.qml.inc').read_text(encoding='utf-8')
    settings=settings.replace('电子快门引闪（临时）','机械快门 · FPGA 试验').replace('电子快门 · 自动引闪','FPGA 信号试验')
    settings=settings.replace('text: "自动引闪：" + (mainRoot.hblRfEnabled ? "开" : "关")',
                              'text: "自动引闪：" + (mainRoot.hblRfEnabled ? "开 · 点击关闭" : "关 · 点击开启")')
    settings=settings.replace('onClicked: mainRoot.hblRfConfigure(!mainRoot.hblRfEnabled, mainRoot.hblRfDelayMs)',
                              'onClicked: { if (mainRoot.hblRfEnabled || (mainRoot.hblRfReady && !mainRoot.hblRfBusy)) mainRoot.hblRfConfigure(!mainRoot.hblRfEnabled, mainRoot.hblRfDelayMs) }')
    a=settings.index('            Text {\n                width: parent.width; wrapMode: Text.WordWrap\n                text: "按本次快门')
    b=settings.index('            Text {\n                text: "无线发射功率',a)
    settings=settings[:a]+'''            Text {
                text: "触发信号 · 开启后每拍最多一次"
                color: "white"; font.pixelSize: 21 * hblRfPanel.unit
            }
            Grid {
                columns: 2; spacing: 8 * hblRfPanel.unit
                Repeater {
                    model: ["A 路首次同步", "B 路首次同步", "启动保持置位", "退出空闲", "状态 1 置位", "状态 3 置位", "返回空闲"]
                    delegate: Rectangle {
                        width: (hblRfContent.width - 8*hblRfPanel.unit)/2
                        height: 52*hblRfPanel.unit; radius: 4
                        color: mainRoot.hblRfSource===index ? "#805829" : "#303030"
                        Text { anchors.centerIn: parent; text: modelData; color: "white"; font.pixelSize: 20*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfSelectSource(index) }
                    }
                }
            }
            Text {
                text: "本信号延迟：" + mainRoot.hblRfDelayMs + " ms"
                color: "#E3A156"; font.pixelSize: 22*hblRfPanel.unit
            }
            Row {
                spacing: 8*hblRfPanel.unit
                Repeater {
                    model: ["−"+mainRoot.hblRfStepMs, "归零", "+"+mainRoot.hblRfStepMs]
                    delegate: Rectangle {
                        width: (hblRfContent.width-16*hblRfPanel.unit)/3; height: 52*hblRfPanel.unit
                        color: "#303030"; radius: 4
                        Text { anchors.centerIn: parent; text: modelData; color: "white"; font.pixelSize: 22*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfAdjustDelay(index===1 ? 0 : mainRoot.hblRfDelayMs+(index===0 ? -1:1)*mainRoot.hblRfStepMs) }
                    }
                }
            }
            Row {
                spacing: 8*hblRfPanel.unit
                Repeater {
                    model: [1,10,100]
                    delegate: Rectangle {
                        width: (hblRfContent.width-16*hblRfPanel.unit)/3; height: 44*hblRfPanel.unit
                        color: mainRoot.hblRfStepMs===modelData ? "#68451D" : "#242424"
                        Text { anchors.centerIn: parent; text: "步长 "+modelData+" ms"; color: "white"; font.pixelSize: 18*hblRfPanel.unit }
                        MouseArea { anchors.fill: parent; onClicked: mainRoot.hblRfStepMs=modelData }
                    }
                }
            }
            Text {
                width: parent.width; wrapMode: Text.WordWrap
                text: "开启一次即可连续测试；切换信号和延迟保持开启，下次拍摄生效。每项延迟单独保留。\\n状态 1、3 的物理含义待确认；未读到变化则跳过本次。"
                color: "#BBBBBB"; font.pixelSize: 17*hblRfPanel.unit
            }
'''+settings[b:]
    settings=settings.replace('hblRfDelayMs','hblRfDelayUs').replace('hblRfStepMs','hblRfStepUs')
    settings=settings.replace('mainRoot.hblRfDelayUs + " ms"','(mainRoot.hblRfDelayUs/1000).toFixed(2) + " ms"')
    settings=settings.replace('model: [1,10,100]','model: [10,100,1000]').replace('modelData+" ms"','modelData+" us"')
    from prepare_mechanical_dispatch import settings_without_statistics
    settings=settings_without_statistics(settings)
    (HERE/'ui/mechanical_settings_additions.qml.inc').write_text(settings,encoding='utf-8')
    return {'generated':7,'hardware_requests':0}

if __name__=='__main__': print(prepare())
