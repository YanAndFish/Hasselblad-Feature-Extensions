"""本轮已授权的持久文件事务；默认离线，阶段只派发一次。"""
from pathlib import Path
import json,shlex,subprocess,sys,time
sys.dont_write_bytecode=True
from session import HERE,ROOT,OUT,REMOTE,Session,sha,bounded
DEST='/opt/hbl-wifi-probe-v1'
def fixed():
    report=json.loads((OUT/'current.json').read_text())
    assert report['packageSha256']=='1e2171827553e3846abe15c5cfe21e75a97a4234cff34ade8cd0ebdbfb7455b6'
    proof=json.loads((OUT/'persistence-validation.json').read_text())
    data=(HERE/'persist.sh').read_bytes()
    assert proof['passed'] and proof['sources']['persist.sh']==sha(data) and proof['packageSha256']==report['packageSha256']
    assert b'\r' not in data
    return report,data
def commands(data):
    result=[]
    for i,start in enumerate(range(0,len(data),32)):
        body=''.join('\\%03o'%b for b in data[start:start+32])
        cmd="printf '%b' "+shlex.quote(body)+(' >' if i==0 else ' >>')+REMOTE+'/persist.sh'
        result.append(bounded(cmd))
    return result
def offline():
    report,data=fixed();parts=commands(data)
    # 用实际 shell 解释所有 octal 字节，包括 UTF-8 注释、换行和美元符。
    script=''.join("printf '%b' "+shlex.quote(''.join('\\%03o'%b for b in data[start:start+32]))+'\n' for start in range(0,len(data),32))
    script_path=OUT/'persist-transfer-roundtrip.sh'
    script_path.write_text(script,encoding='ascii',newline='\n')
    result=subprocess.run(['C:/Program Files/Git/bin/sh.exe',str(script_path)],capture_output=True,timeout=10)
    assert result.returncode==0 and result.stdout==data
    print(json.dumps({'offline':True,'scriptSha256':sha(data),'frames':len(parts),'roundtrip':True}))
def main():
    assert Path.cwd().resolve()==ROOT
    args=sys.argv[1:]
    if not args:offline();return
    assert args in (['--stage-script'],['--install'],['--observe-install'],['--status'],['--remove'])
    report,data=fixed();action=args[0][2:];s=Session('persist-'+action)
    def call(n,c):return s.command(n,c)['output'].strip()
    if action=='status':
        assert call('installed-script','sha256sum '+DEST+'/persist.sh').split()[0]==sha(data)
        print(json.dumps({'status':call('status','sh '+DEST+'/persist.sh status')}));return
    assert call('package-identity','sha256sum '+REMOTE+'/manifest.sha256').split()[0]==report['files']['manifest.sha256']
    if action=='stage-script':
        parts=commands(data)
        call('new-script','test ! -e '+REMOTE+'/persist.sh && test ! -L '+REMOTE+'/persist.sh')
        for i,c in enumerate(parts):call('script-'+str(i),c)
        assert call('script-sha','sha256sum '+REMOTE+'/persist.sh').split()[0]==sha(data)
        call('syntax','sh -n '+REMOTE+'/persist.sh')
        print(json.dumps({'staged':True,'scriptSha256':sha(data),'requests':sum(e['submitted'] for e in s.s.entries)}));return
    assert call('script-identity','sha256sum '+REMOTE+'/persist.sh').split()[0]==sha(data)
    operation='remove' if action=='remove' else 'install'
    phase='persist-'+operation
    if action!='observe-install':
        call('unused-phase','test ! -e '+REMOTE+'/phases/'+phase)
        cmd='r='+REMOTE+';p='+phase+';mkdir "$r/phases/$p" && (sh "$r/persist.sh" '+operation+' >"$r/phases/$p/log" 2>&1;echo $? >"$r/phases/$p/exit") </dev/null >/dev/null 2>&1 &'
        call('dispatch-once',bounded(cmd))
    for i in range(60):
        time.sleep(1)
        cmd='r='+REMOTE+'/phases/'+phase+';if test -f "$r/exit";then cat "$r/exit";tail -n 1 "$r/log";else printf pending;fi'
        result=call('observe-'+str(i),cmd)
        if result!='pending':break
    else:raise RuntimeError('Outcome unknown; observe only, do not repeat')
    print(json.dumps({'operation':operation,'result':result,'closed':all(e['closed'] for e in s.s.entries)}))
    assert result.splitlines()[0]=='0','Persistence transaction failed; inspect and do not repeat automatically'
if __name__=='__main__':main()
