"""已获授权的独立 RAM 回归；不安装补丁、不重启界面、不调用相机业务接口。"""
from pathlib import Path
from datetime import datetime
import hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parents[1]/'build/flash-native-arm-regression'
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'x1d/patch-distribution'),str(ROOT/'x1d/tools')]
from usb_transport import Channel
from installer import upload
from failure_details import HEX_AWK

def read_file(channel,remote,name):
    size=int(channel.command('wc -c <'+remote+'/'+name))
    if not 0<size<=65536:raise RuntimeError('Invalid test report size')
    data=b''
    for offset in range(0,size,64):
        command="LC_ALL=C awk '"+HEX_AWK+"' a="+str(offset)+' '+remote+'/'+name
        text=channel.command(command)
        if not text.startswith('H:'):raise RuntimeError('Invalid test report chunk')
        data+=bytes.fromhex(text[2:])
    if len(data)<size or len(data)>size+1:raise RuntimeError('Test report read length mismatch')
    return data[:size]

def main():
    assert Path.cwd().resolve()==ROOT
    state_path=OUT/'run.json'
    channel=Channel()
    if '--read' in sys.argv:
        state=json.loads(state_path.read_text());remote=state['remote']
    else:
        remote='/tmp/hbl-fnr-'+datetime.now().strftime('%y%m%d%H%M%S')
        data=(OUT/'test.tgz').read_bytes()
        state={'remote':remote,'archiveSha256':hashlib.sha256(data).hexdigest(),'dispatched':False,'cameraBusinessRequests':0}
        state['build']=json.loads((OUT/'build.json').read_text())
        assert state['archiveSha256']==state['build']['files']['test.tgz']
        for name in ['target-result.json','target-failure.json','target-out']:
            (OUT/name).unlink(missing_ok=True)
        state_path.write_text(json.dumps(state,indent=2))
        upload(channel,remote,data,'test.tgz')
        command='r='+remote+';tar xzf "$r/test.tgz" -C "$r" && chmod 700 "$r/runner" && (LD_PRELOAD= "$r/runner" "$r" >"$r/out" 2>&1;echo $? >"$r/exit") </dev/null >/dev/null 2>&1 &'
        state['dispatchAttempted']=True;state_path.write_text(json.dumps(state,indent=2))
        channel.command(command)
        state['dispatched']=True;state_path.write_text(json.dumps(state,indent=2))
    with channel.session():
        for _ in range(65):
            status=channel.command('r='+remote+';if test -f "$r/exit";then cat "$r/exit";else echo pending;fi')
            if status!='pending':break
            time.sleep(1)
        else:raise RuntimeError('Test still pending; do not redispatch')
        state['exitCode']=int(status)
        for name in ['result.json','failure.json','out']:
            available=channel.command('test -s '+remote+'/'+name+' && echo yes || echo no')
            if available=='yes':(OUT/('target-'+name)).write_bytes(read_file(channel,remote,name))
        state['guiServiceAfter']=channel.command('systemctl is-active victory-gui;true')
    state['transportRequests']=channel.requests;state_path.write_text(json.dumps(state,indent=2))
    if state['exitCode']==0:
        result=json.loads((OUT/'target-result.json').read_text())
        assert result['passed'] and state['build']['files']['test.tgz']==state['archiveSha256']
        for name,digest in state['build']['sources'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
        result.update(sources=state['build']['sources'],cameraBusinessRequests=0,archiveSha256=state['archiveSha256'],candidatePageSha256=hashlib.sha256((OUT.parent/'flash-source/FlashPage.qml').read_bytes()).hexdigest())
        (OUT/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in state.items() if k not in ('remote','archiveSha256')}))
    if state['exitCode'] in (0,1) and (OUT/'target-result.json').exists():print((OUT/'target-result.json').read_text())
    elif (OUT/'target-out').exists():print((OUT/'target-out').read_text())
    return state['exitCode']

if __name__=='__main__':raise SystemExit(main())
