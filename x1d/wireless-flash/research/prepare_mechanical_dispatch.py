"""移除机械候选的持续诊断；只保留控制状态、一次资格与故障反馈。"""
import re


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Dispatch anchor mismatch: ' + old[:100])
    return text.replace(old, new)


def prepare(worker):
    start = worker.index('    struct RawSample {')
    end = worker.index('    void increment(', start)
    worker = worker[:start] + worker[end:]
    worker = once(worker, '''            mechanicalHistory[historyNext]={sample,at};
            historyNext=(historyNext+1)%128;
            if (historyCount<128) ++historyCount;
''', '')
    worker = once(worker, '''            if (hbl_mech_confirmed(&sample,core.source)) increment(RV_ENDS);
            else increment(RV_READY_EVENTS);
''', '')
    worker = once(worker, '            if (sent) increment(RV_SENT);\n', '')
    worker = once(worker, 'radio.completed=[this](bool sent,bool ok)',
                  'radio.completed=[this](bool /*sent*/,bool ok)')
    worker = once(worker, '    uint32_t counters[RV_COUNT]={};\n', '')
    worker = once(worker, '    void increment(unsigned index) { if (counters[index]<INT32_MAX) ++counters[index]; }\n', '')
    worker = once(worker, '        memcpy(packet.values,counters,sizeof(counters));\n', '')
    worker = re.sub(r'increment\(RV_[A-Z_]+\); ?', '', worker)
    worker = once(worker, '''            } else if (!core.enabled) message=QStringLiteral("已记录 FPGA 状态；本次引闪关闭");
            else if (!core.consumed) message=QStringLiteral("已记录状态；等待本次所选信号");''', '            }')
    worker = once(worker, '    void publish() {\n        RfBridgePacket packet;', '''    void publish() {
        // 临近发射截止点时，界面状态序列化延后；不改变发射或故障保护。
        if (mechanical_defer_status(&core,mechanical_monotonic_us())) { changed(); return; }
        RfBridgePacket packet;''')
    start = worker.index('        // 界面心跳始终回复；')
    end = worker.index('\n    }\n};\n}', start)
    worker = worker[:start] + worker[end:]
    worker = worker.replace('Radio 在回调或诊断输出前', 'Radio 在界面回调前')
    # 统计槽位仍由协议初始化清零，旧界面协议布局保持兼容。
    forbidden = ('mechanicalHistory', 'QByteArray::number', 'diagnostics',
                 'mechanical-samples', 'last-off-reason', 'increment(', 'counters[')
    if any(item in worker for item in forbidden):
        raise RuntimeError('Persistent diagnostics remain in worker')
    return worker


def settings_without_statistics(settings):
    settings = once(settings, 'text: "CH 5 · ID 5 · D 组    按键收到 " + mainRoot.hblRfCount("manualClicks") + " 次"',
                    'text: "CH 5 · ID 5 · D 组"')
    start = settings.index('            Text {\n                width: parent.width; wrapMode: Text.WordWrap\n                text: "同步记录 "')
    end = settings.index('\n            }', start) + len('\n            }')
    settings = settings[:start] + settings[end:]
    start = settings.index('                Text {\n                    anchors.horizontalCenter: parent.horizontalCenter\n                    text: "按键收到 "')
    end = settings.index('\n                }', start) + len('\n                }')
    settings = settings[:start] + settings[end:]
    if 'hblRfCount(' in settings:
        raise RuntimeError('Statistics remain in mechanical settings')
    return settings
