"""默认离线核验；--stage/--phase/--observe 仅供独占相机的主任务显式调用。"""
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,importlib.util,json,shlex,sys,time
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('ui_resident_session_package',Path(__file__).with_name('package.py'))
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
ROOT=package.ROOT;OUT=package.OUT;HERE=package.HERE
REMOTE='/tmp/hbl-ui-resident'
TRANSPORT=ROOT/'x1d/wireless-flash/research/mechanical_sync_session.py'
TRANSPORT_SHA='2ebbadf244613f64641266342679743b172899555ff6757f9cfded523433528a'
# 已验证 BusyBox 兼容算法；用 od -v -c 分行，避免巨大单行 awk。
DECODER='BEGIN{s="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"}{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="=")break;v=index(s,c)-1;if(v<0)continue;b=b*64+v;n+=6;if(n>=8){n-=8;o=int(b/2^n);b%=2^n;printf "\\\\%03o",o}}}'
MARKERS={'preflight':'ui-resident-preflight-ready','ui':'ui-resident-session-ready','status':'ui-resident-session-ready','restore':'ui-resident-original-restored'}
def bounded(command):
    data=command.encode('ascii')
    if not 1<=len(data)<=231 or b'\n' in data or b'\0' in data:raise ValueError('command frame size')
    return command
def decoder_script():
    return "set -eu;r="+REMOTE+";trap 'echo $? >\"$r/decode.exit\"' 0;test ! -e \"$r/session.tar.gz\";printf '%b' \"$(/usr/bin/od -v -c \"$r/p64\" | /bin/sed 's/^[0-7]* *//' | awk -f \"$r/d.awk\")\" >\"$r/session.tar.gz\";sha256sum \"$r/session.tar.gz\" >\"$r/decode.sha\""
def stage(session,report,data,pause=time.sleep):
    if package.digest(data)!=report['packageSha256'] or len(data)!=report['bytes']:raise ValueError('package identity')
    def call(n,c):return session.command(n,bounded(c))['output']
    out=call('services','systemctl is-active victory-gui msg2dbus-farm configstore jpeg-daemon storage-daemon')
    if out.split()!=['active']*5:raise RuntimeError('original services not active')
    call('stage-new','r='+REMOTE+';umask 077;test ! -e "$r" && test ! -L "$r" && mkdir -m 700 "$r" "$r/phases"')
    helper=decoder_script()
    for name,body in [('d.awk',DECODER),('decode.sh',helper)]:
        for i,start in enumerate(range(0,len(body),64)):
            call(name+'-'+str(i),'printf %s '+shlex.quote(body[start:start+64])+(' >' if i==0 else ' >>')+REMOTE+'/'+name)
        if call(name+'-hash','sha256sum '+REMOTE+'/'+name).split()[0]!=package.digest(body.encode()):raise RuntimeError('helper digest')
    encoded=base64.b64encode(data).decode()
    for i,start in enumerate(range(0,len(encoded),176)):
        call('chunk-'+str(i),'printf %s '+shlex.quote(encoded[start:start+176])+(' >' if i==0 else ' >>')+REMOTE+'/p64')
        if (i+1)%100==0:print(json.dumps({'stage':'transfer','chunks':i+1,'total':(len(encoded)+175)//176}),flush=True)
    if call('encoded-hash','sha256sum '+REMOTE+'/p64').split()[0]!=package.digest(encoded.encode()):raise RuntimeError('encoded digest')
    call('decode-once','r='+REMOTE+';(sh "$r/decode.sh" >"$r/decode.log" 2>&1) </dev/null >/dev/null 2>&1 &')
    for i in range(90):
        pause(1)
        out=call('decode-observe-'+str(i),'r='+REMOTE+';if test -f "$r/decode.exit";then cat "$r/decode.exit";cat "$r/decode.sha";else printf pending;fi').strip()
        if out!='pending':break
    else:raise RuntimeError('decode unknown; do not repeat')
    if out.split()[0:2]!=['0',report['packageSha256']]:raise RuntimeError('archive digest; extraction refused')
    out=call('extract-once','cd '+REMOTE+' && tar xzf session.tar.gz && sha256sum -c manifest.sha256 >/dev/null && sh -n run.sh && printf ui-package-verified')
    if out!='ui-package-verified':raise RuntimeError('package extraction verification')
    return {'staged':True,'packageSha256':report['packageSha256']}
def observe(session,name):
    if name not in MARKERS or name=='status':raise ValueError('phase')
    return session.command(name+'-observe',bounded('r='+REMOTE+';p='+name+';if test -f "$r/phases/$p.exit";then cat "$r/phases/$p.exit";tail -n 1 "$r/phases/$p.log";else printf pending;fi'))['output'].strip()
def phase(session,name,pause=time.sleep):
    if name not in MARKERS or name in session.dispatched:raise ValueError('unknown or duplicate phase')
    session.dispatched.add(name)
    if name=='status':
        out=session.command('status',bounded('sh '+REMOTE+'/run.sh status'))['output'].strip()
        if out!=MARKERS[name]:raise RuntimeError('status failed: '+out)
        return out
    session.command(name+'-once',bounded('r='+REMOTE+';p='+name+';test ! -e "$r/phases/$p.sent" && (sh "$r/run.sh" "$p" >"$r/phases/$p.log" 2>&1) </dev/null >/dev/null 2>&1 &'))
    for i in range(90):
        pause(1);out=observe(session,name)
        if out!='pending':break
    else:raise RuntimeError('phase outcome unknown; observe only, do not repeat')
    if out.splitlines()!=['0',MARKERS[name]]:raise RuntimeError('phase failure: '+out)
    return out
class Session:
    def __init__(self,label):
        if package.build.sha(TRANSPORT)!=TRANSPORT_SHA:raise ValueError('transport source changed')
        spec=importlib.util.spec_from_file_location('ui_reviewed_linux_transport',TRANSPORT)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        # 只改变本实例的证据根；不写来源模块的任何文件。
        mod.HERE=package.build.CANDIDATE
        self.transport=mod.Session;self.parts=[];self.dispatched=set();self.failed=False
        self.directory=OUT/'sessions'/(label+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        self.directory.mkdir(parents=True,exist_ok=False)
    def command(self,label,command):
        bounded(command)
        if self.failed:raise RuntimeError('session stopped; no retry')
        if not self.parts or len(self.parts[-1].entries)>=64:
            p=self.transport(self.directory.name+'-'+str(len(self.parts))+'.json')
            p.output=self.directory/(str(len(self.parts)).zfill(4)+'.json');self.parts.append(p)
        try:return self.parts[-1].command(label,command,15000)
        except BaseException:self.failed=True;raise
    def summary(self):
        entries=[v for p in self.parts for v in p.entries]
        return {'requests':sum(v['submitted'] for v in entries),'allHandlesClosed':all(v['closed'] for v in entries),
            'failed':self.failed,'dispatched':sorted(self.dispatched),'farmRequests':0,'busRestarts':0}
def main(args):
    report,data=package.verify()
    if not args:
        print(json.dumps({'readyForRootStaging':True,'archive':report['archive'],'packageSha256':report['packageSha256'],
            'targetValidated':False,'hardwareRequests':0}));return
    if args!=['--stage'] and not (len(args)==2 and args[0] in ('--phase','--observe') and args[1] in MARKERS):raise ValueError('usage: --stage | --phase preflight/ui/status/restore | --observe preflight/ui/restore')
    name='stage' if args==['--stage'] else args[1]
    session=Session(name);state={'completed':False,'packageSha256':report['packageSha256'],'operation':args}
    try:
        if name=='stage':state.update(stage(session,report,data))
        else:
            out=session.command('manifest-identity','sha256sum '+REMOTE+'/manifest.sha256')['output']
            if out.split()[0]!=report['files']['manifest.sha256']:raise ValueError('remote package changed')
            state['result']=observe(session,name) if args[0]=='--observe' else phase(session,name)
        state['completed']=True
    except BaseException as error:state['failure']=str(error);raise
    finally:
        state.update(session.summary());package.build.save(session.directory/'result.json',state)
        print(json.dumps(state),flush=True)
if __name__=='__main__':main(sys.argv[1:])
