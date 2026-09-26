"""固定新版中断消息接收端；两来源、无处理方式切换，保留原无线发送实现。"""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
BASE=HERE/'build/mechanical-options-candidate'
OUT=HERE/'build/mechanical-irq-candidate'


def once(text,old,new):
    if text.count(old)!=1: raise ValueError('接收端基线锚点不匹配: '+old[:80])
    return text.replace(old,new)


def remove_between(text,start,end):
    first=text.index(start); last=text.index(end,first)
    return text[:first]+text[last:]


def build():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('工作区不匹配')
    OUT.mkdir(exist_ok=True)
    baseline=json.loads((BASE/'client-build.json').read_text(encoding='utf-8'))
    for name,digest in baseline['sourceHashes'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('原双开关基线被修改: '+name)
    files={p.name:p.read_text(encoding='utf-8') for p in BASE.glob('options_*.h')}
    for name in ('options_worker.cpp','options_observer.cpp','options_runtime.cpp'):
        files[name]=(BASE/name).read_text(encoding='utf-8')
    core=(HERE/'native/mechanical_rf_core.h').read_text(encoding='utf-8')
    core=once(core,'"mechanical_sync_wire.h"','"mechanical_irq_wire.h"')
    core=once(core,'source>=HBL_MECH_SOURCES','(source!=2 && source!=3)')
    files['irq_rf_core.h']=core
    files['options_prepared_request.h']=once(files['options_prepared_request.h'],
                                            '"rf_netlink_wire.h"','"options_netlink_wire.h"')
    w=files['options_worker.cpp'].replace('"mechanical_rf_core.h"','"irq_rf_core.h"').replace('"mechanical_sync_wire.h"','"mechanical_irq_wire.h"')
    w=once(w,'HblMechanicalSync sample={HBL_MECH_MAGIC,1,1,','HblMechanicalSync sample={HBL_MECH_MAGIC,2,1,')
    # 检查结束消息不与触发事件混发。
    w=once(w,'sample.clear_flags|=HBL_MECH_DONE;','sample.clear_flags=HBL_MECH_CLOCK|HBL_MECH_DONE;')
    w=once(w,'sample.trial=3; sample.clear_flags&=~HBL_MECH_DONE;','sample.trial=3; sample.clear_flags=HBL_MECH_CLOCK|(1u<<11);')
    files['options_worker.cpp']=w
    bridge=files['options_rf_bridge.h']
    bridge=bridge.replace('p->version=3','p->version=4').replace('p->version!=3','p->version!=4')
    bridge=once(bridge,'p->values[RV_SOURCE]<7','(p->values[RV_SOURCE]==2 || p->values[RV_SOURCE]==3)')
    bridge=once(bridge,'p->values[RV_SAME_PROCESS]<=1','p->values[RV_SAME_PROCESS]==0')
    files['options_rf_bridge.h']=bridge
    observer=files['options_observer.cpp'].replace('"mechanical_sync_wire.h"','"mechanical_irq_wire.h"')
    observer=once(observer,'static bool selfTest,observeEnabled,sameProcess;','static bool selfTest,observeEnabled;')
    observer=remove_between(observer,'extern "C" bool hbl_options_begin();','static int outputFd=-1;')
    observer=once(observer,'    sameProcess=selectedSameProcess();\n    if (sameProcess) return;\n','')
    observer=remove_between(observer,'    if (sameProcess) {','    uint8_t packet[64];')
    observer=observer[:observer.index('\nextern "C" int hbl_options_exec()')]+ '\n'
    files['options_observer.cpp']=observer
    r=files['options_runtime.cpp'].replace('#include <QtCore/qprocess.h>\n','')
    r=once(r,'insert(QStringLiteral("perShot"),false); insert(QStringLiteral("sameProcess"),false);','insert(QStringLiteral("perShot"),false);')
    r=remove_between(r,'        QProcessEnvironment env=','        insert(QStringLiteral("enabled"),false);')
    r=once(r,'            if (switching) return;\n','')
    r=remove_between(r,'            if (desiredProcess>=0 && now-switchRequestedAt>5000) {','            if (connected &&')
    r=once(r,'        if (switching || desiredProcess>=0) return QVariant();\n','')
    r=remove_between(r,'        if (command.startsWith(QStringLiteral("process "))) {','        if (command.startsWith(QStringLiteral("pershot "))) {')
    r=once(r,'nextSource>=7','(nextSource!=2 && nextSource!=3)')
    r=remove_between(r,'    QProcess switcher;','    void status(')
    r=once(r,'    void status(','    uint32_t perShot=0;\n    void status(')
    r=once(r,'packet.values[RV_SAME_PROCESS]=sameProcess;','packet.values[RV_SAME_PROCESS]=0;')
    r=remove_between(r,'            if (first && restoreSettings) {','            if (packet.sequence==revision) {')
    r=once(r,'perShot=packet.values[RV_PER_SHOT]; sameProcess=packet.values[RV_SAME_PROCESS];','perShot=packet.values[RV_PER_SHOT];')
    r=once(r,'insert(QStringLiteral("perShot"),bool(perShot)); insert(QStringLiteral("sameProcess"),bool(sameProcess));','insert(QStringLiteral("perShot"),bool(perShot));')
    r=remove_between(r,'            if (desiredProcess>=0 && packet.sequence==revision','            if (first && page)')
    assert all(word not in r for word in ('sameProcess','switcher','desiredProcess','QProcess','switch-process.sh'))
    files['options_runtime.cpp']=r
    check=(HERE/'native/mechanical_sync_hook_check.cpp').read_text(encoding='utf-8').replace('"mechanical_sync_wire.h"','"mechanical_irq_wire.h"')
    check=once(check,'HblMechanicalSync sample={HBL_MECH_MAGIC,1,7,0x0f07,0x3001,0x3c04,100,7,1,0,3};',
               'HblMechanicalSync sample={HBL_MECH_MAGIC,2,7,0x0c04,1,4,100,7,1,0,3};')
    check=once(check,'{uint32_t(7),uint32_t(5),uint32_t(4),uint32_t(0x0f07),uint32_t(0x8007)}',
               '{uint32_t(0),uint32_t(4),uint32_t(0x0404),uint32_t(0x0804),uint32_t(0x8004)}')
    files['irq_hook_check.cpp']=check
    for name,text in files.items(): (OUT/name).write_text(text,encoding='utf-8')
    # 使用既有 ARM/Qt 构建器，去掉同进程 worker 变体；不生成/替换无线固件。
    source=(HERE/'research/build_mechanical_options.py').read_text(encoding='utf-8')
    source=once(source,"\nOUT=HERE/'build/mechanical-options-candidate'\n","\nOUT=HERE/'build/mechanical-irq-candidate'\n")
    source=once(source,"('embedded','options_worker.cpp',['-DHBL_OPTIONS_EMBEDDED=1']),",'')
    source=once(source,"('runtime','options_runtime.cpp',[])","('runtime','options_runtime.cpp',[]),('hook','irq_hook_check.cpp',[])")
    source=once(source,"['embedded','observer']","['observer']")
    source=once(source,"('libhbl-wireless.so',['runtime'],True)","('libhbl-wireless.so',['runtime'],True),('sync-hook-check',['hook'],False)")
    source=once(source,"'-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout)","'-Wl,--no-undefined','-Wl,--export-dynamic','-Wl,-s','-Wl,-T,'+str(layout)")
    namespace={'__file__':str(HERE/'research/build_mechanical_options.py'),'__name__':'irq_client_builder'}
    exec(compile(source,namespace['__file__'],'exec'),namespace)
    outputs=namespace['compile_clients']()
    report=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    report.update(messageVersion=2,uiBridgeVersion=4,availableSources=[2,3],processSwitchRemoved=True,
                  fixedProcessMode='separate-worker',targetRuntimeChecked=False)
    for path in (Path(__file__),HERE/'native/mechanical_irq_wire.h',HERE/'native/mechanical_rf_core.h'):
        report['sourceHashes'][str(path.relative_to(HERE))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT/'client-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return outputs


if __name__=='__main__': print(json.dumps(build()))
