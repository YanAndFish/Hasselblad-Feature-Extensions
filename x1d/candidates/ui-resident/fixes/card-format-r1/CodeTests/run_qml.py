"""独立进程运行原厂/旧包负例/最小修正，不打开任何相机连接。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys
sys.dont_write_bytecode=True
FIX=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    cases=[(m,s,'both') for m in ('factory','a8','fixed') for s in ('storagefirst','languagefirst')]
    cases += [('fixed','languagefirst',c) for c in ('card0','card1')]
    reports=[]
    for args in cases:
        result=subprocess.run([sys.executable,'-X','utf8','-B',str(FIX/'CodeTests/test_card_format.py'),*args],capture_output=True,text=True,encoding='utf-8',timeout=60,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
        path=FIX/'build'/('reproduction-'+'-'.join(args)+'.json');value=json.loads(path.read_text(encoding='utf-8'))
        assert value['passed'] and value['hostQt']=='5.15.2' and value['mockFormatCalls']==value['hardwareRequests']==0
        reports.append({'file':path.relative_to(FIX).as_posix(),'sha256':sha(path),'checks':len(value['checks'])})
        print(json.dumps({'case':args,'checks':len(value['checks']),'passed':True}),flush=True)
    proof={'passed':True,'checks':sum(v['checks'] for v in reports),'cases':reports,'hostQt':'5.15.2','targetQt55Validated':False,
        'hardwareRequests':0,'mockFormatCalls':0,'sources':{p.relative_to(FIX).as_posix():sha(p) for p in (Path(__file__),FIX/'CodeTests/test_card_format.py',FIX/'patch.py')},
        'hostLimitation':'Qt6.11.2 original a8 and fixed full-list teardown access violation; this validated suite uses Qt5.15.2 with normal close and teardown'}
    (FIX/'build/qml-validation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':proof['checks'],'mockFormatCalls':0}))
if __name__=='__main__':run()
