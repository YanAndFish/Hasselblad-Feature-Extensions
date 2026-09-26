"""传送并单次执行已验证的机内只读探针；不安装永久文件。"""
from pathlib import Path
import base64,hashlib,io,json,shlex,sys,tarfile,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent));import session
sys.path.insert(0,str(HERE.parent/'mechanical-calibration-r1'));import install_candidate
REMOTE='/tmp/hbl-boot-probe-r1';OUT=HERE/'build/probe-install'
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare():
    if Path.cwd().resolve()!=ROOT:raise RuntimeError('workspace')
    proof=json.loads((HERE/'CodeTests/probe-transaction-validation.json').read_text())
    script=(HERE/'probe.sh').read_bytes()
    assert proof['passed'] and proof['scriptSha256']==sha(script)
    build=json.loads((HERE/'build/formal-flash-program/client-build.json').read_text(encoding='utf-8'))
    for name,h in build['sourceHashes'].items():assert sha((HERE/name).read_bytes())==h,name
    lib=(HERE/'build/formal-flash-program/libhbl-boot-probe.so').read_bytes()
    assert sha(lib)==build['outputs']['libhbl-boot-probe.so']['sha256']
    files={'probe.sh':script,'probe.so':lib}
    files['manifest.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as t:
        for n,b in files.items():
            m=tarfile.TarInfo(n);m.size=len(b);m.mode=0o700 if n.endswith('.sh') else 0o600;t.addfile(m,io.BytesIO(b))
    archive=stream.getvalue();OUT.mkdir(exist_ok=True)
    (OUT/'probe.tgz').write_bytes(archive)
    record={'archiveSha256':sha(archive),'archiveBytes':len(archive),'scriptSha256':sha(script),'librarySha256':sha(lib),'permanentInstalled':False}
    (OUT/'package.json').write_text(json.dumps(record,indent=2)+'\n')
    return archive,record
def run():
    data,report=prepare();s=session.Session('boot-transport-readonly-probe');seen=set()
    def cmd(label,command):
        assert label not in seen and 0<len(command.encode('ascii'))<=231 and '\n' not in command,(label,len(command))
        seen.add(label);return s.command(label,command)['output'].strip()
    def save(stage):
        report.update(stage=stage,session=s.summary())
        (OUT/'installation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'stage':stage,'linuxRequests':s.summary()['requests']}),flush=True)
    try:
        cmd('health','/tmp/hbl-wireless-flash/formal-system-check --require-ui-stage')
        cmd('fresh','r='+REMOTE+';test ! -e "$r" && test ! -L "$r"')
        before=install_candidate.audit();(OUT/'preservation-before.json').write_text(json.dumps(before,indent=2)+'\n')
        save('existing-ram-verified')
        cmd('mkdir','umask 077;mkdir -m 700 '+REMOTE)
        decoder=session.transport.DECODER
        for i,start in enumerate(range(0,len(decoder),90)):
            cmd('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+90])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
        encoded=base64.b64encode(data).decode()
        for i,start in enumerate(range(0,len(encoded),160)):
            cmd('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(encoded[start:start+160])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
        cmd('decode-once','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/probe.tgz";sha256sum "$r/probe.tgz" >"$r/decoded.sha") </dev/null >/dev/null 2>&1 &')
        save('transferred-decoding')
        for i in range(60):
            time.sleep(1)
            r=cmd('decode-'+str(i),'r='+REMOTE+';if test -f "$r/decoded.sha";then cat "$r/decoded.sha";else printf pending;fi')
            if r!='pending':break
        assert r.split()[0]==report['archiveSha256'],r
        cmd('extract','cd '+REMOTE+' && tar xzf probe.tgz && sha256sum -c manifest.sha256 >/dev/null && sh -n probe.sh')
        cmd('dispatch-once','r='+REMOTE+';test ! -e "$r/dispatched" && touch "$r/dispatched" && (cd "$r";sh probe.sh >probe.log 2>&1;echo $? >exit) </dev/null >/dev/null 2>&1 &')
        save('probe-dispatched-once')
        for i in range(150):
            time.sleep(1)
            r=cmd('observe-'+str(i),'r='+REMOTE+';if test -f "$r/exit";then cat "$r/exit";test ! -f "$r/result" || cat "$r/result";else printf pending;fi')
            if r!='pending':break
        else:raise RuntimeError('probe still pending; never redispatch')
        report['deviceResult']=r
        report['transportResult']=cmd('transport-result','cat '+REMOTE+'/transport-result.txt')
        if r.splitlines()!=['0','readonly-probe-ready-original-restored']:
            raise RuntimeError('probe failed; inspect restoration record without redispatch')
        after=install_candidate.audit();(OUT/'preservation-after.json').write_text(json.dumps(after,indent=2)+'\n')
        report['passed']=True;report['afAndFlashPreserved']=True;save('readonly-probe-passed-original-restored')
    except BaseException as e:
        report['error']=str(e);save('stopped-for-review');raise
if __name__=='__main__':
    if sys.argv[1:]==['--prepare']:print(json.dumps(prepare()[1]))
    elif sys.argv[1:]==['--run']:run()
    else:raise SystemExit('select --prepare or --run')
