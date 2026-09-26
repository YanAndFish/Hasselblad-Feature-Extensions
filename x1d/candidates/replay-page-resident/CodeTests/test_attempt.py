"""离线验证旧尝试整根归档与同包新轮门禁；不初始化设备传输。"""
from pathlib import Path
import importlib.util,json,subprocess,sys,tempfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('replay_attempt_under_test',HERE/'session/attempt.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
REPORT={'packageSha256':m.PACKAGE_SHA,'files':{'manifest.sha256':'a'*64}}
class Model:
    def __init__(self,wrong=None,unknown=False,observe='archive=1 root=0'):
        self.calls=[];self.wrong=wrong;self.unknown=unknown;self.observe=observe;self.dispatched=set();self.failed=False
    def command(self,label,text):
        m.delivery.bounded(text);self.calls.append((label,text))
        if self.unknown and label=='attempt-archive-once':self.failed=True;raise RuntimeError('unknown transport result')
        values={'attempt-manifest':'a'*64+'  file','attempt-clean':'replay-health-self-test-pass\nreplay-page-preflight-ready',
            'attempt-phase-dir':'phase-dir-clean','attempt-preflight-records':'preflight-regular','attempt-ui-records':'ui-regular',
            'attempt-record-names':'\n'.join(m.EXPECTED_NAMES),'attempt-exits':'0\n62','attempt-destination':'archive-ready',
            'attempt-archive-once':'archived','attempt-observe-roots':self.observe,'attempt-observe-manifest':'a'*64+'  file'}
        return {'output':'bad' if label==self.wrong else values[label]}
def run():
    assert Path.cwd().resolve()==ROOT
    checks=[]
    def check(n,v):assert v,n;checks.append(n)
    model=Model();value=m.archive(model,REPORT)
    check('exact old attempt accepted',value['archived'] and value['oldOutcomes']=={'preflight':0,'ui':62})
    check('all commands bounded',all(len(v.encode())<=231 and '\n' not in v for _,v in model.calls))
    mutations=[v for n,v in model.calls if 'mv ' in v or 'rm ' in v]
    check('one atomic whole-root rename and no deletion',len(mutations)==1 and 'mv "$r" "$a"' in mutations[0] and 'rm ' not in mutations[0])
    for label in ('attempt-manifest','attempt-clean','attempt-phase-dir','attempt-preflight-records','attempt-ui-records','attempt-record-names','attempt-exits','attempt-destination'):
        model=Model(wrong=label)
        try:m.archive(model,REPORT)
        except RuntimeError:pass
        else:raise AssertionError(label+' accepted')
        check(label+' failure blocks rename',not any(n=='attempt-archive-once' for n,_ in model.calls))
    model=Model(unknown=True)
    try:m.archive(model,REPORT)
    except RuntimeError:pass
    else:raise AssertionError('unknown accepted')
    check('unknown rename is sent once and not retried',sum(n=='attempt-archive-once' for n,_ in model.calls)==1)
    for state,expected in [('archive=1 root=0',(True,False)),('archive=1 root=1',(True,True)),('archive=0 root=1',(False,True))]:
        value=m.observe(Model(observe=state),REPORT);check('observe '+state,(value['archived'],value['newRootPresent'])==expected)
    model=Model(observe='archive=0 root=0')
    try:m.observe(model,REPORT)
    except RuntimeError:pass
    else:raise AssertionError('ambiguous state accepted')
    check('ambiguous observation rejected',True)
    # 实际本地 shell 验证 rename 后旧 phase 六件证据逐字节保留。
    with tempfile.TemporaryDirectory(dir=HERE/'build/session') as t:
        t=Path(t);old=t/'root';archive=t/'archive';(old/'phases').mkdir(parents=True)
        (old/'common.sh').write_text('private(){ [ -d "$1" ]&&[ ! -L "$1" ];}\nabsent(){ [ ! -e "$1" ]&&[ ! -L "$1" ];}\n',encoding='ascii')
        before={}
        for n in m.EXPECTED_NAMES:
            data=('0\n' if n=='preflight.exit' else '62\n' if n=='ui.exit' else n+'\n').encode();(old/'phases'/n).write_bytes(data);before[n]=data
        mutation=mutations[0].replace(m.ARCHIVE,archive.as_posix()).replace(m.REMOTE,old.as_posix())
        result=subprocess.run(['C:/Program Files/Git/bin/sh.exe','-c',mutation],capture_output=True,text=True,timeout=10)
        check('actual same-filesystem rename succeeds',result.returncode==0 and result.stdout=='archived' and not old.exists() and archive.is_dir())
        check('all prior records preserved byte-identically',all((archive/'phases'/n).read_bytes()==v for n,v in before.items()))
    proof={'passed':True,'checks':checks,'testSha256':m.package.build.sha(Path(__file__)),'sourceSha256':m.package.build.sha(HERE/'session/attempt.py'),
        'hardwareRequests':0,'targetValidated':False,'scope':'modelled transport plus actual local atomic directory rename'}
    m.package.build.save(HERE/'build/session/attempt-validation.json',proof)
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
