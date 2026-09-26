"""实际 ARM ISR 导出消息 → 本机编译解析器、延时和无线请求编码；无设备。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'

def run():
    assert Path.cwd().resolve()==ROOT
    validation=json.loads((OUT/'irq-capture-validation.json').read_text(encoding='utf-8'))
    assert validation['passed']
    source=HERE/'CodeTests/mechanical_irq_wire.test.c'
    exe=OUT/'mechanical_irq_wire.test.exe'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:
        folder=OUT/name; folder.mkdir(exist_ok=True); env[key]=str(folder)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    subprocess.run([str(zig),'cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(HERE/'native'),str(source),'-o',str(exe)],env=env,check=True,timeout=60)
    packets=[OUT/f'irq-message-source-{s}.bin' for s in (2,3)]
    result=subprocess.run([str(exe),*map(str,packets)],capture_output=True,text=True,check=True,timeout=20)
    report={'passed':True,'nativeArmExportedPackets':2,'delayCases':1000002,
            'messageVersion':2,'uiBridgeVersion':4,'onlySources':[2,3],
            'oldPollingMessagesRejected':True,'preparedRequestSelectorsUnchanged':[40,43],
            'targetQtRuntimeChecked':False,'physicalLatencyMeasured':False,'hardwareRequests':0,
            'sourceHashes':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
               [Path(__file__),source,HERE/'native/mechanical_irq_wire.h',OUT/'irq_rf_core.h',OUT/'options_rf_bridge.h',OUT/'options_prepared_request.h',*packets]}}
    (OUT/'irq-wire-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result.stdout.strip())

if __name__=='__main__': run()
