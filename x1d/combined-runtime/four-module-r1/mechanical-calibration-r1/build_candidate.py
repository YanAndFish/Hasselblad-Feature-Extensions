"""构建配套标定 GUI/observer 和包含两秒提示的组合资源。"""
from pathlib import Path
import hashlib,json,sys,importlib.util
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;ROOT=HERE.parents[3]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(b):return hashlib.sha256(b).hexdigest()
def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    compose=load('calibration_compose',PARENT/'compose.py')
    report=json.loads((PARENT/'build/resources.json').read_text(encoding='utf-8'))
    values={('/'+p.relative_to(HERE/'qml').as_posix()):p.read_text(encoding='utf-8') for p in (HERE/'qml').rglob('*') if p.is_file()}
    assert len(values)==25
    report['resources']['/controlscreen/FlashCalibrationDialog.qml']={'owner':'flash'}
    assert set(values)==set(report['resources'])
    writer=load('calibration_rcc_writer',ROOT/'x1d/candidates/ui-resident/tools/resource_bundle.py')
    blob=writer.rcc(values);assert compose.read_rcc(blob)==values
    (HERE/'build/combined-ui.rcc').write_bytes(blob)
    for name,value in values.items():report['resources'][name]['sha256']=sha(value.encode())
    report.update(rccSha256=sha(blob),rccBytes=len(blob),targetValidated=False)
    (HERE/'build/resources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    builder=load('calibration_native',PARENT/'build_native.py')
    builder.HERE=HERE;builder.OUT=HERE/'build/native';builder.FLASH=HERE
    gui=builder.build()
    clients=load('calibration_clients',HERE/'research/build_formal_clients.py')
    clients.ROOT=ROOT;clients.CACHE=ROOT/'.research-cache/x1d-1.25.0';clients.BASELINE=clients.CACHE/'baseline'
    worker=clients.build()
    print(json.dumps({'gui':gui,'clients':worker,'hardwareRequests':0}))
if __name__=='__main__':build()
