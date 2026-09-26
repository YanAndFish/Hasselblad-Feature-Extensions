"""从已实装七节点／三开关基线生成专用定时发送线程版；仅在电脑构建。"""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
BASE = HERE / 'build/mechanical-options-candidate'
OUT = HERE / 'build/mechanical-direct-candidate'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('Direct candidate anchor: ' + before[:100])
    return text.replace(before, after)


def sources():
    report = json.loads((BASE / 'client-build.json').read_text(encoding='utf-8'))
    for name, expected in report['sourceHashes'].items():
        if sha((HERE / name).read_bytes()) != expected:
            raise RuntimeError('Installed baseline source changed: ' + name)
    for path in list(BASE.glob('options_*.h')) + list(BASE.glob('options_*.cpp')):
        (OUT / path.name).write_bytes(path.read_bytes())

    text = (BASE / 'options_netlink_radio.h').read_text(encoding='utf-8')
    text = once(text, '#include "options_netlink_wire.h"',
                '#include "options_netlink_wire.h"\n#include "mechanical_direct_dispatch.h"')
    text = once(text, '        watchdog.setSingleShot(true);', '''        if (dispatch.valid()) {
            dispatchNotifier=new QSocketNotifier(dispatch.completionFd(),QSocketNotifier::Read,this);
            QObject::connect(dispatchNotifier,&QSocketNotifier::activated,this,[this](int) {
                finishDispatch(dispatch.take());
            });
        }
        watchdog.setSingleShot(true);''')
    text = once(text, '    ~NetlinkRadio() override { closeChannel(); }', '''    ~NetlinkRadio() override { closeChannel(); delete dispatchNotifier; }
    bool valid() const { return dispatch.valid(); }''')
    text = once(text, '        if (mode>1) return false;',
                '        if (mode>1 || !dispatch.valid()) return false;')
    start = text.index('    bool fire() {')
    end = text.index('    void invalidate()', start)
    text = text[:start] + '''    bool fire(uint64_t deadline=0) {
        if (!ready || operation!=None || fd<0 || !dispatch.valid()) return false;
        ready=false;
        if (!mechanical_consume_request(preparedRequest,sequence)) {
            closeChannel(); error=QStringLiteral("预编码发射请求已失效"); return false;
        }
        sequence=preparedRequest->sequence;
        if (!deadline) deadline=mechanical_monotonic_us();
        // 暂不读驱动回复：发送线程完成提交后再恢复，避免回复先于发送返回的竞态。
        operation=Fire;
        notifier->setEnabled(false);
        if (!dispatch.schedule(fd,preparedRequest->bytes,preparedRequest->size,
                               reinterpret_cast<const sockaddr *>(&preparedPeer),sizeof(preparedPeer),deadline)) {
            closeChannel(); error=QStringLiteral("专用触发线程未接受截止点"); return false;
        }
        return true;
    }
    MechanicalDirectDispatch::Result cancelPending() {
        const auto state=dispatch.cancel();
        if (state==MechanicalDirectDispatch::Cancelled) {
            operation=None; watchdog.stop(); ready=prepareNextRequest();
            if (notifier) notifier->setEnabled(true);
            if (!ready) { error=QStringLiteral("取消后预编码请求失效"); closeChannel(); return MechanicalDirectDispatch::Failed; }
        } else if (state==MechanicalDirectDispatch::Submitted) {
            finishDispatch(state);
        } else if (state==MechanicalDirectDispatch::Failed) {
            error=QStringLiteral("专用触发线程提交失败"); closeChannel();
        }
        return state;
    }
''' + text[end:]
    text = once(text, '    QTimer watchdog;', '''    QTimer watchdog;
    MechanicalDirectDispatch dispatch;
    QSocketNotifier *dispatchNotifier=nullptr;
    void finishDispatch(MechanicalDirectDispatch::Result state) {
        if (state==MechanicalDirectDispatch::Empty || operation!=Fire) return;
        if (state!=MechanicalDirectDispatch::Submitted) {
            fail(QStringLiteral("专用触发线程提交失败")); return;
        }
        if (notifier) notifier->setEnabled(true);
        watchdog.start(1000);
    }''')
    text = once(text, '    void closeChannel() {',
                '    void closeChannel() {\n        dispatch.cancel();')
    (OUT / 'options_netlink_radio.h').write_text(text, encoding='utf-8')

    text = (BASE / 'options_radio.h').read_text(encoding='utf-8')
    text = once(text, '        completed=nullptr; prepared=nullptr; changed=nullptr;',
                '        completed=nullptr; prepared=nullptr; changed=nullptr;\n        channel.cancelPending();')
    text = once(text, '    bool fire(int power,unsigned mode) {', '''    bool valid() const { return channel.valid(); }
    void cancelPendingDispatch() {
        const auto state=channel.cancelPending();
        if (state==MechanicalDirectDispatch::Cancelled && operation==Firing) {
            operation=Idle;
            ready=wanted && held && desiredPower==preparedPower && desiredMode==preparedMode;
            publish(); later();
        } else if (state==MechanicalDirectDispatch::Failed) {
            fail(channel.error,true);
        }
    }
    bool fire(int power,unsigned mode,uint64_t deadline=0) {''')
    text = once(text, 'if (!channel.fire())', 'if (!channel.fire(deadline))')
    text = once(text, '        wanted=false; ready=false;\n        publish(); reconcile();',
                '        wanted=false; ready=false;\n        cancelPendingDispatch();\n        publish(); reconcile();')
    (OUT / 'options_radio.h').write_text(text, encoding='utf-8')

    text = (BASE / 'options_worker.cpp').read_text(encoding='utf-8')
    text = once(text, ',timer(this) {', ' {')
    text = once(text, 'valid=timer.valid();', 'valid=radio.valid();')
    text = once(text, 'if (!timer.valid()) { record("worker-timerfd-failed"); return; }',
                'if (!radio.valid()) { record("worker-direct-thread-failed"); return; }')
    text = once(text, '        timer.expired=[this]() { due(); };\n        timer.failed=[this]() { disable(QStringLiteral("高分辨定时器读取失败")); };\n', '')
    start = text.index('        radio.timing=')
    end = text.index('        radio.changed=', start)
    text = text[:start] + text[end:]
    text = once(text, '        radio.completed=[this](bool /*sent*/,bool ok) {',
                '        radio.completed=[this](bool /*sent*/,bool ok) {\n            core.pending=0;')
    text = once(text, '    MechanicalDeadline timer;\n', '')
    start = text.index('    HblTimingRing timingRing={};')
    end = text.index('    void refreshSourcePid()', start)
    text = text[:start] + text[end:]
    # 本版没有时序采样、记录环或采样文件。功能状态与错误反馈仍保留。
    text = re.sub(r'^.*\brecordTiming\([^\n]*\);\r?\n', '', text, flags=re.MULTILINE)
    text = text.replace('                timingActive=true;\n', '').replace('            if (nextOn) timingActive=true;\n', '')
    text = once(text, '        timingDispatch=timingEvent(0,0);\n', '')
    text = once(text, '        flushTiming();\n', '')
    text = once(text, '        if (core.pending) timer.stop();',
                '        if (core.pending) radio.cancelPendingDispatch();')
    text = once(text, '    void transmit() {', '    void transmit(uint64_t deadline=0) {')
    text = once(text, 'radio.fire(power,perShot)', 'radio.fire(power,perShot,deadline)')
    start = text.index('    void due() {')
    end = text.index('    void receiveSync()', start)
    text = text[:start] + text[end:]
    text = once(text, '''                if (core.deadline_us>now) {
                    if (!timer.start(core.deadline_us)) { disable(QStringLiteral("高分辨定时器设置失败")); return; }
                    message=QStringLiteral("本次信号已确认；等待预设延迟");
                } else due();''', '''                if (!testOnly) transmit(core.deadline_us);''')
    text = once(text, '#include "mechanical_deadline.h"',
                '#include "mechanical_deadline.h"\n#include "mechanical_direct_check.h"')
    text = once(text, '    if (argc==2 && !std::strcmp(argv[1],"--check-options")) {', '''    if (argc==2 && !std::strcmp(argv[1],"--check-direct")) return mechanical_direct_check();
    if (argc==2 && !std::strcmp(argv[1],"--check-options")) {''')
    for forbidden in ('timer.start(core.deadline_us)', 'timingActive', 'recordTiming(', 'timing.bin', 'HblTimingRing'):
        if forbidden in text:
            raise RuntimeError('Old timed-dispatch/recording path retained: ' + forbidden)
    (OUT / 'options_worker.cpp').write_text(text, encoding='utf-8')


def compile_clients():
    source = HERE / 'research/build_mechanical_options.py'
    code = source.read_text(encoding='utf-8')
    code = once(code, "\nOUT=HERE/'build/mechanical-options-candidate'\n", "\nOUT=HERE/'build/mechanical-direct-candidate'\n")
    code = once(code, "'lib/libdl-2.22.so','lib/libc-2.22.so'", "'lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so'")
    scope = {'__file__': str(source), '__name__': 'direct_build_compiler'}
    exec(compile(code, str(source), 'exec'), scope)
    outputs = scope['compile_clients']()
    report = json.loads((OUT / 'client-build.json').read_text(encoding='utf-8'))
    for path in (Path(__file__), HERE / 'native/mechanical_direct_dispatch.h', HERE / 'native/mechanical_direct_check.h'):
        report['sourceHashes'][str(path.relative_to(HERE))] = sha(path.read_bytes())
    report.update(baseline='mechanical-options-candidate', dedicatedThread=True, schedulingPolicy='SCHED_FIFO',
                  schedulingPriority=1, waitsForQtBeforeSubmit=False, timingSamplesAdded=False,
                  firmwareModified=False, farmModified=False, fpgaModified=False)
    (OUT / 'client-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return outputs


def build():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Workspace mismatch')
    OUT.mkdir(exist_ok=True)
    sources()
    return compile_clients()


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
