"""授权的 Linux 临时文件自测；不替换启动文件、不读写 FARM、不重启。"""
from pathlib import Path
import base64
import hashlib
import io
import json
import shlex
import sys
import tarfile
import time
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[3]
assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(BASE.parent))
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
import session
from elftools.elf.elffile import ELFFile
OUT=BASE/'build/fast-start-research'
REMOTE='/tmp/hbl-bw1'

def main():
    proof=OUT/'boot-wait-target-validation.json'
    if proof.exists():raise RuntimeError('已有尝试，先检查记录，不重复执行')
    binary=(OUT/'boot-wait').read_bytes()
    elf=ELFFile(io.BytesIO(binary))
    assert elf.elfclass==32 and elf['e_machine']=='EM_ARM'
    assert all(p['p_type']!='PT_INTERP' for p in elf.iter_segments())
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        item=tarfile.TarInfo('boot-wait');item.size=len(binary);item.mode=0o700
        archive.addfile(item,io.BytesIO(binary))
    data=stream.getvalue()
    report={'sourceSha256':hashlib.sha256((BASE/'native/boot_wait.c').read_bytes()).hexdigest(),
            'binarySha256':hashlib.sha256(binary).hexdigest(),'archiveSha256':hashlib.sha256(data).hexdigest(),
            'passed':False,'startupChanged':False,'farmRequests':0,'automaticReboots':0}
    s=session.Session('boot-wait-temporary-selftest')
    def command(label,text):
        assert len(text.encode('ascii'))<=231
        return s.command(label,text)['output'].strip()
    def save(stage):
        report.update(stage=stage,session=s.summary())
        proof.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'stage':stage,'requests':s.summary()['requests']}),flush=True)
    try:
        assert command('stable-files','sh /opt/hbl-four-module-v1/install.sh status')=='persistent-files-verified-root-readonly'
        assert command('stable-ready','cat /run/hbl-four-module/result')=='four-modules-loaded'
        report['beforePids']=command('before-pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        command('private-dir','umask 077;test ! -e '+REMOTE+' && test ! -L '+REMOTE+' && mkdir -m 700 '+REMOTE)
        save('temporary-directory-created')
        decoder=session.transport.DECODER
        for i,start in enumerate(range(0,len(decoder),90)):
            command('decoder-'+str(i),'printf %s '+shlex.quote(decoder[start:start+90])+(' >' if i==0 else ' >>')+REMOTE+'/d.awk')
        encoded=base64.b64encode(data).decode()
        for i,start in enumerate(range(0,len(encoded),170)):
            command('chunk-'+str(i),"printf '%s\\n' "+shlex.quote(encoded[start:start+170])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
        command('decode','r='+REMOTE+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/p.tgz";sha256sum "$r/p.tgz" >"$r/decoded") </dev/null >/dev/null 2>&1 &')
        save('transferred')
        for i in range(30):
            time.sleep(1)
            value=command('decode-check-'+str(i),'r='+REMOTE+';if test -f "$r/decoded";then cat "$r/decoded";else echo pending;fi')
            if value!='pending':break
        assert value.split()[0]==report['archiveSha256']
        command('extract','cd '+REMOTE+' && tar xzf p.tgz')
        assert command('binary-hash','sha256sum '+REMOTE+'/boot-wait').split()[0]==report['binarySha256']
        report['selftest']=command('selftest',REMOTE+'/boot-wait --selftest')
        assert report['selftest'].startswith('boot-wait-selftest passed=1 notificationMs=')
        command('existing-loader-state',REMOTE+'/boot-wait --loader')
        report['afterPids']=command('after-pids','systemctl show -p MainPID victory-gui msg2dbus-farm')
        assert report['afterPids']==report['beforePids']
        assert command('unchanged-stable','sh /opt/hbl-four-module-v1/install.sh status')=='persistent-files-verified-root-readonly'
        report['passed']=True
        save('temporary-selftest-passed-stable-unchanged')
    except BaseException as error:
        report['error']=str(error);save('stopped-for-review');raise

if __name__=='__main__':
    if sys.argv[1:]!=['--run']:raise SystemExit('需要显式 --run；只执行临时文件自测')
    main()
