"""固定R4临时RAM装载器。默认report只读电脑文件；异常停止，不自动续装或清除代码。"""
import sys,os,json,struct,hashlib,argparse
from pathlib import Path
from datetime import datetime
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE/'CodeTests'),str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from r5_install_plan import InstallPlan,M,BUILD,BASE,COUNT,HOOK,BLOB,WAKE_BASE,WAKE_HOOK,WAKE_BLOB,SENT
from farm_diagnostic_binary import FarmApplication
from r3_install_journal import InstallJournal
import read_usb_link_once as usb

ARTIFACT='2fc4332a8eeab0677cbaf9791d26e79436e0b7e4adec18b27e52f2231890503d'
SCRATCH=0x2b2800;DESC=0x2b2820;CB=0x2a5074;ARG=0x2a5078
ORIG_CB=0x109304;ORIG_ARG=0x6da728;NOOP=0x1009d4
CLEAN=0x10a2d0;INVALIDATE=0x10a310;CLEAN_RANGE=0x10a270;INVALIDATE_RANGE=0x10a354
SGIR=0xf8f01f00;SELF15=0x0200000f;PENDING=0xf8f01200;ACTIVE=0xf8f01300
MAGIC=0xafaf2026
PROBE=bytes.fromhex('261002e3af1f4ae3001080e51eff2fe1')
THUNK=struct.pack('<7I',0xe92d4010,0xe1a04000,0xe8940007,0xe12fff32,0xe3a00001,0xe584000c,0xe8bd8010)
VERSIONS=['827fa74','c9bb91d','abad48d']
REQUEST_LIMIT=24000
TRANSPORT_HASHES={
    'read_usb_link_once.py':'8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3',
    'usb_diagnostic_contract.py':'80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84'}

class FixedContract:
    def __init__(self,farm):
        if Path.cwd().resolve()!=ROOT.resolve():raise ValueError('current workspace required')
        for name,digest in TRANSPORT_HASHES.items():
            if hashlib.sha256((ROOT/'x1d/tools'/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('USB transport source changed')
        if M['artifact_sha256']!=ARTIFACT:raise ValueError('unreviewed artifact')
        for name,digest in M['sources'].items():
            if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise ValueError('candidate source changed')
        self.plan=p=InstallPlan(farm)
        digest=hashlib.sha256()
        for a,blob in [(M['base'],(BUILD/'candidate.bin').read_bytes())]+[
                (item['base'],(BUILD/item['file']).read_bytes()) for item in M['segments']]:
            digest.update(struct.pack('<II',a,len(blob)));digest.update(blob)
        digest.update(json.dumps({'hooks':M['hooks'],'speed_words':M['speed_words']},
            sort_keys=True,separators=(',',':')).encode())
        if digest.hexdigest()!=ARTIFACT:raise ValueError('candidate artifact content mismatch')
        self.guards={0x2ad78c:(0xffffffff,0x2a4ffc),0x6da728:(0xffffffff,0x2a4ff0),
            0x6da72c:(0xffffffff,0x11111111),CB:(0xffffffff,ORIG_CB),ARG:(0xffffffff,ORIG_ARG),
            0x6bb46c:(255,0),0x6bb598:(255,0),0x2adc78:(0xff00,18<<8),0x2adc8c:(255,0),
            0xf8f01000:(1,1),0xf8f00100:(9,1),0xf8f01100:(0x8000,0x8000),
            PENDING:(0x8000,0),ACTIVE:(0x8000,0),0xf8f0140c:(0xff000000,0xa0000000),
            0xf8f01080:(0x8000,0)}
        self.expected=dict(p.baseline)
        self.expected.pop(0x6bb46c)  # AF状态是一个字节，邻接填充不属于状态守卫。
        self.expected.update({a:0 for a in range(SCRATCH,M['base'],4)})
        regions=[(0x100770,0x100930),(0x10a270,0x10a3ac),(0x10acac,0x10acb8),
            (0x18b034,0x18b09c),(0x1a4890,0x1a4950),(0x18a020,0x18a210),
            (0x189e4c,0x18a020),(0x19b718,0x19b77c),(0x1e1ff8,0x1e22cc),
            (0x1e1768,0x1e1888),(0x1e2524,0x1e2560)]
        for lo,hi in regions:
            for a in range(lo,hi,4):self.expected[a]=farm.word(a)
        # GFS3四个入口必须已随本次手动重启恢复；不接受其他探针仍在驻留。
        self.baseline_sites=set(p.hooks)|{WAKE_HOOK,0x21409c,0x1c4380,0x1c4458,0x1c44f4,
            0x19d198,0x1009d4,0x27b824,0x27b828}
        for a in self.baseline_sites:
            for site in range(a&~31,(a&~31)+32,4):self.expected[site]=farm.word(site)
        for a,old,new in M['speed_words']:self.expected[a]=old
        self.allowed={a:{v} for a,v in self.expected.items() if SCRATCH<=a<0x2b4000}
        for a,v in p.code.items():self.allowed.setdefault(a,set()).add(v)
        for a,v in p.baseline.items():
            if a in p.code:self.allowed[a].add(v)
        for a,v in p.helper.items():self.allowed.setdefault(a,{0}).add(v)
        for start,blob in ((SCRATCH,PROBE),(SCRATCH,THUNK)):
            for offset in range(0,len(blob),4):self.allowed[start+offset].add(struct.unpack_from('<I',blob,offset)[0])
        for a,old,new in M['hooks']+M['speed_words']:self.allowed[a]={old,new}
        self.allowed[HOOK].add(p.gate);self.allowed[WAKE_HOOK]={p.wake_original,p.wake_hook}
        self.allowed[CB]={ORIG_CB,NOOP,CLEAN,INVALIDATE,SCRATCH}
        self.allowed[ARG]={ORIG_ARG,SCRATCH,DESC};self.allowed[SGIR]={SELF15}
        self.allowed[p.af_armed].add(2);self.allowed[p.video_enabled].add(2)
        self.ranges={(a,len(blob)) for a,blob in p.uploads}|{(BASE,p.helper_size)}
        self.ranges|={(a&~31,32) for a in p.hooks}|{(WAKE_HOOK&~31,32)}
        self.allowed[DESC].update(a for a,n in self.ranges)
        self.allowed[DESC+4].update(n for a,n in self.ranges)
        self.allowed[DESC+8].update((CLEAN_RANGE,INVALIDATE_RANGE))
        self.reads=set(self.expected)|set(self.guards)|set(self.allowed)-{SGIR}
        self.reads|={0x6badd0,0x6c176c,0x6c1778,0x6c172c}
        # 主机永远不能伪造屏障ACK或一次性唤醒标志。
        self.allowed[COUNT]={0};self.allowed[SENT]={0}
        self.state_ranges=((M['symbols']['af_state'],M['stateBytes']),
                           (M['symbols']['fast_video_state'],M['fastStateBytes']))
        self.static_code={a:v for a,v in p.code.items() if not any(lo<=a<lo+n for lo,n in self.state_ranges)}
        self.digest=hashlib.sha256(json.dumps({'artifact':ARTIFACT,'helper':p.helper,
            'expected':self.expected,'guards':self.guards,'allowed':{a:sorted(v) for a,v in self.allowed.items()},
            'ranges':sorted(self.ranges)},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def packet(self,kind,a=None,v=None,size=512):
        if size not in (512,1024):raise ValueError('fixed packet size')
        if kind=='version':
            if a is not None or v is not None:raise ValueError('version arguments')
            body=bytes.fromhex('0d000801')
        elif kind=='read':
            if type(a)!=int or a not in self.reads or a%4 or v is not None:raise ValueError('fixed read denied')
            body=bytes.fromhex('f4000801')+struct.pack('<I',a)
        elif kind=='write':
            if type(a)!=int or type(v)!=int or a%4 or a not in self.allowed or v not in self.allowed[a]:
                raise ValueError('fixed write denied')
            body=bytes.fromhex('f2000801')+struct.pack('<II',a,v)
        else:raise ValueError('request kind')
        return body+bytes(size-len(body))
    @staticmethod
    def reply(kind,data,size):
        if type(data)!=bytes or len(data)!=size:raise ValueError('reply size')
        if kind=='version':
            if data[:4]!=bytes.fromhex('0e000108'):raise ValueError('version header')
            fields=[data[a:a+64].split(b'\0',1)[0] for a in (4,68,132)]
            if fields!=[v.encode('ascii') for v in VERSIONS]:raise ValueError('firmware version mismatch')
            return VERSIONS
        if data[:4]!=bytes.fromhex('f5000108' if kind=='read' else 'f3000108'):
            raise ValueError('reply header')
        if data[8 if kind=='read' else 4]!=0:raise ValueError('device rejected request')
        return struct.unpack_from('<I',data,4)[0] if kind=='read' else 0

class NativePacket(usb.NativeWinUsb):
    def __init__(self,contract,kind,a,v):
        self.contract,self.kind,self.address,self.value=contract,kind,a,v;super().__init__()
    def write_query(self,size):
        if not self.prepared or self.sent or size!=self.packet_size:raise usb.UsbFailure('USB_REQUEST_DENIED')
        packet=self.contract.packet(self.kind,self.address,self.value,size)
        buffer=usb.c.create_string_buffer(packet,size);count=usb.U32();self.sent=True
        self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buffer,size,usb.c.byref(count),None),'USB_WRITE')
        return count.value

class FixedIO:
    is_hardware=True
    def __init__(self,contract):
        self.contract=contract;self.requests=0;self.writes=0;self.closed=True;self.failed=False
        self.journal=None;self.phase='preflight';self.wake_live=False
    def transport(self,kind,a,v):return NativePacket(self.contract,kind,a,v)
    def exchange(self,kind,a=None,v=None):
        self.contract.packet(kind,a,v)
        if self.failed or self.requests>=REQUEST_LIMIT:raise RuntimeError('failed or exhausted session; no retry')
        if kind=='write' and self.journal is None:raise RuntimeError('durable recovery record required')
        operation='wake_read' if kind=='read' and a==COUNT and self.wake_live else kind
        if self.journal:self.journal.begin(self.phase,(operation,a or 0,v or 0))
        t=None
        try:
            t=self.transport(kind,a,v);size=usb.validate_interface(t.open());t.prepare()
            self.requests+=1
            if kind=='write':self.writes+=1
            if t.write_query(size)!=size:raise RuntimeError('short request write')
            result=self.contract.reply(kind,t.read_reply(size),size)
        except BaseException:self.failed=True;raise
        finally:
            if t is not None:
                self.closed=all(t.close().values())
                if not self.closed:self.failed=True;raise RuntimeError('USB handle close failed')
        if self.journal:
            self.journal.record.update({'requests':self.requests,'writeRequests':self.writes,
                'hardwareRequests':self.requests if self.is_hardware else 0,'allHandlesClosed':self.closed})
            try:self.journal.complete()
            except BaseException:self.failed=True;raise
        return result
    def read(self,a):return self.exchange('read',a)
    def write(self,a,v):
        self.exchange('write',a,v)
        if a!=SGIR and self.read(a)!=v:self.failed=True;raise RuntimeError('RAM readback mismatch')
        if a==WAKE_HOOK:self.wake_live=v==self.contract.plan.wake_hook

class R5Loader:
    def __init__(self,contract,io):
        self.contract=contract;self.plan=contract.plan;self.io=io;self.journal=None
        self.phase='new';self.probe_executed=False;self.cache_verified=set();self.gated=False
    def phase_to(self,name):self.phase=name;self.io.phase=name
    def idle(self):
        for a,(mask,value) in self.contract.guards.items():
            if a not in (0x6bb46c,0x6bb598,0x2adc78,0x2adc8c):continue
            if self.io.read(a)&mask!=value:raise RuntimeError('AF/profile changed '+hex(a))
    def preflight(self):
        if self.phase!='new':raise RuntimeError('new session required')
        self.phase_to('preflight');self.io.exchange('version')
        for a,(mask,value) in self.contract.guards.items():
            if self.io.read(a)&mask!=value:raise RuntimeError('preflight guard '+hex(a))
        for a,value in sorted(self.contract.expected.items()):
            if self.io.read(a)!=value:raise RuntimeError('cold baseline mismatch '+hex(a))
        self.idle();self.phase_to('prepared')
    def attach_journal(self,journal):
        if self.phase!='prepared' or self.journal:raise RuntimeError('preflight required')
        journal.record.update({'contractSha256':self.contract.digest,'manifest':M,
            'coldBaselineVerified':True,'originalArena':{'start':SCRATCH,'end':0x2b4000,'allZero':True},
            'originalCallbacks':{str(CB):ORIG_CB,str(ARG):ORIG_ARG},
            'automaticAf':False,'automaticRestore':False,'automaticResume':False,
            'recovery':'retain all resident code; inspect record, then user manual restart and cold verification'})
        journal.persist(journal.record);self.journal=journal;self.io.journal=journal
    def write(self,a,v):self.io.write(a,v)
    def upload(self,a,blob):
        for off in range(0,len(blob),4):self.write(a+off,struct.unpack_from('<I',blob,off)[0])
    def quiescent(self,ack=None):
        # 不修改仍可能执行的回调/参数；只等这一次SGI完成，不重新发送。
        for _ in range(64):
            pending=self.io.read(PENDING)&0x8000;active=self.io.read(ACTIVE)&0x8000
            confirmed=ack is None or self.io.read(ack[0])==ack[1]
            if not pending and not active and confirmed:
                if not (self.io.read(PENDING)|self.io.read(ACTIVE))&0x8000:return
        raise RuntimeError('SGI completion not established; retain callback and descriptor')
    def quiet(self):
        self.quiescent();self.write(CB,NOOP);self.quiescent()
    def cache_intent(self,fn,arg,ack=None):
        self.journal.record['cacheInFlight']={'callback':fn,'argument':arg,
            'ack':ack,'completion':'unknown_until_ack_and_quiescence'}
        self.journal.persist(self.journal.record)
    def cache_complete(self):
        self.journal.record['cacheInFlight']=None;self.journal.persist(self.journal.record)
    def line_cache(self,fn):
        if fn not in (CLEAN,INVALIDATE):raise ValueError('cache function')
        self.quiet();self.write(ARG,SCRATCH);self.write(CB,fn)
        self.cache_intent(fn,SCRATCH);self.write(SGIR,SELF15)
        self.quiescent();self.cache_complete();self.quiet()
    def probe(self):
        if self.journal is None or self.phase!='prepared':raise RuntimeError('saved preflight required')
        self.phase_to('cache_probe');self.quiet();self.upload(SCRATCH,PROBE);self.write(DESC,0)
        self.line_cache(CLEAN);self.line_cache(INVALIDATE)
        self.write(ARG,DESC);self.write(CB,SCRATCH);self.cache_intent(SCRATCH,DESC,(DESC,MAGIC))
        self.write(SGIR,SELF15)
        self.quiescent((DESC,MAGIC));self.cache_complete();self.quiet();self.probe_executed=True
        # 不自动清除暂存区。仅在确认探针回调结束后替换为固定缓存范围helper。
        self.upload(SCRATCH,THUNK);self.line_cache(CLEAN);self.line_cache(INVALIDATE)
        self.phase_to('cache_ready')
    def range_cache(self,start,size,fn):
        if (start,size) not in self.contract.ranges or fn not in (CLEAN_RANGE,INVALIDATE_RANGE):
            raise ValueError('fixed cache range')
        self.quiet()
        for a,v in ((DESC,start),(DESC+4,size),(DESC+8,fn),(DESC+12,0)):self.write(a,v)
        self.write(ARG,DESC);self.write(CB,SCRATCH)
        self.cache_intent(SCRATCH,DESC,(DESC+12,1));self.write(SGIR,SELF15)
        self.quiescent((DESC+12,1));self.cache_complete();self.quiet()
    def sync(self,start,size):
        if not self.probe_executed:raise RuntimeError('executed cache probe required')
        self.range_cache(start,size,CLEAN_RANGE);self.range_cache(start,size,INVALIDATE_RANGE)
        self.cache_verified.update(range(start&~31,(start+size+31)&~31,4))
    def sync_hook(self,a):self.sync(a&~31,32)
    def stage(self):
        if self.phase!='cache_ready':raise RuntimeError('cache bootstrap required')
        p=self.plan;self.idle();self.phase_to('installing_independent_gate')
        for a,v in p.helper.items():self.write(a,v)
        self.sync(BASE,p.helper_size)
        if self.io.read(HOOK)!=p.baseline[HOOK] or self.io.read(WAKE_HOOK)!=p.wake_original:
            raise RuntimeError('staging entry changed')
        self.write(HOOK,p.gate);self.sync_hook(HOOK)
        self.write(WAKE_HOOK,p.wake_hook);self.sync_hook(WAKE_HOOK)
        self.phase_to('waiting_native_idle_ack')
        # COUNT读取的首次调用由临时F4hook产生一次通知，所有请求均记录其副作用。
        for _ in range(64):
            count=self.io.read(COUNT);sent=self.io.read(SENT)
            if count and sent==1:break
        else:raise RuntimeError('fresh native AF barrier missing; no body uploaded')
        self.idle()
        if self.io.read(HOOK)!=p.gate or self.io.read(WAKE_HOOK)!=p.wake_hook:
            raise RuntimeError('staged entry changed')
        for a,v in p.helper.items():
            if self.io.read(a)!=v:raise RuntimeError('independent helper changed')
        # 允许有多个原生idle通知；计数必须非零且来自本次已核对的零初始化区域。
        self.gated=True;self.phase_to('removing_wake_entry')
        self.write(WAKE_HOOK,p.wake_original);self.sync_hook(WAKE_HOOK)
        self.phase_to('gated')
    def state_check(self,armed):
        p=self.plan;a=M['symbols']['af_state'];v=M['symbols']['fast_video_state']
        checks={a:M['stateMagic'],a+4:6,a+8:armed,a+16:0,a+20:0,a+40:0,
            a+M['canaryOffset']:M['canary'],v:0x46313630,v+4:1,v+8:armed,
            v+12:0,v+16:0,v+20:0,v+32:0,v+36:0,v+40:0,v+116:0x30363146,
            M['symbols']['fast_video_begin_status']:0x80000000,
            M['symbols']['fast_video_begin_generation']:0,
            M['symbols']['fast_video_begin_gain']:0,
            M['symbols']['af_error_events']:0,M['symbols']['af_error_generation']:0}
        for addr,value in checks.items():
            if self.io.read(addr)!=value:raise RuntimeError('state guard '+hex(addr))
    def install(self):
        if not self.gated or self.phase!='gated':raise RuntimeError('native AF gate required')
        p=self.plan;self.idle()
        for a,v in p.baseline.items():
            if a in p.helper or a in (HOOK,COUNT,SENT,0x6bb46c):continue
            if self.io.read(a)!=v:raise RuntimeError('baseline changed while gated '+hex(a))
        if self.io.read(HOOK)!=p.gate or not self.io.read(COUNT):raise RuntimeError('AF gate lost')
        self.phase_to('uploading_gated')
        for a,blob in p.uploads:self.upload(a,blob);self.sync(a,len(blob))
        self.phase_to('installing_hooks_gated')
        for a,(old,new) in p.hooks.items():
            if a==HOOK:continue
            if self.io.read(a)!=old:raise RuntimeError('hook changed '+hex(a))
            self.write(a,new);self.sync_hook(a)
        for a,old,new in M['speed_words']:
            if self.io.read(a)!=old:raise RuntimeError('speed changed')
            self.write(a,new)
        self.phase_to('verifying_gated');self.verify_code(final=False);self.state_check(0);self.idle()
        # 所有代码和依赖入口已同步后再置启用字段，最后释放AF入口。
        self.write(p.video_enabled,2);self.write(p.af_armed,2);self.phase_to('releasing_af_gate')
        self.write(HOOK,p.final_gate);self.sync_hook(HOOK)
        self.phase_to('restoring_cache_slot');self.quiet();self.write(ARG,ORIG_ARG);self.write(CB,ORIG_CB)
        self.quiescent();self.phase_to('verifying_installed')
        self.verify_code(final=True);self.state_check(2);self.idle()
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG:raise RuntimeError('cache slot not restored')
        self.phase_to('installed_armed_until_restart')
        self.journal.record.update({'phase':self.phase,'installed':True,'armed':True,
            'probeExecuted':True,'nativeIdleAckObserved':True,'installerScratchRetained':True,
            'requests':self.io.requests,'writeRequests':self.io.writes,'allHandlesClosed':self.io.closed,
            'hardwareRequests':self.io.requests if self.io.is_hardware else 0,
            'physicalAfSpeedVerified':False,'physical160PreviewVerified':False})
        self.journal.persist(self.journal.record)
    def verify_code(self,final):
        p=self.plan
        for a,v in self.contract.static_code.items():
            if a not in self.cache_verified or self.io.read(a)!=v:raise RuntimeError('static code verification '+hex(a))
        for a,(old,new) in p.hooks.items():
            expected=new if final or a!=HOOK else p.gate
            if a not in self.cache_verified or self.io.read(a)!=expected:raise RuntimeError('hook verification '+hex(a))
        if self.io.read(WAKE_HOOK)!=p.wake_original:raise RuntimeError('wake hook not restored')
        for a,old,new in M['speed_words']:
            if self.io.read(a)!=new:raise RuntimeError('speed verification')
    def summary(self):
        return {'stage':self.phase,'artifactSha256':ARTIFACT,'requests':self.io.requests,
            'writeRequests':self.io.writes,'hardwareRequests':self.io.requests if self.io.is_hardware else 0,
            'allHandlesClosed':self.io.closed,'automaticRetry':False,'automaticRestore':False,
            'installed':self.phase=='installed_armed_until_restart'}

def readiness(contract):
    path=BUILD/'loader-validation.json'
    if not path.exists():return False
    r=json.loads(path.read_text(encoding='utf-8'))
    if not r.get('passed') or r.get('contractSha256')!=contract.digest or r.get('artifactSha256')!=ARTIFACT:return False
    files=r.get('files',{})
    required=('full_loader_r5.py','r3_install_journal.py','CodeTests/test_full_loader_r5.py',
        'CodeTests/test_r5_task_wake.py','CodeTests/test_r5_install_barrier.py','CodeTests/r5_install_plan.py',
        'CodeTests/test_r5_sgi_native.py','CodeTests/test_r5_install_plan.py',
        'CodeTests/validate_r5_installation.py','CodeTests/check_r5_peak.py',
        'read_full_diagnostic_r5.py','read_r5_transition_timing.py','CodeTests/test_r5_diagnostics.py')
    return all(files.get(n)==hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in required)

def record_failure(loader,journal,error):
    """仅补充电脑端故障记录，保留请求/缓存操作的未知状态，不访问设备。"""
    if journal is None or journal.failed:return False
    record=dict(journal.record)
    record.update({'phase':loader.phase,'failureType':type(error).__name__,
        'requests':loader.io.requests,'writeRequests':loader.io.writes,
        'hardwareRequests':loader.io.requests if loader.io.is_hardware else 0,
        'allHandlesClosed':loader.io.closed,'requiresReview':True})
    try:journal.persist(record)
    except BaseException:journal.failed=True;return False
    journal.record=record;journal.failed=True;return True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('report','install'),nargs='?',default='report');args=parser.parse_args()
    contract=FixedContract(FarmApplication());ready=readiness(contract)
    if args.action=='report':
        print(json.dumps({'artifactSha256':ARTIFACT,'contractSha256':contract.digest,'experimentalInstallReady':ready,
            'releaseReady':False,'hardwareRequests':0,'requestLimit':REQUEST_LIMIT,
            'recovery':'no automatic retry or in-place rollback; preserve record and resident code'},indent=2));return
    if not ready:raise RuntimeError('current loader validation required; no USB opened')
    loader=R5Loader(contract,FixedIO(contract));journal=None
    try:
        loader.preflight()
        stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
        path=HERE/'recovery'/('full-r5-'+stamp+'.json')
        journal=InstallJournal(path,ARTIFACT,backend='fixed_usb')
        loader.attach_journal(journal);print(json.dumps({'stage':'prepared','recovery':path.name}),flush=True)
        loader.probe();loader.stage();print(json.dumps(loader.summary()),flush=True)
        loader.install();print(json.dumps(loader.summary()),flush=True)
    except BaseException as error:
        record_failure(loader,journal,error)
        print(json.dumps(loader.summary()),flush=True)
        raise
    finally:
        if journal:journal.close()

if __name__=='__main__':main()
