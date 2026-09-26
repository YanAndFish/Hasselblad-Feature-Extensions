"""从已装组合基线生成仅 EVF 提示变更的资源与 GUI 库。"""
from pathlib import Path
import importlib.util,json,hashlib,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];WORK=HERE/'evf-hint-r1'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(data):return hashlib.sha256(data).hexdigest()
def build():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    compose=load('evf_compose',HERE/'compose.py')
    report=json.loads((HERE/'build/resources.json').read_text())
    blob=(HERE/'build/combined-ui.rcc').read_bytes();assert sha(blob)==report['rccSha256']
    values=compose.read_rcc(blob)
    for name in ('/main.qml','/common/TouchWindow.qml'):
        values[name]=(HERE/'mechanical-calibration-r1/qml'/name.lstrip('/')).read_text(encoding='utf-8')
    writer=load('evf_rcc_writer',ROOT/'x1d/candidates/ui-resident/tools/resource_bundle.py')
    blob=writer.rcc(values);assert compose.read_rcc(blob)==values
    out=WORK/'build';out.mkdir(parents=True,exist_ok=True)
    (out/'combined-ui.rcc').write_bytes(blob)
    for name,value in values.items():
        p=out/'qml'/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8',newline='\n')
        report['resources'][name]['sha256']=sha(value.encode())
    report.update(rccSha256=sha(blob),rccBytes=len(blob),targetValidated=False)
    (out/'resources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    builder=load('evf_native_builder',HERE/'build_native.py');builder.HERE=WORK;builder.OUT=out/'native'
    result=builder.build();print(json.dumps(result))
if __name__=='__main__':build()
