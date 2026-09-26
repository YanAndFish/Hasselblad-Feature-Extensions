"""只恢复已逐字前缀核对的文件上传；不恢复服务、FARM 或 AF 事务。"""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import build_package
import transfer

def prefix_position(encoded, confirmed, attempted, size, digest):
    if attempted!=confirmed or confirmed<0:raise ValueError('only last submitted chunk may be ambiguous')
    boundaries={min(confirmed*176,len(encoded)),min((attempted+1)*176,len(encoded))}
    if size not in boundaries or hashlib.sha256(encoded[:size].encode('ascii')).hexdigest()!=digest:
        raise ValueError('target is not an exact allowed prefix; no write')
    return (size+175)//176

def local_prefix(staged_path, report):
    staged_path=Path(staged_path).resolve()
    if not staged_path.is_relative_to(transfer.HERE/'build/sessions') or staged_path.name!='stage.json':raise ValueError('fixed staging record')
    state=json.loads(staged_path.read_text(encoding='utf-8'))
    if state.get('staged') is not False or not state.get('failed') or state.get('allHandlesClosed') is not True or state.get('dispatched') or state.get('packageSha256')!=report['packageSha256']:
        raise ValueError('only failed file-only staging may be inspected')
    entries=[]
    for path in sorted(staged_path.parent.glob('[0-9]*.json')):entries+=json.loads(path.read_text(encoding='utf-8'))['entries']
    chunks=[e for e in entries if e['label'].startswith('chunk-')]
    if not chunks or entries[-1] is not chunks[-1]:raise ValueError('failure must be final file chunk')
    for index,entry in enumerate(chunks):
        if entry['label']!='chunk-'+str(index) or entry['submitted']!=1 or not entry['closed']:raise ValueError('staging sequence or closure')
        if index<len(chunks)-1 and (not entry.get('matched') or entry.get('exit_code')!=0):raise ValueError('earlier chunk unknown')
    if chunks[-1].get('matched') or not chunks[-1].get('error'):raise ValueError('last chunk must be unresolved')
    return len(chunks)-1

def resume(staged_path):
    report,data=build_package.verify();attempted=local_prefix(staged_path,report)
    encoded=base64.b64encode(data).decode('ascii')
    session=transfer.Session('stage-reconciled')
    state={'staged':False,'packageSha256':report['packageSha256'],'sourceStaging':str(Path(staged_path).resolve().relative_to(transfer.ROOT)),
           'servicesRestarted':False,'farmRequests':0,'shots':0,'flashTrials':0,'ambiguousChunkResent':False}
    try:
        r=transfer.REMOTE
        session.command('private-staging','r='+r+';set -e;test ! -e "$r/install-state";test ! -L "$r";test ! -L "$r/p64";test "$(stat -c %u:%a "$r")" = 0:700;test "$(stat -c %u:%h "$r/p64")" = 0:1')
        result=session.command('read-prefix','r='+r+';set -e;wc -c <"$r/p64";sha256sum "$r/p64";systemctl is-active victory-gui msg2dbus-farm')
        lines=result['output'].splitlines()
        if len(lines)!=4 or lines[-2:]!=['active','active']:raise ValueError('prefix observation incomplete')
        size=int(lines[0]);digest=lines[1].split()[0]
        start=prefix_position(encoded,attempted,attempted,size,digest)
        state.update(verifiedPrefixBytes=size,verifiedPrefixSha256=digest,nextChunk=start)
        print(json.dumps({'stage':'exact-prefix-reconciled','nextChunk':start,'attemptedChunk':attempted}),flush=True)
        parts=[encoded[n:n+176] for n in range(0,len(encoded),176)]
        for index in range(start,len(parts)):
            session.command('chunk-'+str(index),'printf %s '+shlex.quote(parts[index])+' >>'+r+'/p64')
            if (index+1)%100==0:print(json.dumps({'stage':'transfer','chunks':index+1,'total':len(parts)}),flush=True)
        result=session.command('complete-encoded-check','r='+r+';wc -c <"$r/p64";sha256sum "$r/p64"')
        lines=result['output'].splitlines()
        if len(lines)!=2 or int(lines[0])!=len(encoded) or lines[1].split()[0]!=hashlib.sha256(encoded.encode()).hexdigest():raise ValueError('final encoded transfer changed')
        session.command('decode-once','r='+r+';(printf \'%b\' "$(awk -f "$r/d.awk" "$r/p64")" >"$r/combined.tar.gz";sha256sum "$r/combined.tar.gz" >"$r/decode.sha") </dev/null >/dev/null 2>&1 &')
        for attempt in range(120):
            time.sleep(1)
            result=session.command('decode-observe-'+str(attempt),'r='+r+';if test -f "$r/decode.sha";then cat "$r/decode.sha";else printf pending;fi')
            if result['output']!='pending':break
        else:raise RuntimeError('decode pending; do not repeat')
        if result['output'].split()[0]!=report['packageSha256']:raise ValueError('decoded archive changed')
        result=session.command('extract-once','cd '+r+' && tar xzf combined.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf combined-package-verified')
        if result['output']!='combined-package-verified':raise RuntimeError('extraction failed')
        state['staged']=True
    finally:
        state.update(session.summary())
        (session.directory/'stage.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(state,ensure_ascii=True),flush=True)

def test():
    data='a'*176+'b'*176+'c'*176
    for size,wanted in ((176,1),(352,2)):
        assert prefix_position(data,1,1,size,hashlib.sha256(data[:size].encode()).hexdigest())==wanted
    for size,digest in ((177,hashlib.sha256(data[:177].encode()).hexdigest()),(352,'0'*64),(528,hashlib.sha256(data.encode()).hexdigest())):
        try:prefix_position(data,1,1,size,digest)
        except ValueError:pass
        else:raise AssertionError('unverified prefix accepted')
    print(json.dumps({'passed':True,'checks':5,'hardwareRequests':0}))

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--resume-verified-prefix':resume(sys.argv[2])
    elif len(sys.argv)==1:test()
    else:raise SystemExit('No action')
