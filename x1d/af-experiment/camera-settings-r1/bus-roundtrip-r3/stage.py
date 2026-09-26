"""bus-only 包传输；不发送任何 FARM 请求。"""
from pathlib import Path
import base64,hashlib,json,shlex,time
import bus_package as package
import transfer
HERE=package.HERE;ROOT=package.ROOT;REMOTE=transfer.REMOTE
def record(session,state,name):
    state.update(session.summary());(session.directory/name).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def stage():
    report,data=package.verify();session=transfer.Session('af-bus-r3-stage')
    state={'staged':False,'packageSha256':report['packageSha256'],'flashIncluded':False,'farmRequests':0}
    helper='''#!/bin/sh
set -eu
r=/tmp/hbl-af-bus-r3
trap 'result=$?;echo "$result" >"$r/decode.exit"' 0
test ! -e "$r/af-bus-r3.tar.gz"
printf '%b' "$(/usr/bin/od -v -c "$r/p64" | /bin/sed 's/^[0-7]* *//' | awk -f "$r/d.awk")" >"$r/af-bus-r3.tar.gz"
sha256sum "$r/af-bus-r3.tar.gz" >"$r/decode.sha"
'''
    helper=';'.join(helper.splitlines()[1:])
    try:
        result=session.command('original-services','systemctl is-active victory-gui msg2dbus-farm')
        if result['output'].split()!=['active','active']:raise RuntimeError('original services not active')
        session.command('create-stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r" "$r/phases"')
        for name,body in [('d.awk',transfer.DECODER),('decode.sh',helper)]:
            for i,start in enumerate(range(0,len(body),70)):
                session.command(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+70])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        result=session.command('helper-hash','sha256sum '+REMOTE+'/decode.sh')
        if result['output'].split()[0]!=hashlib.sha256(helper.encode()).hexdigest():raise RuntimeError('helper checksum')
        encoded=base64.b64encode(data).decode()
        parts=[encoded[i:i+176] for i in range(0,len(encoded),176)]
        for i,part in enumerate(parts):
            session.command('chunk-'+str(i),'printf %s '+shlex.quote(part)+(' >' if i==0 else ' >>')+REMOTE+'/p64')
            if (i+1)%100==0:print(json.dumps({'stage':'af-transfer','chunks':i+1,'total':len(parts)}),flush=True)
        session.command('decode-once','r='+REMOTE+';(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
        for i in range(90):
            time.sleep(1)
            out=session.command('decode-observe-'+str(i),'r='+REMOTE+';if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')['output'].strip()
            if out!='pending':break
        else:raise RuntimeError('decode unknown; no retry')
        if out.split()[0:2]!=['0',report['packageSha256']]:raise RuntimeError('decode checksum mismatch')
        out=session.command('extract-once','cd '+REMOTE+' && tar xzf af-bus-r3.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf af-bus-r3-package-verified')['output']
        if out!='af-bus-r3-package-verified':raise RuntimeError('extract verification')
        state['staged']=True
    finally:
        record(session,state,'stage.json');print(json.dumps(state),flush=True)
    return session.directory/'stage.json'