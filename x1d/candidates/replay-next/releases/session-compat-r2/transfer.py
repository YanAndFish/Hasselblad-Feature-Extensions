"""给已获授权的其他会话使用的分阶段传输接口；本模块没有设备发现或连接代码。

直接运行只核对本地包。Transfer(session) 的 session 必须由执行会话显式提供，
command(label, ASCII命令) 返回 {exit_code:0, output:str, closed:True}。
每条命令最多 231 字节；任何不明确结果都会锁住此 Transfer，不重发。
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import shlex
import tarfile
import io

HERE=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent
REMOTE='/tmp/hbl-x1d-rp'
DECODER='BEGIN{s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"}{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="=")break;v=index(s,c)-1;if(v<0)continue;b=b*64+v;n+=6;if(n>=8){n-=8;o=int(b/2^n);b%=2^n;printf "\\\\%03o",o}}}'

def verify_package():
    report=json.loads((OUT/'package.json').read_text(encoding='utf-8'))
    data=(OUT/'session.tar.gz').read_bytes()
    if len(data)!=report['packageBytes'] or hashlib.sha256(data).hexdigest()!=report['packageSha256']:
        raise RuntimeError('Local archive differs from reviewed package')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        seen=set()
        for m in archive:
            if not m.isfile() or m.name not in report['files'] or m.name in seen or m.mode!=0o700:
                raise RuntimeError('Unexpected archive member')
            content=archive.extractfile(m).read()
            if hashlib.sha256(content).hexdigest()!=report['files'][m.name]:raise RuntimeError('Archive member mismatch')
            seen.add(m.name)
        if seen!=set(report['files']):raise RuntimeError('Incomplete archive')
    return report,data

HELPER='set -eu;r=/tmp/hbl-x1d-rp;trap \'c=$?;echo "$c" >"$r/decode.next";mv "$r/decode.next" "$r/decode.exit"\' 0;test ! -e "$r/session.tar.gz";printf \'%b\' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed \'s/^[0-7]* *//\' | awk -f "$r/d.awk")" >"$r/session.tar.gz";sha256sum "$r/session.tar.gz" >"$r/sha.next";mv "$r/sha.next" "$r/decode.sha"'

class Transfer:
    def __init__(self,session,package=None):
        self.session=session
        self.report,self.data=verify_package() if package is None else package
        self.stopped=False;self.staged=False;self.decodeSent=False;self.sent=set();self.completed={}
    def send(self,label,command):
        if self.stopped or getattr(self.session,'failed',False):raise RuntimeError('Transfer is stopped; do not retry')
        encoded=command.encode('ascii')
        if not 1<=len(encoded)<=231 or b'\0' in encoded or b'\n' in encoded:raise ValueError('Frame bound exceeded')
        try:
            r=self.session.command(label,command)
            if not isinstance(r,dict) or r.get('exit_code')!=0 or r.get('closed') is not True or not isinstance(r.get('output'),str):
                raise RuntimeError('Unconfirmed command result')
            return r['output'].strip()
        except BaseException:
            self.stopped=True
            raise
    def upload(self,progress=None):
        if self.staged or self.decodeSent:raise RuntimeError('Upload already sent')
        self.send('replay-create',f'umask 077;test ! -e {REMOTE} && test ! -L {REMOTE} && mkdir -m 700 {REMOTE}')
        for name,body in [('d.awk',DECODER),('decode.sh',HELPER)]:
            for i,start in enumerate(range(0,len(body),70)):
                self.send(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+70])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        got=self.send('helper-hash','sha256sum '+REMOTE+'/decode.sh')
        if got.split()[:1]!=[hashlib.sha256(HELPER.encode()).hexdigest()]:
            self.stopped=True;raise RuntimeError('Helper differs; no upload')
        encoded=base64.b64encode(self.data).decode('ascii');parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
        for i,part in enumerate(parts):
            self.send('replay-chunk-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if progress and (i+1)%100==0:progress(i+1,len(parts))
        self.decodeSent=True
        self.send('replay-decode',f'r={REMOTE};(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        return {'decodeDispatched':True,'chunks':len(parts)}
    def finish_upload(self):
        if not self.decodeSent or self.staged:raise RuntimeError('No pending upload')
        out=self.send('replay-decode-result',f'r={REMOTE};if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')
        if out=='pending':return False
        if out.split()[:2]!=['0',self.report['packageSha256']]:
            self.stopped=True;raise RuntimeError('Decode failed or archive differs; extraction refused')
        out=self.send('replay-extract',f'cd {REMOTE} && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && printf replay-package-verified')
        if out!='replay-package-verified':
            self.stopped=True;raise RuntimeError('Extraction not verified')
        self.staged=True
        return True
    def dispatch(self,phase):
        options={'ui':'install.sh --stage-ui','enable':'install.sh --enable','restore':'restore.sh'}
        if not self.staged or phase not in options or phase in self.sent:raise RuntimeError('Invalid or repeated phase')
        if self.sent-set(self.completed):raise RuntimeError('A prior phase is pending; do not overlap phases')
        if phase=='enable' and self.completed.get('ui')!=0:raise RuntimeError('UI phase not confirmed')
        # 先在本地登记，丢失应答后不再次派发同一动作。
        self.sent.add(phase)
        command=f'd={REMOTE};p={phase};(set -C; : >"$d/$p.sent") || exit 1;(sh "$d/'+options[phase].split()[0]+'"'+(' '+options[phase].split(' ',1)[1] if ' ' in options[phase] else '')+' >"$d/$p.log" 2>&1;echo $? >"$d/$p.next";mv "$d/$p.next" "$d/$p.exit") </dev/null >/dev/null 2>&1 &'
        self.send('replay-'+phase+'-dispatch',command)
    def result(self,phase):
        if phase not in self.sent:raise RuntimeError('Phase was not dispatched by this transfer')
        text=self.send('replay-'+phase+'-result',f'd={REMOTE};p={phase};if test -f "$d/$p.exit";then cat "$d/$p.exit";tail -c 160 "$d/$p.log";else printf pending;fi')
        if text=='pending':return {'pending':True}
        first,*rest=text.splitlines()
        if not first.isdigit() or int(first)>255:
            self.stopped=True;raise RuntimeError('Invalid phase result; do not repeat dispatch')
        code=int(first);self.completed[phase]=code
        if code:self.stopped=True
        return {'pending':False,'exit_code':code,'detail':'\n'.join(rest)}

if __name__=='__main__':
    r,_=verify_package();print(json.dumps({'localPackageVerified':True,'bytes':r['packageBytes'],'sha256':r['packageSha256'],'cameraAccess':False}))
