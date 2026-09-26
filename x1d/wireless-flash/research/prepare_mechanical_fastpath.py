"""机械候选的拍前准备与触发路径优化；导入不访问相机。"""
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]

def once(text,old,new):
    if text.count(old)!=1: raise RuntimeError('Fast path anchor mismatch: '+old[:100])
    return text.replace(old,new)

def prepare(worker,observer):
    native=HERE/'native'
    channel=(native/'netlink_radio.h').read_text(encoding='utf-8')
    channel=once(channel,'#include "rf_netlink_wire.h"','#include "mechanical_prepared_request.h"')
    channel=once(channel,'        return send(Fire);','''        if (!mechanical_consume_request(preparedRequest,sequence)) {
            closeChannel(); error=QStringLiteral("预编码发射请求已失效"); return false;
        }
        sequence=preparedRequest->sequence;
        if (sendto(fd,preparedRequest->bytes,preparedRequest->size,MSG_DONTWAIT,
                   reinterpret_cast<sockaddr *>(&preparedPeer),sizeof(preparedPeer))!=ssize_t(preparedRequest->size)) {
            closeChannel(); error=QStringLiteral("驱动请求未提交"); return false;
        }
        operation=Fire; watchdog.start(1000); return true;''')
    channel=once(channel,'    QTimer watchdog;','''    QTimer watchdog;
    MechanicalPreparedRequest requestStorage={};
    MechanicalPreparedRequest *preparedRequest=&requestStorage;
    sockaddr_nl preparedPeer={};
    bool prepareNextRequest() {
        preparedPeer.nl_family=AF_NETLINK;
        if (mechanical_prepare_request(preparedRequest,family,sequence,port,ifindex)) return true;
        error=QStringLiteral("无法预编码下一次发射请求"); closeChannel(); return false;
    }''')
    channel=once(channel,'        watchdog.stop(); operation=None; ready=false; family=0;',
                 '        watchdog.stop(); operation=None; ready=false; family=0; preparedRequest->ready=0;')
    channel=once(channel,'            if (prepared) prepared(ready);',
                 '            if (ready) ready=prepareNextRequest();\n            if (prepared) prepared(ready);')
    channel=once(channel,'            if (fired) fired(ready);',
                 '            if (ready) ready=prepareNextRequest();\n            if (fired) fired(ready);')
    channel=once(channel,'    void invalidate() { ready=false; }','    void invalidate() { ready=false; preparedRequest->ready=0; }')
    (native/'mechanical_netlink_radio.h').write_text(channel,encoding='utf-8')
    radio=(native/'prepared_radio.h').read_text(encoding='utf-8')
    radio=once(radio,'#include "netlink_radio.h"','#include "mechanical_netlink_radio.h"')
    radio=once(radio,'        operation=Firing; ready=false; errorStep.clear();','        operation=Firing; ready=false;')
    (native/'mechanical_prepared_radio.h').write_text(radio,encoding='utf-8')
    worker=once(worker,'#include "prepared_radio.h"','#include "mechanical_prepared_radio.h"')
    start=worker.index('            QByteArray raw="trial="')
    end=worker.index('            if (hbl_mech_confirmed',start)
    formatting=worker[start:end]
    worker=worker[:start]+worker[end:]
    worker=once(worker,'    QList<QByteArray> mechanicalHistory;', '''    struct RawSample { HblMechanicalSync sample; uint64_t at; };
    RawSample mechanicalHistory[128]={};
    unsigned historyNext=0,historyCount=0;
    uint64_t lastDiagnosticsUs=0;''')
    worker=once(worker,'            if (sample.clear_flags&HBL_MECH_DONE) {','''            mechanicalHistory[historyNext]={sample,at};
            historyNext=(historyNext+1)%128;
            if (historyCount<128) ++historyCount;
            if (sample.clear_flags&HBL_MECH_DONE) {''')
    worker=once(worker,'        rf_cancel(&core); timer.stop();',
                '        if (core.pending) timer.stop();\n        rf_cancel(&core);')
    worker=once(worker,'                    message=QStringLiteral("本次信号已确认；等待 %1 us").arg(core.delay_us);',
                '                    message=QStringLiteral("本次信号已确认；等待预设延迟");')
    worker=once(worker,'        const char *labels[]={', '''        // 界面心跳始终回复；待发截止点期间不格式化或写入诊断。
        const uint64_t diagnosticNow=mechanical_monotonic_us();
        if (core.pending || (lastDiagnosticsUs && diagnosticNow-lastDiagnosticsUs<250000)) return;
        lastDiagnosticsUs=diagnosticNow;
        const char *labels[]={''')
    old='        if (history.open(QIODevice::WriteOnly)) { for (const auto &line:mechanicalHistory) history.write(line); history.commit(); }'
    fields=formatting[:formatting.index('            mechanicalHistory.append(raw);')]
    worker=once(worker,old,'''        if (history.open(QIODevice::WriteOnly)) {
            for (unsigned i=0;i<historyCount;++i) {
                const RawSample &entry=mechanicalHistory[(historyNext+128-historyCount+i)%128];
                const HblMechanicalSync &sample=entry.sample; const uint64_t at=entry.at;
'''+fields+'''                history.write(raw);
            }
            history.commit();
        }''')
    # 正常采样不统计、不写文件；仅初始化与故障保留就绪反馈。
    observer=once(observer,'    } else health("forwarded");',
                  '    }')
    observer=once(observer,'''    if (!__atomic_load_n(&outputEnabled,__ATOMIC_ACQUIRE)) return;
    __atomic_add_fetch(&acceptedCount,1,__ATOMIC_RELAXED);
    __atomic_store_n(&lastShot,sample.trial,__ATOMIC_RELAXED);''',
                  '    if (!__atomic_load_n(&outputEnabled,__ATOMIC_ACQUIRE)) return;')
    from prepare_mechanical_dispatch import prepare as dispatch
    return dispatch(worker),observer
