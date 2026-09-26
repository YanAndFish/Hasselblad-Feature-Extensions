"""参数页先就绪、其余页面启动后异步预热；仅构建。"""
from pathlib import Path
import importlib.util,json,hashlib
P=Path(__file__).resolve().parent;O=P/'build/halfpress-ui';O.mkdir(exist_ok=True)
def load(n,path):
 spec=importlib.util.spec_from_file_location(n,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
values={('/'+f.relative_to(P/'qml').as_posix()):f.read_text(encoding='utf-8') for f in (P/'qml').rglob('*') if f.is_file()}
values['/mainmenu/MainScreen.qml']=values['/mainmenu/MainScreen.qml'].replace('warmEnabled: System.system_state === System.StateUp','warmEnabled: System.system_state === System.StateUp && typeof hblNative!=="undefined" && hblNative.backgroundWarm >= 1')
values['/mainmenu/ResidentLoader.qml']=values['/mainmenu/ResidentLoader.qml'].replace('interval: 16; onTriggered: host.warmNext()','interval: 150; onTriggered: host.warmNext()')
for name,anchor,stage in [('/common/TouchWindow.qml','id: media_browse_loader',2),('/liveview/EVFWindow.qml','id: preView',3)]:
 s=values[name];at=s.index(anchor);end=s.index('active: true',at)
 s=s[:end]+s[end:].replace('active: true','active: presented || (typeof hblNative!=="undefined" && hblNative.backgroundWarm >= '+str(stage)+')',1);values[name]=s

gate=values['/FormalExposureGate.qml']
a=gate.index('    function begin(');b=gate.index('    function cancel()',a)
gate=gate[:a]+'    function begin(liveviewAfterExposure) {\n        if (!alive || !contextValid) return false\n        // 曝光不依赖无线状态或回执。尽力提交本次参数；不重入已有无线任务。\n        if (!activeToken && nativeAdapter && nativeAdapter.connected && nativeAdapter.masterEnabled &&\n                isFinite(exposureUs) && exposureUs>=1 && exposureUs<=86400000000) {\n            var last=nativeAdapter.lastFlushToken\n            if(last===undefined)last=0\n            var candidate=Math.max(nextToken,last)+1\n            if(candidate<2147483647) {\n                nextToken=candidate;activeToken=candidate\n                command({op:"flush",token:candidate,electronic:electronic,exposureUs:Math.round(exposureUs)})\n            }\n        }\n        continueExposure(liveviewAfterExposure)\n        return true\n    }\n'+gate[b:]
a=gate.index('    function checkAcknowledgement()');b=gate.index('    onAckTokenChanged:',a)
gate=gate[:a]+'    function checkAcknowledgement() {\n        if (!activeToken || !nativeAdapter || ackToken!==activeToken) return\n        // 回执只清理失败的无线任务，绝不触发第二次曝光。\n        if(nativeAdapter.flushResult!==0)activeToken=0\n    }\n'+gate[b:]
a=gate.index('    function begin(');z=gate.index('    function cancel()',a)
old=gate[a:z]
prepare=old.replace('function begin(liveviewAfterExposure)', 'function prepareHalfPress()').replace('        continueExposure(liveviewAfterExposure)\n','')
gate=gate[:a]+prepare+'    property bool fullCommitted: false\n    function begin(liveviewAfterExposure) {\n        if (!alive || !contextValid) return false\n        fullCommitted=true\n        continueExposure(liveviewAfterExposure)\n        return true\n    }\n    function halfReleased() {\n        if (!fullCommitted) shotEnded()\n        fullCommitted=false\n    }\n'+gate[z:]
gate=gate.replace('op:"flush"','op:"prepare"')
gate=gate.replace('        fullCommitted=true\n', '''        if (!fullCommitted && activeToken && nativeAdapter && nativeAdapter.connected &&
                isFinite(exposureUs) && exposureUs>=1 && exposureUs<=86400000000)
            command({op:"queueSync",token:activeToken,electronic:electronic,exposureUs:Math.round(exposureUs)})
        fullCommitted=true
''')
main=values['/main.qml']
anchor='            console.log("Got half press")'
assert main.count(anchor)==1
main=main.replace(anchor,anchor+'\n            formalExposureGate.prepareHalfPress()')
anchor='                console.log("Got half release")'
assert main.count(anchor)==1
main=main.replace(anchor,anchor+'\n                formalExposureGate.halfReleased()')
values['/main.qml']=main
values['/FormalExposureGate.qml']=gate
page=values['/controlscreen/FlashPage.qml']
page=page.replace('        if (typeof powerUpdates!=="boolean"','        powerUpdates=true\n        if (typeof powerUpdates!=="boolean"')
a=page.index('            FlashToggleRow {',page.index('label: "发送功率更新"')-150) if False else page.rfind('            FlashToggleRow {',0,page.index('label: "发送功率更新"'))
# only remove the power switch; synchronization preference remains.
if a<0: raise RuntimeError('power toggle anchor')
b=page.index('            }',page.index('label: "发送功率更新"'))+len('            }')
page=page[:a]+page[b:]
values['/controlscreen/FlashPage.qml']=page

writer=load('background_rcc',P.parents[3]/'x1d/candidates/ui-resident/tools/resource_bundle.py')
compose=load('background_compose',P.parent/'compose.py');blob=writer.rcc(values);assert compose.read_rcc(blob)==values
(O/'build').mkdir(exist_ok=True);(O/'build/combined-ui.rcc').write_bytes(blob)
r=json.loads((P/'build/resources.json').read_text(encoding='utf-8'))
for n,v in values.items():r['resources'][n]['sha256']=hashlib.sha256(v.encode()).hexdigest()
r['rccSha256']=hashlib.sha256(blob).hexdigest();r['rccBytes']=len(blob)
(O/'build/resources.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
b=load('background_gui',P/'build_combined_ui.py').b;b.HERE=O;b.OUT=O/'gui'
original=b.generate
def generate():
 r=original();f=b.OUT/'runtime.cpp';s=f.read_text(encoding='utf-8')
 a=s.index('void replayStatus(');z=s.index('\n}',a)+2;s=s[:a]+s[z:]
 a=s.index('namespace {\nbool pages(');z=s.index('\n}\n}',a)+4;s=s[:a]+s[z:]
 a=s.index('        replayStatus("replay-page-awaiting-pages");');z=s.index('        timer->start();',a)+len('        timer->start();')
 s=s[:a]+'''        runtime->insert(QStringLiteral("backgroundWarm"),0);
        auto warm=new QTimer(engine);warm->setInterval(500);
        QObject::connect(warm,&QTimer::timeout,engine,[warm](){
            if(!runtime || runtime->value(QStringLiteral("bootLoading")).toBool() ||
               runtime->value(QStringLiteral("installationHold")).toBool())return;
            int phase=runtime->value(QStringLiteral("backgroundWarm")).toInt()+1;
            runtime->insert(QStringLiteral("backgroundWarm"),phase);
            if(phase>=3){warm->stop();warm->deleteLater();}
        });
        warm->start();'''+s[z:]
 a=s.index('            // 仅编译动态页面');z=s.index('else report("formal-ui-loaded-default-off");',a)+len('else report("formal-ui-loaded-default-off");')
 s=s[:a]+'            report("formal-ui-loaded-default-off");'+s[z:]
 s=s.replace('power=(saved.flags&HblPersistentSettings::Power)!=0;','power=true;').replace('power=o.value("power").toBool();','power=true;')
 f.write_text(s,encoding='utf-8',newline='\n')
 (b.OUT/'readiness.h').write_text('''#pragma once
namespace {
struct BootGate : QObject {
 QQmlApplicationEngine *engine;QTimer timer;unsigned attempts=0;
 explicit BootGate(QQmlApplicationEngine *e):QObject(e),engine(e){
  QObject::connect(&timer,&QTimer::timeout,this,[this](){
   bool ready=false;
   for(QObject *root:engine->rootObjects()) {
    QObject *loader=root->findChild<QObject *>(QStringLiteral("camera_view_loader"));
    QObject *page=root->findChild<QObject *>(QStringLiteral("ControlScreen_focusScope"));
    if(loader && loader->property("status").toInt()==1 && page)ready=true;
   }
   if(ready){timer.stop();status("parameter-page-ready");}
   else if(++attempts>=300){timer.stop();status("parameter-page-timeout");}
  });
 }
 void start(){status("parameter-page-pending");timer.start(100);}
};
}
''',encoding='utf-8',newline='\n')
 return r
b.generate=generate
if __name__=='__main__':print(json.dumps(b.build()))
