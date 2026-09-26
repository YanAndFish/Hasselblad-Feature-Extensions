"""编译白名单检查、核对原厂调用点与界面资源基线。"""
from pathlib import Path
import hashlib, importlib.util, json, os, subprocess, sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-options-candidate'
def sha(data): return hashlib.sha256(data).hexdigest()
def validate():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]: env[key]=str(OUT/name)
    exe=OUT/'wire-check.exe'
    result=subprocess.run([str(compiler),'cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(HERE/'native'),str(HERE/'CodeTests/mechanical_options_wire.test.c'),'-o',str(exe)],env=env,capture_output=True,text=True,timeout=60)
    if result.returncode: raise RuntimeError(result.stderr)
    run=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=10,check=True)
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from binary import ArmElf
    raw=(ROOT/'.research-cache/x1d-1.25.0/usb-diagnostic-inputs/usr/bin/msg2dbus').read_bytes()
    assert sha(raw)=='988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1'
    bridge=ArmElf(raw)
    call=bridge.instructions(0x1a09c,4)[0]
    assert call.mnemonic=='bl' and bridge.name(int(call.op_str[1:],0))=='_ZN16QCoreApplication4execEv'
    spec=importlib.util.spec_from_file_location('options_validate_assets',HERE/'build.py'); assets=importlib.util.module_from_spec(spec); spec.loader.exec_module(assets)
    parent=HERE/'build/mechanical-sync-candidate/qml'
    files={'/'+str(p.relative_to(parent)).replace('\\','/'):p.read_text(encoding='utf-8') for p in parent.rglob('*.qml')}
    actual=(HERE/'build/mechanical-timing-candidate/package-files/ui.rcc').read_bytes()
    assert assets.rcc(files)==actual,'QML baseline differs from installed resource'
    generated=OUT/'qml/controlscreen/MechanicalFlashPage.qml'
    qml=generated.read_text(encoding='utf-8')
    for label in ('自动引闪：','每次准备：','同一程序处理：'): assert qml.count(label)==1
    assert 'model: ["A 首次同步", "B 首次同步", "启动保持", "退出空闲", "状态 1 置位", "状态 3 置位", "返回空闲"]' in qml
    report={'passed':True,'wireCheck':run.stdout.strip(),'fixedMsg2dbusExecCallVerified':True,
            'qmlParentMatchesInstalled':True,'threeToggleLabels':True,'sourcesRetained':7,'hardwareRequests':0,
            'targetRuntimeChecked':False,'physicalTimingVerified':False}
    (OUT/'options-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': validate()
