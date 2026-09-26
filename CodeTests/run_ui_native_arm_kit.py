"""仅运行两个固定的目标Qt纯UI测试包；无拍摄/对焦/照片接口。"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,re,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/tools')]
from usb_transport import Channel
from installer import upload
from failure_details import HEX_AWK

def read_file(channel,remote,name):
    assert name in ('result.json','failure.json','out')
    size=int(channel.command('wc -c <'+remote+'/'+name))
    if not 0<size<=(1024*1024 if name=='out' else 65536):raise RuntimeError('Invalid test report size')
    # Keep exact JSON evidence, but only transfer the end of verbose crash
    # checkpoints. Their final case/event is useful; replaying every earlier
    # successful event over this 64-byte interface can take several minutes.
    start=max(0,size-8192) if name=='out' else 0
    data=bytearray()
    for offset in range(start,size,64):
        value=channel.command("LC_ALL=C awk '"+HEX_AWK+"' a="+str(offset)+' '+remote+'/'+name)
        if not value.startswith('H:'):raise RuntimeError('Invalid report read chunk')
        data.extend(bytes.fromhex(value[2:]))
    length=size-start
    if len(data)<length or len(data)>length+1:raise RuntimeError('Report length mismatch')
    if start:
        header=('[Diagnostic tail; omitted '+str(start)+' bytes from '+str(size)+' byte log]\n').encode()
        return header+data[:length].decode('utf-8',errors='replace').encode('utf-8')
    return data[:length]

def main():
    assert Path.cwd().resolve()==ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kit',choices=['page-pool','settings-rules'])
    parser.add_argument('--read',action='store_true')
    args=parser.parse_args();out=ROOT/'x1d/wifi-region/temporary-ui/build'/(args.kit+'-native')
    path=out/'run.json';channel=Channel()
    if args.read:
        state=json.loads(path.read_text());remote=state['remote']
        assert re.fullmatch('/tmp/hbl-uir-[0-9]{12}',remote)
    else:
        build=json.loads((out/'build.json').read_text())
        data=(out/'test.tgz').read_bytes()
        assert hashlib.sha256(data).hexdigest()==build['files']['test.tgz']
        remote='/tmp/hbl-uir-'+datetime.now().strftime('%y%m%d%H%M%S')
        state={'remote':remote,'kit':args.kit,'build':build,'cameraBusinessRequests':0,'dispatchAttempted':False}
        for name in ['target-result.json','target-failure.json','target-out','validation.json']:(out/name).unlink(missing_ok=True)
        path.write_text(json.dumps(state,indent=2))
        upload(channel,remote,data,'test.tgz')
        state['dispatchAttempted']=True;path.write_text(json.dumps(state,indent=2))
        command='r='+remote+';tar xzf "$r/test.tgz" -C "$r" && chmod 700 "$r/runner" && (LD_PRELOAD= "$r/runner" "$r" >"$r/out" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &'
        channel.command(command)
    with channel.session():
        for _ in range(100):
            status=channel.command('r='+remote+';if test -s "$r/exit";then cat "$r/exit";else echo pending;fi')
            if status!='pending':break
            time.sleep(1)
        else:raise RuntimeError('Test still pending; inspect result without redispatch')
        state['exitCode']=int(status)
        for name in ['result.json','failure.json','out']:
            if channel.command('test -s '+remote+'/'+name+' && echo yes || echo no')=='yes':
                (out/('target-'+name)).write_bytes(read_file(channel,remote,name))
        state['guiServiceAfter']=channel.command('systemctl is-active victory-gui;true')
    state['transportRequests']=channel.requests;path.write_text(json.dumps(state,indent=2))
    if (out/'target-result.json').exists():
        result=json.loads((out/'target-result.json').read_text())
        brief={name:result[name] for name in ('passed','qtVersion','cases','records','assertions','elapsedMs','forcedGcInterval','translationAssertions') if name in result}
        if 'microbenchmark' in result:
            brief['microbenchmark']={name:{key:value for key,value in row.items() if key!='samples'}
                                     for name,row in result['microbenchmark'].items() if isinstance(row,dict)}
        print(json.dumps(brief,ensure_ascii=False))
        if state['exitCode']==0 and result['passed']:
            assert result['qtVersion']=='5.5.1' and result['cameraRequests']==0
            build=json.loads((out/'build.json').read_text())
            assert state['build']['files']==build['files']
            sources=build.get('sources',{})
            assert sources,'Source binding needed before accepting regression'
            for name,digest in sources.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
            result.update(sources=sources,files=build['files'],guiServiceAfter=state['guiServiceAfter'],cameraBusinessRequests=0)
            (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    elif (out/'target-out').exists():print((out/'target-out').read_text())
    print(json.dumps({k:state[k] for k in ('kit','exitCode','guiServiceAfter','transportRequests','cameraBusinessRequests')}))
    return state['exitCode']

if __name__=='__main__':raise SystemExit(main())
