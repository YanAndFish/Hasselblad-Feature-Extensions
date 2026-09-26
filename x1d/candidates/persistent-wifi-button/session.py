"""独占设备的本轮传输；未知结果停止，不自动重发。"""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,importlib.util,json,shlex,sys,time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'build'
REMOTE='/tmp/hbl-wifi-probe-stage-r4'
TRANSPORT=ROOT/'x1d/wireless-flash/research/mechanical_sync_session.py'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def bounded(cmd):
    assert 0<len(cmd.encode('ascii'))<=231 and '\n' not in cmd and '\0' not in cmd
    return cmd
def transfer(s,report,data,pause=time.sleep):
    assert sha(data)==report['packageSha256'] and len(data)==report['bytes']
    helper=load('wifi_probe_decoder_reference',ROOT/'x1d/candidates/ui-resident/session/delivery.py');helper.REMOTE=REMOTE
    def call(n,c):return s.command(n,bounded(c))['output'].strip()
    assert call('services','systemctl is-active victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon').split()==['active']*5
    call('new-stage','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r" "$r/phases"')
    for name,body in [('d.awk',helper.DECODER),('decode.sh',helper.decoder_script())]:
        for i,start in enumerate(range(0,len(body),64)):
            call(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+64])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        assert call(name+'-hash','sha256sum '+REMOTE+'/'+name).split()[0]==sha(body.encode())
    encoded=base64.b64encode(data).decode()
    for i,start in enumerate(range(0,len(encoded),128)):
        call('chunk-'+str(i),'printf %s '+shlex.quote(encoded[start:start+128])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
    assert call('encoded-hash','sha256sum '+REMOTE+'/p64').split()[0]==sha(encoded.encode())
    call('decode-once','r='+REMOTE+';(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
    for i in range(40):
        pause(1);result=call('decode-observe-'+str(i),'r='+REMOTE+';if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi')
        if result!='pending':break
    else:raise RuntimeError('Decoder result unknown; do not repeat')
    assert result.split()[0:2]==['0',report['packageSha256']]
    assert call('extract-once','cd '+REMOTE+' && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf probe-package-verified')=='probe-package-verified'
    return {'staged':True}
class Session:
    def __init__(self,label):
        assert sha(TRANSPORT.read_bytes())=='2ebbadf244613f64641266342679743b172899555ff6757f9cfded523433528a'
        m=load('wifi_probe_transport',TRANSPORT);m.HERE=HERE
        name=label+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json'
        self.s=m.Session(name);folder=OUT/'sessions';folder.mkdir(exist_ok=True);self.s.output=folder/name
    def command(self,n,c):return self.s.command(n,bounded(c),15000)
    def summary(self):return {'requests':sum(x['submitted'] for x in self.s.entries),'closed':all(x['closed'] for x in self.s.entries),'failed':self.s.failed,'cameraFileWrites':'temporary scope only'}
def main():
    assert Path.cwd().resolve()==ROOT
    report=json.loads((OUT/'current.json').read_text());data=Path(report['archive']).read_bytes();assert sha(data)==report['packageSha256']
    args=sys.argv[1:]
    if not args:print(json.dumps({'offline':True,'package':report['packageSha256']}));return
    if args==['--stage']:
        s=Session('stage');print(json.dumps(transfer(s,report,data)));print(json.dumps(s.summary()));return
    assert len(args)==2 and args[0] in ('--phase','--observe') and args[1] in ('preflight','temporary','status','restore','archive-runtime')
    phase=args[1];s=Session(phase)
    value=s.command('manifest','sha256sum '+REMOTE+'/manifest.sha256')['output'].split()[0];assert value==report['files']['manifest.sha256']
    if phase in ('preflight','status','archive-runtime'):
        assert args[0]=='--phase'
        print(json.dumps(s.command(phase,'sh '+REMOTE+'/run.sh '+phase)));print(json.dumps(s.summary()));return
    if args[0]=='--phase':
        c='r='+REMOTE+';p='+phase+';mkdir "$r/phases/$p" && (sh "$r/run.sh" "$p" >"$r/phases/$p/log" 2>&1;echo $? >"$r/phases/$p/exit") </dev/null >/dev/null 2>&1 &'
        s.command(phase+'-once',c)
    for i in range(55):
        time.sleep(1)
        c='r='+REMOTE+'/phases/'+phase+';if test -f "$r/exit";then cat "$r/exit";tail -n 1 "$r/log";else printf pending;fi'
        result=s.command('observe-'+str(i),c)['output'].strip()
        if result!='pending':break
    else:raise RuntimeError('Phase outcome unknown; observe only')
    print(json.dumps({'phase':phase,'result':result,'summary':s.summary()}))
    if result.splitlines()[0]!='0':raise RuntimeError('Phase failed; inspect own result, do not repeat')
if __name__=='__main__':main()
