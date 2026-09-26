"""三状态候选：固定已装源码增量生成，不执行相机操作。"""
from pathlib import Path
import hashlib, importlib.util, json, os, subprocess, sys
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
O=P/'build/radio-three-state';O.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(P.parent),str(ROOT/'x1d/candidates/ui-resident/tools')]
from compose import read_rcc
from resource_bundle import rcc

def replace(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def sources():
    src=P/'build/halfpress-ui/gui'
    out=O/'gui';out.mkdir(exist_ok=True)
    for n in ['readiness.h','gate_policy.h','catalog.h']:
        (out/n).write_bytes((src/n).read_bytes())
    s=(src/'runtime.cpp').read_text(encoding='utf-8')
    s='#include <QtCore/qprocess.h>\n#include "radio_mode_policy.h"\n'+s
    s=replace(s,'private:\n','private:\n#include "radio_mode_runtime.inc"\n')
    s=replace(s,'        timer.start();','        modeInitialize();\n        timer.start();')
    s=replace(s,'            const uint64_t now=rf_monotonic_ms();\n            updateHold();','            const uint64_t now=rf_monotonic_ms();\n            updateHold();\n            modeTick(now);')
    s=replace(s,'        if(op==QStringLiteral("options")) {','''        if(op==QStringLiteral("radioMode")) {
            uint64_t mode=0;
            if(o.size()==2 && integer(o,"mode",2,&mode))modeRequest(unsigned(mode));
            return QVariant();
        } else if(op==QStringLiteral("options")) {''')
    s=replace(s,'            const bool nextMaster=o.value("master").toBool();','''            const bool nextMaster=o.value("master").toBool();
            if(nextMaster!=masterRequested) { modeRequest(nextMaster?2:0);return QVariant(); }''')
    # 冷启动恢复参数，但不按旧布尔 Master 自动占用无线。
    s=s.replace('(saved.flags&HblPersistentSettings::Master)!=0','false')
    s=replace(s,'            restoreReply(p);','            restoreReply(p);\n            modeReply(p);')
    (out/'runtime.cpp').write_text(s,encoding='utf-8',newline='\n')
    # 只扩大关闭时忙状态的报告，不改发送与曝光路径。
    worker=(P/'build/shutter-sync/worker/formal_worker.cpp').read_text(encoding='utf-8')
    worker=replace(worker,'p.values[FV_BUSY]=policy.busy();','p.values[FV_BUSY]=policy.busy() || radio.busy || (!policy.master && radio.held);')
    (O/'formal_worker.cpp').write_text(worker,encoding='utf-8',newline='\n')
    coordinate=(P/'build/second-camera-fixed/stage/files/coordinate.sh').read_text(encoding='utf-8')
    assert hashlib.sha256(coordinate.encode()).hexdigest()=='91efc47d35944bb67c105a81ece7cc225eba07f0523cd47779cb474f48b553cc'
    coordinate=replace(coordinate,'phase=prepare-radio\nsh "$p/prepare-radio.sh"','phase=radio-deferred-until-user-selection')
    (O/'coordinate.sh').write_text(coordinate,encoding='utf-8',newline='\n')
    values=read_rcc((P/'build/focus-delivery-repair/stage/files/af-ui.rcc').read_bytes())
    values['/common/RadioModeButton.qml']=(P/'qml/common/RadioModeButton.qml').read_text(encoding='utf-8')
    page=values['/controlscreen/FlashPage.qml']
    page=page.replace('import QtQuick 2.5','import QtQuick 2.5\nimport "../common"')
    a=page.index('        FlashIconButton {\n            objectName: "FlashMaster";')
    z=page.index('\n        Item {',a)
    page=page[:a]+'''        RadioModeButton {
            objectName: "FlashMaster"; x: 500; y: 3
            visible: page.screen!=="wireless"
        }
'''+page[z:]
    values['/controlscreen/FlashPage.qml']=page
    control=values['/controlscreen/ControlScreen.qml']
    if 'import "../common"' not in control:control=control.replace('import QtQuick 2.5','import QtQuick 2.5\nimport "../common"')
    a=control.rfind('            Item {',0,control.index('                    id: wifiIcon'))
    z=control.index('            Item {',control.index('                    id: wifiIcon'))
    control=control[:a]+'            RadioModeButton { objectName: "ControlRadioMode" }\n'+control[z:]
    values['/controlscreen/ControlScreen.qml']=control
    values['/main.qml']=replace(values['/main.qml'],'configstore.WIFI_power = !configstore.WIFI_power','if (typeof hblNative!=="undefined" && hblNative.radioModeVerified && !hblNative.radioModeBusy) hblNative.command=JSON.stringify({op:"radioMode",mode:(hblNative.radioMode+1)%3})')
    page=values['/controlscreen/NativeFlashPage.qml']
    page=replace(page,'(adapter.settingsError || adapter.errorText)','(adapter.radioModeError || adapter.settingsError || adapter.errorText)')
    values['/controlscreen/NativeFlashPage.qml']=page
    blob=rcc(values);assert read_rcc(blob)==values;(O/'af-ui.rcc').write_bytes(blob)
    return out

def build():
    out=sources()
    spec=importlib.util.spec_from_file_location('radio_ui_builder',P.parent/'build_native.py')
    b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    b.HERE=P/'build/halfpress-ui';b.FLASH=P;b.OUT=out
    b.generate=lambda:json.loads((b.HERE/'build/resources.json').read_text(encoding='utf-8'))
    ui=b.build()
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    old=P/'build/uart-source-repair'
    records=json.loads((old/'build.json').read_text(encoding='utf-8'))['commands']
    compile_args=list(records[0]['arguments'])
    compile_args[compile_args.index('-c')+1]=str(O/'formal_worker.cpp')
    compile_args[compile_args.index('-o')+1]=str(O/'formal_worker.o')
    link_args=list(records[-1]['arguments'])
    link_args=[str(O/'formal_worker.o') if x==str(old/'formal_worker.o') else x for x in link_args]
    link_args[link_args.index('-o')+1]=str(O/'libhbl-af-loader.so')
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(out/'global-cache'),ZIG_LOCAL_CACHE_DIR=str(out/'local-cache'),TEMP=str(out/'tmp'),TMP=str(out/'tmp'))
    for args in [compile_args,link_args]:
        result=subprocess.run([str(compiler),*args],env=env,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr)
    result=dict(compiled=True,installed=False,ui=ui,
                workerSha256=hashlib.sha256((O/'libhbl-af-loader.so').read_bytes()).hexdigest())
    (O/'build.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    print(json.dumps(build()))
