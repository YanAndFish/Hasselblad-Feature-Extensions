"""生成 PagePool 真实 Loader 差分包并离线编译 Qt5.5.1 ARM；不操作设备。

--host-oracle 用本项目已有 PySide6 单独验证旧缺陷与基线期望，不能证明
C++ 候选通过。--build-arm 生成由父任务在获授权环境运行的独立 fixture。
测试不实例化相机对象、照片 provider、窗口、D-Bus 或传输层。
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode=True
MODULE=Path(__file__).resolve().parents[1]
ROOT=MODULE.parents[2]
OUTPUT=MODULE/'build/page-pool-native'
sys.path.insert(0,str(MODULE))
from native_page_pool import apply_native_page_pool, BASELINE_SHA256
from page_pool_native_cases import cases


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def prepare():
    assert Path.cwd().resolve()==ROOT
    OUTPUT.mkdir(parents=True,exist_ok=True)
    source=(MODULE/'PagePool.qml').read_text(encoding='utf-8')
    (OUTPUT/'BaselinePool.qml').write_bytes((MODULE/'PagePool.qml').read_bytes())
    (OUTPUT/'CandidatePool.qml').write_text(apply_native_page_pool(source),encoding='utf-8')
    harness=Path(__file__).with_name('page_pool_native_Harness.qml').read_text(encoding='utf-8')
    for kind in ['Baseline','Candidate']:
        (OUTPUT/(kind+'Harness.qml')).write_text(harness.replace('POOL_TYPE',kind+'Pool'),encoding='utf-8')
    (OUTPUT/'Dummy.qml').write_bytes(Path(__file__).with_name('page_pool_native_Dummy.qml').read_bytes())
    inputs={'format':'hbl-page-pool-v1','baselineSha256':BASELINE_SHA256,'cases':cases()}
    save(OUTPUT/'events.json',inputs)
    save(OUTPUT/'build.json',{'built':False,'executed':False,'hardwareRequests':0,'baselineSha256':BASELINE_SHA256})
    return inputs


def at(value,path):
    for key in path.split('.'):
        value=value[int(key)] if isinstance(value,list) else value.get(key)
    return value


def host_oracle(inputs):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    os.environ['QML_DISABLE_DISK_CACHE']='1'
    os.environ['QML_DISK_CACHE_PATH']=str(OUTPUT/'qml-cache')
    sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
    from PySide6.QtCore import QCoreApplication,QEvent,QUrl,qVersion
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine,QQmlEngine,QQmlIncubationController
    import shiboken6
    app=QCoreApplication.instance() or QGuiApplication([])
    assertions=0;records=0
    def call(engine,root,name,event=None):
        obj=engine.newQObject(root);fn=obj.property(name)
        result=fn.callWithInstance(obj,[] if event is None else [engine.toScriptValue(event)])
        if result.isError():raise RuntimeError(result.toString()+' '+result.property('stack').toString())
        return result
    def settle(controller):
        begin=time.monotonic()
        app.processEvents();app.sendPostedEvents(None,QEvent.DeferredDelete)
        while time.monotonic()-begin<.1 or controller.incubatingObjectCount():
            controller.incubateFor(3);app.processEvents();app.sendPostedEvents(None,QEvent.DeferredDelete);time.sleep(.001)
            if time.monotonic()-begin>3:raise TimeoutError('incubation')
    report={'passed':False,'runtime':'Qt6 host baseline only','qtVersion':qVersion(),'candidateExecuted':False,'hardwareRequests':0}
    # PySide6 6.11.2/CPython 3.14 crashes deleting even a minimal exposed
    # QQmlComponent. QQmlApplicationEngine owns that component in C++ instead;
    # roots and the engine are still explicitly deleted and cleanup is tested.
    engine=QQmlApplicationEngine();controller=QQmlIncubationController();engine.setIncubationController(controller)
    with (OUTPUT/'host-baseline-trace.jsonl').open('w',encoding='utf-8') as trace:
        try:
            for case in inputs['cases']:
                engine.load(QUrl.fromLocalFile(str(OUTPUT/'BaselineHarness.qml')))
                roots=engine.rootObjects()
                if not roots:raise RuntimeError('Baseline harness could not be created')
                root=roots[-1]
                QQmlEngine.setObjectOwnership(root,QQmlEngine.CppOwnership)
                for index,event in enumerate(case['events']):
                    call(engine,root,'run',event)
                    if event['op']=='settle':settle(controller)
                    observed=json.loads(call(engine,root,'observe').toString());records+=1
                    trace.write(json.dumps({'case':case['name'],'index':index,'state':observed},ensure_ascii=False)+'\n');trace.flush()
                    for key,expected in {**event.get('expect',{}),**event.get('baseline',{})}.items():
                        actual=at(observed,key);assertions+=1
                        if actual!=expected:raise AssertionError(f"{case['name']} #{index} {key}: expected {expected!r}, got {actual!r}")
                shiboken6.delete(root)
                settle(controller)
            report.update(passed=True,records=records,assertions=assertions,cases=len(inputs['cases']))
        except Exception as exc:
            report.update(error=str(exc),records=records,assertions=assertions)
            save(OUTPUT/'host-baseline-result.json',report)
            engine.setIncubationController(None)
            if shiboken6.isValid(root):shiboken6.delete(root)
            shiboken6.delete(engine)
            raise
    save(OUTPUT/'host-baseline-result.json',report)
    print(json.dumps(report,ensure_ascii=False))
    engine.setIncubationController(None)
    shiboken6.delete(engine)


def build_arm(inputs):
    base=ROOT/'.research-cache/x1d-1.25.0';qt=base/'qt-public';qtbase=qt/'qtbase-opensource-src-5.5.1'
    env=dict(os.environ)
    for key,folder in [('ZIG_GLOBAL_CACHE_DIR','global'),('ZIG_LOCAL_CACHE_DIR','local'),('TEMP','tmp'),('TMP','tmp')]:
        directory=OUTPUT/folder;directory.mkdir(exist_ok=True);env[key]=str(directory)
    include=OUTPUT/'include/QtCore';include.mkdir(parents=True,exist_ok=True)
    (include/'qconfig.h').write_text('#define QT_SHARED\n#define QT_NO_DEBUG\n#define QT_POINTER_SIZE 4\n#define QT_OPENGL_ES_2\n',encoding='utf-8')
    (include/'qfeatures.h').write_text('/* target Qt 5.5.1 */\n',encoding='utf-8')
    layout=OUTPUT/'relocations.ld';layout.write_text('SECTIONS { .rel.dyn : { *(.rel.dyn) } .rel.plt : { *(.rel.plt) } } INSERT BEFORE .ARM.exidx;\n',encoding='utf-8')
    target=['-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9']
    flags=target+['-marm','-O2','-fPIC','-fno-stack-protector','-I',str(OUTPUT/'include'),'-isystem',str(qtbase/'include'),'-isystem',str(qt/'qtdeclarative-opensource-src-5.5.1/include'),'-I',str(qtbase/'mkspecs/linux-arm-gnueabi-g++'),'-Wno-deprecated-declarations','-Wno-enum-constexpr-conversion']
    zig=base/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    libs=[base/('baseline/usr/lib/libQt5'+name+'.so.5.5.1') for name in ['Quick','Qml','Gui','Network','Core']]+[base/('baseline/'+name) for name in ['usr/lib/libstdc++.so.6.0.21','lib/libgcc_s.so.1','lib/libdl-2.22.so','lib/libc-2.22.so','lib/libpthread-2.22.so']]
    obj=OUTPUT/'runner.o';binary=OUTPUT/'runner'
    for command in [['c++','-std=c++11']+flags+['-c',str(Path(__file__).with_name('page_pool_native_runner.cpp')),'-o',str(obj)],['cc']+target+['-no-pie','-Wl,--no-undefined','-Wl,-s','-Wl,-T,'+str(layout),str(obj)]+[str(lib) for lib in libs]+['-o',str(binary)]]:
        result=subprocess.run([str(zig)]+command,env=env,capture_output=True,text=True,timeout=120)
        if result.returncode:raise RuntimeError(result.stderr)
    names=['runner','BaselinePool.qml','CandidatePool.qml','BaselineHarness.qml','CandidateHarness.qml','Dummy.qml','events.json']
    with tarfile.open(OUTPUT/'test.tgz','w:gz',compresslevel=9) as archive:
        for name in names:archive.add(OUTPUT/name,arcname=name)
    names+=['test.tgz']
    report={'built':True,'executed':False,'targetQt':'5.5.1','cameraRequests':0,'baselineSha256':BASELINE_SHA256,'cases':len(inputs['cases']),
        'scope':'Pure QtQuick Loader/cache/lifecycle fixture; no window, camera, network or photos.',
        'files':{name:hashlib.sha256((OUTPUT/name).read_bytes()).hexdigest() for name in names}}
    source_names=['page_pool_core.h','native_page_pool.py','NativePagePool.qml','PagePool.qml',
        'CodeTests/page_pool_native_runner.cpp','CodeTests/page_pool_native_cases.py',
        'CodeTests/page_pool_native_Harness.qml','CodeTests/page_pool_native_Dummy.qml']
    report['sources']={str((MODULE/name).relative_to(ROOT)).replace('\\','/'):hashlib.sha256((MODULE/name).read_bytes()).hexdigest() for name in source_names}
    save(OUTPUT/'build.json',report)
    print(json.dumps({'built':True,'executed':False,'bytes':(OUTPUT/'test.tgz').stat().st_size,'cases':len(inputs['cases'])}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host-oracle',action='store_true');parser.add_argument('--build-arm',action='store_true')
    args=parser.parse_args();inputs=prepare()
    if args.host_oracle:host_oracle(inputs)
    if args.build_arm:build_arm(inputs)
