"""从已确认停止的旧 worker 继续；只发送修正脚本，不重传包。"""
from pathlib import Path
import base64,hashlib,json,shlex,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import increment,install_candidate
REMOTE=increment.REMOTE
def sha(b):return hashlib.sha256(b).hexdigest()
if __name__=='__main__':
    assert sys.argv[1:]==['--resume-confirmed-stop']
    data=(HERE/'resume.sh').read_bytes();proof=json.loads((HERE/'CodeTests/resume-transaction-validation.json').read_text())
    assert proof['passed'] and proof['applySha256']==sha(data)
    s=increment.session.Session('calibration-resume-confirmed-stop');seen=set()
    report={'installed':False,'resumeSha256':sha(data),'reusedUploadedArchive':True}
    def cmd(label,command):
        assert label not in seen and len(command.encode('ascii'))<=231 and '\n' not in command,(label,len(command))
        seen.add(label);return s.command(label,command)['output'].strip()
    def save(stage):
        report.update(stage=stage,session=s.summary())
        (HERE/'update/resumed-installation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'stage':stage,'requests':s.summary()['requests']}),flush=True)
    try:
        cmd('resume-fresh','r='+REMOTE+';test -d "$r/previous" && test ! -e "$r/resume64" && test ! -e "$r/resume.sh" && test ! -e "$r/resume-dispatched"')
        expected=json.loads((HERE/'update/proof.json').read_text())['archiveSha256']
        assert cmd('existing-archive','sha256sum '+REMOTE+'/update.tgz').split()[0]==expected
        encoded=base64.b64encode(data).decode()
        for i,start in enumerate(range(0,len(encoded),160)):
            cmd('script-'+str(i),"printf '%s\\n' "+shlex.quote(encoded[start:start+160])+(' >' if i==0 else ' >>')+REMOTE+'/resume64')
        cmd('decode-script','r='+REMOTE+';printf \'%b\' "$(awk -f "$r/d.awk" "$r/resume64")" >"$r/resume.sh";sha256sum "$r/resume.sh"')
        assert cmd('script-hash','sha256sum '+REMOTE+'/resume.sh').split()[0]==sha(data)
        cmd('syntax','sh -n '+REMOTE+'/resume.sh')
        cmd('resume-once','r='+REMOTE+';test ! -e "$r/resume-dispatched" && touch "$r/resume-dispatched" && (cd "$r";sh resume.sh >resume.log 2>&1;echo $? >resume.exit) </dev/null >/dev/null 2>&1 &')
        save('resume-dispatched-once')
        for i in range(200):
            time.sleep(1)
            result=cmd('observe-'+str(i),'r='+REMOTE+';if test -f "$r/resume.exit";then cat "$r/resume.exit";test ! -f "$r/result" || cat "$r/result";else printf pending;fi')
            if result!='pending':break
        else:raise RuntimeError('resume pending; do not redispatch')
        assert result.splitlines()==['0','calibration-increment-ready'],result
        assert cmd('services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon').splitlines()==['active']*5
        report['installed']=True;save('paired-update-ready')
        after=install_candidate.audit()
        (HERE/'update/preservation-after.json').write_text(json.dumps(after,indent=2)+'\n')
        report['afAndFlashPreserved']=True;save('complete')
        (HERE/'update/final-result.json').write_text(json.dumps(report,indent=2)+'\n')
    except BaseException as e:
        report['error']=str(e);save('stopped-for-review');raise
