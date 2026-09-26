"""组合入口只追加本模块声明，保留引闪曝光续行与常驻页修改；无设备。"""
from pathlib import Path
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE/'tools'))
from compose_joint_resources import compose,identity,MARKER
sys.path.insert(0,str(ROOT/'x1d/tools'))
from binary import ArmElf,qml_files

def run():
    original=qml_files(ArmElf.load('usr/bin/victory-gui'))
    checks=[]
    def check(name,condition):assert condition,name;checks.append(name)
    # 此处只读取主任务当前离线资源，不把它当作新组合的冻结输入。
    formal=ROOT/'x1d/wireless-flash/build/formal-runtime-ui/qml/main.qml'
    resident=ROOT/'x1d/candidates/ui-resident/build/overlay/mainmenu/MainScreen.qml'
    examples=[('original',dict(original)),('formal-plus-resident',dict(original))]
    examples[1][1]['/main.qml']=formal.read_text(encoding='utf-8')
    examples[1][1]['/mainmenu/MainScreen.qml']=resident.read_text(encoding='utf-8')
    for label,source in examples:
        before=dict(source);result=compose(source)
        check(label+'-input-unchanged',source==before)
        check(label+'-only-main-changed',{k for k in result if result[k]!=source.get(k)}=={'/main.qml'})
        check(label+'-previous-main-body-retained',result['/main.qml'].startswith(source['/main.qml'].rstrip()[:-1]))
        check(label+'-single-marker',result['/main.qml'].count(MARKER)==1)
        check(label+'-main-identity',identity(result)==hashlib.sha256(result['/main.qml'].encode()).hexdigest())
        check(label+'-no-second-hold',result['/main.qml'].count('idleWakeupOrForceOff')==source['/main.qml'].count('idleWakeupOrForceOff'))
        try:compose(result)
        except ValueError:checks.append(label+'-duplicate-rejected')
        else:raise AssertionError('duplicate')
    for invalid in ({},{'main.qml':original['/main.qml']},{'/main.qml':'Item {}'}):
        try:compose(invalid)
        except ValueError:checks.append('invalid-input-rejected')
        else:raise AssertionError('invalid accepted')
    report={'passed':True,'checks':checks,'cameraAccess':False,'targetQtExecuted':False,
            'inputScope':'current offline resource examples; not a frozen joint installation',
            'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            [Path(__file__),HERE/'tools/compose_joint_resources.py']},
            'exampleInputHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [formal,resident]}}
    out=HERE/'artifacts/joint-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'composition.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jointCompositionChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
