"""EVF 提示的界面增量；默认离线打包，明确参数执行当前会话安装。"""
from pathlib import Path
import base64,hashlib,io,json,shlex,subprocess,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(PARENT));import session
REMOTE='/tmp/hbl-evf-hint-r2'
def sha(b):return hashlib.sha256(b).hexdigest()
def build():
    info=json.loads((HERE/'build/native/build.json').read_text())
    old=(PARENT/'evf-hint-r1/update/manifest.sha256').read_bytes()
    assert sha(old)=='2fecd16e4fda183463fdd92c74404c9a2aedb26ea291adef444bab033395ccff'
    rcc=(HERE/'build/combined-ui.rcc').read_bytes();lib=(HERE/'build/native/libhbl-four-module.so').read_bytes()
    assert sha(rcc)==info['rccSha256'] and sha(lib)==info['librarySha256']
    rows={n:h for h,n in (line.split() for line in old.decode().splitlines())}
    rows['formal-ui.rcc']=sha(rcc);rows['libhbl-formal.so']=sha(lib)
    manifest=''.join(h+'  '+n+'\n' for n,h in sorted(rows.items())).encode()
    files={'formal-ui.rcc':rcc,'libhbl-formal.so':lib,'manifest.sha256':manifest,
           'package-manifest.sha256':(sha(manifest)+'\n').encode(),'apply.sh':(HERE/'apply.sh').read_bytes()}
    files['update.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    out=HERE/'update';out.mkdir(exist_ok=True)
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        for n,b in files.items():
            (out/n).write_bytes(b)
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o600;t.addfile(m,io.BytesIO(b))
    data=buf.getvalue();(out/'update.tar.gz').write_bytes(data)
    shell='C:/Program Files/Git/bin/sh.exe'
    assert subprocess.run([shell,'-n',str(HERE/'apply.sh')],capture_output=True).returncode==0
    encoded=base64.b64encode(data).decode()
    (out/'p64').write_text('\n'.join(encoded[i:i+172] for i in range(0,len(encoded),172))+'\n',encoding='ascii')
    (out/'d.awk').write_text(session.transport.DECODER,encoding='ascii')
    r=subprocess.run([shell,'-c','printf \'%b\' "$(awk -f d.awk p64)" > decoded.tgz'],cwd=out,capture_output=True)
    assert r.returncode==0 and sha((out/'decoded.tgz').read_bytes())==sha(data)
    proof={'passed':True,'archiveSha256':sha(data),'bytes':len(data),'manifestSha256':sha(manifest),
           'rccSha256':sha(rcc),'librarySha256':sha(lib),'applySha256':sha(files['apply.sh']),'hardwareRequests':0}
    (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
def install():
    proof=json.loads((HERE/'update/proof.json').read_text());data=(HERE/'update/update.tar.gz').read_bytes()
    assert proof['passed'] and sha(data)==proof['archiveSha256'] and sha((HERE/'apply.sh').read_bytes())==proof['applySha256']
    s=session.Session('evf-hint-framed');seen=set()
    def cmd(label,command):
        assert label not in seen and len(command.encode('ascii'))<=231 and '\n' not in command,(label,len(command))
        seen.add(label);return s.command(label,command)['output'].strip()
    report={'installed':False,'proof':proof}
    def save(stage):
        report.update(stage=stage,session=s.summary())
        (HERE/'update/installation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'stage':stage,'requests':s.summary()['requests']}),flush=True)
    try:
        cmd('stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r"')
        decoder=session.transport.DECODER
        for i,start in enumerate(range(0,len(decoder),85)):
            cmd('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+85])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
        encoded=base64.b64encode(data).decode();chunks=[encoded[i:i+172] for i in range(0,len(encoded),172)]
        for i,part in enumerate(chunks):
            cmd('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if (i+1)%150==0:save('transferred-'+str(i+1)+'-of-'+str(len(chunks)))
        save('archive-transferred')
        cmd('decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/update.tgz";sha256sum "$r/update.tgz" >"$r/decode.sha") </dev/null >/dev/null 2>&1 &')
        for i in range(100):
            time.sleep(1);result=cmd('decode-'+str(i),'r='+REMOTE+';if test -f "$r/decode.sha";then cat "$r/decode.sha";else printf pending;fi')
            if result!='pending':break
        else:raise RuntimeError('decode pending; no redispatch')
        assert result.split()[0]==proof['archiveSha256']
        cmd('extract','cd '+REMOTE+' && tar xzf update.tgz && sha256sum -c update.sha256 >/dev/null && sh -n apply.sh')
        save('verified-before-apply')
        cmd('apply-once','r='+REMOTE+';test ! -e "$r/dispatched" && touch "$r/dispatched" && (cd "$r";sh apply.sh >log 2>&1;echo $? >exit) </dev/null >/dev/null 2>&1 &')
        save('apply-dispatched-once')
        for i in range(140):
            time.sleep(1);result=cmd('apply-'+str(i),'r='+REMOTE+';if test -f "$r/exit";then cat "$r/exit";test ! -f "$r/result" || cat "$r/result";else printf pending;fi')
            if result!='pending':break
        else:raise RuntimeError('apply pending; no redispatch')
        assert result.splitlines()==['0','evf-hint-increment-ready'],result
        assert cmd('services','systemctl is-active victory-gui msg2dbus-farm system-manager configstore jpeg-daemon').splitlines()==['active']*5
        report['installed']=True;save('complete')
    except BaseException as e:
        report.update(error=str(e),automaticRetry=False);save('stopped-for-review');raise
    return report
if __name__=='__main__':
    if not sys.argv[1:]:print(json.dumps(build()))
    elif sys.argv[1:]==['--install']:print(json.dumps(install()))
    else:raise SystemExit('unsupported action')
