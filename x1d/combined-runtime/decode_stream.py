"""处理大暂存文件的分行解码；仅替换本轮已明确识别的解码进程。"""
from pathlib import Path
import base64
import hashlib
import json
import shlex
import sys
import time
import build_package
import transfer

def script(old_pid,encoded_sha,archive_sha,classic=False):
    if type(old_pid)!=int or old_pid<=1:raise ValueError('observed decoder PID required')
    for value in (encoded_sha,archive_sha):
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('digest')
    if classic:
        return '''#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-x1d-combined
test ! -e "$r/install-state"
test ! -d /proc/@PID@
test "$(cat "$r/stream.exit")" = 1
test "$(wc -c < "$r/stream.tar.gz")" = 0
test ! -L "$r"
test "$(stat -c %u:%a "$r")" = 0:700
test ! -L "$r/p64"
test "$(stat -c %u:%h "$r/p64")" = 0:1
test "$(sha256sum "$r/p64" | cut -d' ' -f1)" = @ENCODED@
test ! -e "$r/stream2.tar.gz"
test ! -L "$r/stream2.tar.gz"
printf '%b' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" > "$r/stream2.tar.gz"
test "$(sha256sum "$r/stream2.tar.gz" | cut -d' ' -f1)" = @ARCHIVE@
cd "$r"
tar xzf stream2.tar.gz
sha256sum -c manifest.sha256 >/dev/null
sh -n run.sh
printf 'combined-package-verified\\n'
'''.replace('@PID@',str(old_pid)).replace('@ENCODED@',encoded_sha).replace('@ARCHIVE@',archive_sha)
    return '''#!/bin/sh
set -eu
umask 077
r=/tmp/hbl-x1d-combined
test ! -e "$r/install-state"
test ! -L "$r"
test "$(stat -c %u:%a "$r")" = 0:700
test ! -L "$r/p64"
test "$(stat -c %u:%h "$r/p64")" = 0:1
test "$(sha256sum "$r/p64" | cut -d' ' -f1)" = @ENCODED@
test ! -e "$r/stream.tar.gz"
test ! -L "$r/stream.tar.gz"
if test -d /proc/@PID@;then
    owner=$(tr '\\000' ' ' </proc/@PID@/cmdline)
    test "$owner" = 'awk -f /tmp/hbl-x1d-combined/d.awk /tmp/hbl-x1d-combined/p64 '
    kill -TERM @PID@
    for n in 1 2 3 4 5 6 7 8 9 10;do test ! -d /proc/@PID@ && break;sleep 1;done
    test ! -d /proc/@PID@
    # od 对 base64 ASCII 输入逐行显示字符；原解码器忽略空白，位累加跨行保持。
    printf '%b' "$(/usr/bin/od -An -v -t c "$r/p64" | awk -f "$r/d.awk")" > "$r/stream.tar.gz"
else
    test "$(sha256sum "$r/combined.tar.gz" | cut -d' ' -f1)" = @ARCHIVE@
    cp "$r/combined.tar.gz" "$r/stream.tar.gz"
fi
test "$(sha256sum "$r/stream.tar.gz" | cut -d' ' -f1)" = @ARCHIVE@
cd "$r"
tar xzf stream.tar.gz
sha256sum -c manifest.sha256 >/dev/null
sh -n run.sh
printf 'combined-package-verified\\n'
'''.replace('@PID@',str(old_pid)).replace('@ENCODED@',encoded_sha).replace('@ARCHIVE@',archive_sha)

def finish(old_pid,classic=False):
    report,data=build_package.verify()
    encoded_sha=hashlib.sha256(base64.b64encode(data)).hexdigest()
    body=script(old_pid,encoded_sha,report['packageSha256'],classic)
    tag='stream2' if classic else 'stream'
    session=transfer.Session('stage-stream-decoded')
    (session.directory/'stream.sh').write_text(body,encoding='utf-8',newline='\n')
    state={'staged':False,'packageSha256':report['packageSha256'],'servicesRestarted':False,'farmRequests':0,
           'shots':0,'flashTrials':0,'decoderScriptSha256':hashlib.sha256(body.encode()).hexdigest(),
           'encodedSha256':encoded_sha,'observedOwnedDecoder':old_pid,'decoderMode':tag}
    try:
        r=transfer.REMOTE
        session.command('new-helper-path','r='+r+';p='+tag+';test ! -e "$r/$p.sh" && test ! -L "$r/$p.sh" && test ! -e "$r/$p.sent" && test ! -L "$r/$p.sent"')
        encoded=base64.b64encode(body.encode()).decode()
        for index,start in enumerate(range(0,len(encoded),176)):
            session.command('helper-'+str(index),'printf %s '+shlex.quote(encoded[start:start+176])+(' >' if index==0 else ' >>')+r+'/'+tag+'64')
        session.command('decode-helper-once','r='+r+';p='+tag+';printf \'%b\' "$(awk -f "$r/d.awk" "$r/${p}64")" >"$r/$p.sh"')
        result=session.command('helper-hash','sha256sum '+r+'/'+tag+'.sh')
        if result['output'].split()[0]!=state['decoderScriptSha256']:raise RuntimeError('helper changed')
        session.command('stream-once','r='+r+';p='+tag+';umask 077;set -C;: >"$r/$p.sent" && (sh "$r/$p.sh" >"$r/$p.log" 2>&1;echo $? >"$r/$p.exit") </dev/null >/dev/null 2>&1 &')
        for index in range(90):
            time.sleep(1)
            result=session.command('stream-observe-'+str(index),'r='+r+';p='+tag+';if test -f "$r/$p.exit";then cat "$r/$p.exit";tail -n 1 "$r/$p.log";else printf pending;fi')
            if result['output']!='pending':break
        else:raise RuntimeError('stream helper outcome unknown; no repeat')
        state['decodeOutcome']=result['output']
        if result['output'].splitlines()!=['0','combined-package-verified']:raise RuntimeError('stream decode failed')
        state['staged']=True
    finally:
        state.update(session.summary())
        (session.directory/'stage.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(state,ensure_ascii=True),flush=True)

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--finish-owned-decoder':finish(int(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--finish-classic-decoder':finish(int(sys.argv[2]),True)
    else:print(json.dumps({'hardwareRequests':0,'requires':'verified current owned decoder'}))
