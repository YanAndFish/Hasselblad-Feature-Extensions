"""AF 独立堆装载合同和事务。此模块仅定义流程，不打开 USB。"""
import hashlib,json,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication

SCRATCH=0x2b2800;DESC=0x2b2820;CB=0x2a5074;ARG=0x2a5078
ORIG_CB=0x109304;ORIG_ARG=0x6da728;NOOP=0x1009d4
CLEAN=0x10a2d0;INVALIDATE=0x10a310;CLEAN_RANGE=0x10a270;INVALIDATE_RANGE=0x10a354
SGIR=0xf8f01f00;SELF15=0x0200000f;PENDING=0xf8f01200;ACTIVE=0xf8f01300
MAGIC=0xafaf2026;EXEC_MAGIC=0x314b4341
PROBE=bytes.fromhex('261002e3af1f4ae3001080e51eff2fe1')
THUNK=struct.pack('<7I',0xe92d4010,0xe1a04000,0xe8940007,0xe12fff32,0xe3a00001,0xe584000c,0xe8bd8010)
GATE_HOOK=0x19b960;WAKE_HOOK=0x1e2224
VERSIONS=['827fa74','c9bb91d','abad48d']
BASELINE_SHA='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def words(base,blob):
    assert base%4==0 and len(blob)%4==0
    return {base+i:struct.unpack_from('<I',blob,i)[0] for i in range(0,len(blob),4)}
def checked(path,key):
    manifest=json.loads(path.read_text(encoding='utf-8'))
    for name,h in manifest[key].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=h:raise ValueError('source changed: '+name)
    return manifest

class NativeContract:
    def __init__(self,farm=None,nonce=1):
        if Path.cwd().resolve()!=ROOT.resolve():raise ValueError('current workspace required')
        self.farm=f=FarmApplication() if farm is None else farm
        if f.sha256!=BASELINE_SHA or hashlib.sha256(f.data).hexdigest()!=BASELINE_SHA:raise ValueError('factory FARM identity')
        out=HERE/'build/native-bootstrap-r1'
        self.bootstrap=b=checked(out/'bootstrap-manifest.json','sourceSha256')
        self.bootstrap_blob=(out/'bootstrap.bin').read_bytes()
        if b['baselineSha256']!=f.sha256 or hashlib.sha256(self.bootstrap_blob).hexdigest()!=b['payloadSha256']:
            raise ValueError('bootstrap identity')
        if (b['base'],b['end'])!=(0x2b3400,0x2b37c0):raise ValueError('coexistence bootstrap layout changed')
        if type(nonce)!=int or not 1<=nonce<=0xffffffff:raise ValueError('nonzero installation nonce required')
        self.nonce=nonce
        # 只替换请求代次及其校验；可执行代码仍逐字来自已验证模板。
        runtime=bytearray(self.bootstrap_blob);offset=b['symbols']['nr_request']-b['base']
        struct.pack_into('<I',runtime,offset+8,nonce)
        prefix=struct.unpack_from('<5I',runtime,offset);checksum=0x6c871ae5
        for value in prefix:checksum^=value
        struct.pack_into('<I',runtime,offset+20,checksum);self.bootstrap_blob=bytes(runtime)
        self.offline=c=checked(HERE/'build/native-capture-r1/00800000/capture-manifest.json','source_sha256')
        offline_blob=(HERE/'build/native-capture-r1/00800000/candidate.bin').read_bytes()
        if c['baseline_sha256']!=f.sha256 or hashlib.sha256(offline_blob).hexdigest()!=c['payload_sha256']:
            raise ValueError('offline candidate identity')
        if c['end']-c['base']>16384 or c['initialSpeedOverrides'] or c['initialPredictionActuation']:
            raise ValueError('observation initial state required')
        self.request=b['symbols']['nr_request'];self.control=b['symbols']['nr_gate_control']
        self.count=self.control+4;self.sent=self.control+8
        self.bootstrap_words=words(b['base'],self.bootstrap_blob)
        self.bootstrap_hooks={a:(old,new) for a,old,new in b['emulatorOnlyHooks']}
        self.candidate=None;self.candidate_words={};self.allocation=None;self.scratch_before={}
        self.guards={0x2ad78c:(0xffffffff,0x2a4ffc),0x6da728:(0xffffffff,0x2a4ff0),
            0x6da72c:(0xffffffff,0x11111111),CB:(0xffffffff,ORIG_CB),ARG:(0xffffffff,ORIG_ARG),
            0x6bb46c:(255,0),0x6bb598:(255,0),0x2adc78:(0xff00,18<<8),0x2adc8c:(255,0),
            0xf8f01000:(1,1),0xf8f00100:(9,1),0xf8f01100:(0x8000,0x8000),
            PENDING:(0x8000,0),ACTIVE:(0x8000,0),0xf8f0140c:(0xff000000,0xa0000000),
            0xf8f01080:(0x8000,0)}
        self.expected={a:0 for a in self.bootstrap_words}
        regions=[(0x100770,0x100930),(0x10a270,0x10a3ac),(0x10acac,0x10acb8),
            (0x18b034,0x18b09c),(0x1a4890,0x1a4950),(0x18a020,0x18a210),
            (0x189e4c,0x18a020),(0x19b708,0x19b77c),(0x1e1ff8,0x1e22cc),
            (0x19b284,0x19b46c),(0x1a44f8,0x1a4618),
            (0x1e164c,0x1e1888),(0x1e2524,0x1e2560),(0x238ef8,0x238f3c),(0x15a3dc,0x15a5e8),
            (0x184a60,0x1850e4),(0x188370,0x1883a0),(0x188424,0x188630),
            (0x1986d8,0x198778),(0x1f0c20,0x1f0e6c),(0x19bfb0,0x19eac0),
            (0x1a0240,0x1a03e0),(0x1a1a98,0x1a22bc),(0x1a2a30,0x1a3168),
            (0x1a4950,0x1a4af0)]
        for lo,hi in regions:
            for a in range(lo,hi,4):self.expected[a]=f.word(a)
        for a in set(self.bootstrap_hooks)|{a for a,_,_ in c['emulatorOnlyHooks']}|{0x19d198,NOOP}:
            for p in range(a&~31,(a&~31)+32,4):self.expected[p]=f.word(p)
        for section in range(2,7):self.expected[0x2b4000+section*4]=f.word(0x2b4000+section*4)
        # 来源任务的正式引闪现已驻留；仅核对其代码/入口，不导入或调用引闪装载器。
        self.flash=json.loads((HERE/'CodeTests/Fixtures/InstalledHfs1.json').read_text(encoding='utf-8'))
        fm=self.flash;flash_blob=(HERE/fm['payloadFile']).read_bytes()
        if (fm['base'],fm['bytes'],fm['record'],fm['recordBytes'])!=(0x2b2880,2716,0x2b31b0,364):
            raise ValueError('fixed HFS1 coexistence layout')
        if hashlib.sha256(flash_blob).hexdigest()!=fm['payloadSha256'] or len(flash_blob)!=fm['bytes']:
            raise ValueError('installed HFS1 payload identity')
        self.flash_expected=words(fm['base'],flash_blob[:fm['record']-fm['base']])
        if len(fm['newHooks'])!=8 or fm['newHooks'].keys()!=fm['originalHooks'].keys():raise ValueError('HFS1 hooks')
        for key,new in fm['newHooks'].items():
            a=int(key)
            if f.word(a)!=fm['originalHooks'][key]:raise ValueError('HFS1 factory hook')
            for p in range(a&~31,(a&~31)+32,4):self.flash_expected[p]=f.word(p)
        self.flash_expected.update({int(a):v for a,v in fm['newHooks'].items()})
        if any(a in self.expected and self.expected[a]!=v for a,v in self.flash_expected.items()):
            raise ValueError('AF/HFS1 expected code conflict')
        self.expected.update(self.flash_expected)
        self.guards.update({fm['record']:(0xffffffff,0x31534648),fm['record']+4:(0xffffffff,1),fm['record']+8:(0xffffffff,0)})
        self.allowed={a:{v} for a,v in self.bootstrap_words.items()}
        for a,(old,new) in self.bootstrap_hooks.items():self.allowed[a]={old,new}
        for a,old,_ in c['emulatorOnlyHooks']:self.allowed[a]={old}
        for a in range(SCRATCH,SCRATCH+64,4):self.allowed[a]={0}
        for blob in (PROBE,THUNK):
            for a,v in words(SCRATCH,blob).items():self.allowed[a].add(v)
        self.allowed[CB]={ORIG_CB,NOOP,CLEAN,INVALIDATE,SCRATCH};self.allowed[ARG]={ORIG_ARG,SCRATCH,DESC}
        self.allowed[SGIR]={SELF15};self.allowed[self.control].add(2)
        self.ranges={(b['base'],len(self.bootstrap_blob))}|{(a&~31,32) for a in self.bootstrap_hooks}
        self.ranges|={(a&~31,32) for a,_,_ in c['emulatorOnlyHooks']}
        self.allowed[DESC].update(a for a,n in self.ranges);self.allowed[DESC+4].update(n for a,n in self.ranges)
        self.allowed[DESC+8].update((CLEAN_RANGE,INVALIDATE_RANGE))
        # 主机只能发布原始请求/零 ACK，不能伪造申请结果或执行回执。
        self.allowed[self.count]={0};self.allowed[self.sent]={0};self.allowed[DESC+12]={0}
        self.reads=set(self.expected)|set(self.guards)|set(self.allowed)-{SGIR}
        self.reads|={0x6badd0,0x6bb470,0x6baccc,0x6bacb0,0x6bacb4,0x6bacbc,fm['record']+12}
        if set(self.allowed)&(set(self.flash_expected)|set(range(fm['base'],fm['base']+fm['bytes'],4))):
            raise ValueError('AF write ownership overlaps HFS1')
        from native_hold import identity as hold_identity
        self.hold=hold_identity()
        self.identity=digest({'bootstrap':b['payloadSha256'],'offline':c['payload_sha256'],'hold':self.hold,
            'expected':self.expected,'guards':self.guards,'flash':self.flash,'sources':{**b['sourceSha256'],**c['source_sha256']}})
    def allocation_header_addresses(self,r):
        original=struct.unpack_from('<6I',self.bootstrap_blob,self.request-self.bootstrap['base'])
        if len(r)!=13 or tuple(r[:6])!=original or r[6:8]!=[3,0]:raise ValueError('native allocation not READY')
        raw,base,size,before,after=r[8:13]
        if raw%8 or not 0x2bacb0<=raw<0x6baca0 or base!=(raw+31)&~31 or size%8 or size<16424:
            raise ValueError('invalid native allocation shape')
        if raw-8+size>0x6baca0 or base+16384>raw-8+size or before-after!=size or after<131072:
            raise ValueError('native allocation capacity/accounting')
        self.reads.update((raw-8,raw-4))
        return raw-8,raw-4
    def bind(self,r,header,manifest,blob):
        if self.candidate is not None:raise ValueError('only one allocation may be bound')
        self.allocation_header_addresses(r)
        if header!=(0,r[10]|0x80000000):raise ValueError('original allocator ownership header')
        if manifest['base']!=r[9] or manifest['end']>r[9]+16384 or manifest['baseline_sha256']!=BASELINE_SHA:
            raise ValueError('candidate exceeds owned allocation')
        if manifest['source_sha256']!=self.offline['source_sha256'] or hashlib.sha256(blob).hexdigest()!=manifest['payload_sha256']:
            raise ValueError('relocated candidate source/content identity')
        if len(blob)!=manifest['end']-manifest['base'] or len(blob)%32:raise ValueError('candidate body bounds')
        if [(a,old) for a,old,new in manifest['emulatorOnlyHooks']]!=[(a,old) for a,old,new in self.offline['emulatorOnlyHooks']]:
            raise ValueError('candidate hook identity')
        self.allocation=list(r);self.candidate=manifest;self.candidate_blob=blob
        self.candidate_words=words(manifest['base'],blob)
        for a,v in self.candidate_words.items():self.allowed[a]={v}
        for a,old,new in manifest['emulatorOnlyHooks']:self.allowed[a].add(new)
        start,n=manifest['base'],len(blob);self.ranges.add((start,n))
        self.allowed[DESC].add(start);self.allowed[DESC+4].add(n)
        self.exec_ack=manifest['symbols']['nc_capture']+28
        self.exec_probe=manifest['symbols']['nc_execution_probe']
        if not self.exec_probe&1 or not start<=self.exec_probe&~1<manifest['state_start']:
            raise ValueError('Thumb execution probe bounds')
        self.allowed[CB].add(self.exec_probe);self.allowed[ARG].add(self.exec_ack)
        if self.allowed[self.exec_ack]!={0}:raise ValueError('execution ACK must initialize zero')
        self.reads.update(self.candidate_words)
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
    def check_write_phase(self,phase,a):
        if phase in ('new','preflight','prepared','installed_observation_until_restart'):
            raise ValueError('writes denied in current phase')
        if a in self.bootstrap_words:
            if a==self.control and phase=='releasing_native_gate':return
            if phase!='staging_idle_allocation':raise ValueError('bootstrap state cannot be rewritten')
        if a in self.candidate_words and phase!='uploading_owned_body':
            raise ValueError('owned body cannot be rewritten after upload')
    @staticmethod
    def reply(kind,data,size):
        if type(data)!=bytes or len(data)!=size:raise ValueError('reply size')
        if kind=='version':
            if data[:4]!=bytes.fromhex('0e000108'):raise ValueError('version header')
            if [data[a:a+64].split(b'\0',1)[0] for a in (4,68,132)]!=[v.encode('ascii') for v in VERSIONS]:
                raise ValueError('firmware version mismatch')
            return VERSIONS
        if data[:4]!=bytes.fromhex('f5000108' if kind=='read' else 'f3000108'):
            raise ValueError('reply header')
        if data[8 if kind=='read' else 4]!=0:raise ValueError('device rejected request')
        return struct.unpack_from('<I',data,4)[0] if kind=='read' else 0

class NativeLoader:
    def __init__(self,contract,io):
        self.c=contract;self.io=io;self.phase='new';self.journal=None
        self.probe_executed=False;self.gated=False;self.cache_verified=set();self.flash_sequence=None
    def phase_to(self,name):self.phase=name;self.io.phase=name
    def persist(self,**values):self.journal.record.update(values);self.journal.persist(self.journal.record)
    def idle(self):
        for a in (0x6bb46c,0x6bb598,0x2adc78,0x2adc8c):
            mask,value=self.c.guards[a]
            if self.io.read(a)&mask!=value:raise RuntimeError('AF/profile changed '+hex(a))
        record=self.c.flash['record']
        for offset,value in ((0,0x31534648),(4,1),(8,0)):
            if self.io.read(record+offset)!=value:raise RuntimeError('HFS1 not ready/idle')
        if self.flash_sequence is not None and self.io.read(record+12)!=self.flash_sequence:
            raise RuntimeError('exposure occurred during AF installation; stop')
    def preflight(self):
        if self.phase!='new':raise RuntimeError('new session required')
        self.phase_to('preflight');self.hold_initial();self.io.exchange('version')
        for a,(mask,value) in self.c.guards.items():
            if self.io.read(a)&mask!=value:raise RuntimeError('preflight guard '+hex(a))
        for index,(a,value) in enumerate(sorted(self.c.expected.items())):
            if index%256==0:self.hold_boundary('preflight_'+str(index))
            if self.io.read(a)!=value:raise RuntimeError('original code/bootstrap mismatch '+hex(a))
        self.c.scratch_before={a:self.io.read(a) for a in range(SCRATCH,SCRATCH+64,4)}
        self.flash_sequence=self.io.read(self.c.flash['record']+12)
        self.idle();self.phase_to('prepared')
    def attach(self,journal):
        if self.phase!='prepared' or self.journal:raise RuntimeError('completed preflight required')
        self.journal=journal;self.io.journal=journal
        self.persist(contractSha256=self.c.identity,bootstrap=self.c.bootstrap,offlineCandidate=self.c.offline,
            bootstrapNonce=self.c.nonce,runtimeBootstrapSha256=hashlib.sha256(self.c.bootstrap_blob).hexdigest(),
            scratchBefore=self.c.scratch_before,originalCallbacks={str(CB):ORIG_CB,str(ARG):ORIG_ARG},
            holdContract=self.c.hold,holdChecks=list(self.io.hold_results),holdRequests=self.io.hold_requests,
            allocated=None,installed=False,automaticAf=False,automaticRestore=False,automaticResume=False,
            preservedFlash=self.c.flash,flashSequence=self.flash_sequence,
            recovery='retain resident code and heap allocation; inspect event chain; completed unchanged observation may use native_detach after review; partial installation requires phase-specific review; no automatic restart')
    def write(self,a,v):self.io.write(a,v)
    def upload(self,start,blob):
        for a,v in words(start,blob).items():self.write(a,v)
    def quiescent(self,ack=None):
        for _ in range(64):
            pending=self.io.read(PENDING)&0x8000;active=self.io.read(ACTIVE)&0x8000
            confirmed=ack is None or self.io.read(ack[0])==ack[1]
            if not pending and not active and confirmed and not (self.io.read(PENDING)|self.io.read(ACTIVE))&0x8000:return
        raise RuntimeError('SGI completion unknown; retain callback/descriptor and stop')
    def quiet(self):self.quiescent();self.write(CB,NOOP);self.quiescent()
    def hold_initial(self):
        # 设备窗口由主任务独占；本事务未借用任何回调，先查 Linux 再发第一笔 FARM。
        io=self.io
        if io.requests or self.journal or io.transfer_active or not io.closed:raise RuntimeError('new serial hold transaction required')
        io.hold_permitted=True
        try:io.check_hold('entry')
        except BaseException:io.failed=True;raise
        finally:io.hold_permitted=False
    def hold_boundary(self,label,park=False):
        io=self.io
        try:
            if (io.failed or io.transfer_active or not io.closed or io.wake_live or
                (self.journal and (self.journal.record.get('inFlight') is not None or self.journal.record.get('cacheInFlight') is not None))):
                raise RuntimeError('hold boundary still has an in-flight operation')
            self.quiescent()
            if park:
                if io.read(CB)!=NOOP:raise RuntimeError('cache slot changed before hold boundary')
                self.write(ARG,ORIG_ARG);self.write(CB,ORIG_CB);self.quiescent()
            if io.read(CB)!=ORIG_CB or io.read(ARG)!=ORIG_ARG:raise RuntimeError('original callback required for hold check')
            self.quiescent();io.hold_permitted=True;io.check_hold(label)
        except BaseException:io.failed=True;raise
        finally:io.hold_permitted=False
    def invoke(self,fn,arg,ack=None):
        self.quiet();self.write(ARG,arg);self.write(CB,fn)
        self.persist(cacheInFlight={'callback':fn,'argument':arg,'ack':ack,'completion':'unknown'})
        self.write(SGIR,SELF15);self.quiescent(ack);self.persist(cacheInFlight=None);self.quiet()
    def line_cache(self,fn):
        if fn not in (CLEAN,INVALIDATE):raise ValueError('fixed cache function')
        self.invoke(fn,SCRATCH)
    def probe(self):
        if self.phase!='prepared' or not self.journal:raise RuntimeError('durable preflight required')
        self.hold_boundary('before_cache_probe')
        self.idle()
        self.phase_to('cache_probe');self.quiet();self.upload(SCRATCH,PROBE);self.write(DESC,0)
        self.line_cache(CLEAN);self.line_cache(INVALIDATE);self.invoke(SCRATCH,DESC,(DESC,MAGIC))
        self.probe_executed=True;self.upload(SCRATCH,THUNK)
        self.line_cache(CLEAN);self.line_cache(INVALIDATE);self.phase_to('cache_ready')
    def range_cache(self,start,size,fn):
        if not self.probe_executed or (start,size) not in self.c.ranges or fn not in (CLEAN_RANGE,INVALIDATE_RANGE):
            raise ValueError('unapproved cache range')
        self.quiet()
        for a,v in ((DESC,start),(DESC+4,size),(DESC+8,fn),(DESC+12,0)):self.write(a,v)
        self.invoke(SCRATCH,DESC,(DESC+12,1))
    def sync(self,start,size):
        self.range_cache(start,size,CLEAN_RANGE);self.range_cache(start,size,INVALIDATE_RANGE)
        self.cache_verified.update(range(start&~31,(start+size+31)&~31,4))
    def sync_hook(self,address):self.sync(address&~31,32)
    def stage(self):
        if self.phase!='cache_ready':raise RuntimeError('cache bootstrap required')
        self.hold_boundary('before_bootstrap',park=True)
        c=self.c;self.idle();self.phase_to('staging_idle_allocation')
        self.upload(c.bootstrap['base'],c.bootstrap_blob);self.sync(c.bootstrap['base'],len(c.bootstrap_blob))
        for a in (GATE_HOOK,WAKE_HOOK):
            old,new=c.bootstrap_hooks[a]
            if self.io.read(a)!=old:raise RuntimeError('bootstrap entry changed')
            self.write(a,new);self.sync_hook(a)
        self.phase_to('waiting_native_idle_allocation')
        for _ in range(64):
            if self.io.read(c.count) and self.io.read(c.sent)==1:break
        else:raise RuntimeError('no native idle ACK; no body uploaded')
        self.idle()
        if self.io.read(c.control)!=0 or self.io.read(GATE_HOOK)!=c.bootstrap_hooks[GATE_HOOK][1]:
            raise RuntimeError('idle gate lost')
        result=[self.io.read(c.request+4*i) for i in range(13)]
        self.persist(allocationResponse=result)
        header_addresses=c.allocation_header_addresses(result)
        header=tuple(self.io.read(a) for a in header_addresses)
        if header!=(0,result[10]|0x80000000):raise RuntimeError('allocator ownership changed')
        self.persist(allocated={'rawPointer':result[8],'payloadBase':result[9],'blockBytes':result[10],'payloadBytes':16384})
        self.gated=True;self.phase_to('removing_wake_entry')
        self.write(WAKE_HOOK,c.bootstrap_hooks[WAKE_HOOK][0]);self.sync_hook(WAKE_HOOK)
        self.phase_to('allocated_and_gated');self.hold_boundary('allocated_before_build',park=True)
        return result,header
    def install(self,result,header,manifest,blob):
        if self.phase!='allocated_and_gated' or not self.gated:raise RuntimeError('owned idle allocation required')
        c=self.c;c.bind(result,header,manifest,blob);self.persist(candidate=manifest)
        self.hold_boundary('before_body')
        self.idle()
        if self.io.read(GATE_HOOK)!=c.bootstrap_hooks[GATE_HOOK][1] or self.io.read(c.control)!=0:
            raise RuntimeError('idle gate lost before body')
        if tuple(self.io.read(a) for a in c.allocation_header_addresses(result))!=header:
            raise RuntimeError('heap ownership changed before body')
        self.phase_to('uploading_owned_body')
        # 原厂回调已恢复，主体尚未执行；仅在完整读回的批次之间查询 Linux。
        for offset in range(0,len(blob),1024):
            if offset:self.hold_boundary('body_'+str(offset))
            self.upload(manifest['base']+offset,blob[offset:offset+1024])
        self.sync(manifest['base'],len(blob))
        self.phase_to('executing_owned_probe');self.invoke(c.exec_probe,c.exec_ack,(c.exec_ack,EXEC_MAGIC))
        self.persist(ownedCodeExecuted=True)
        self.hold_boundary('before_native_hooks',park=True)
        self.phase_to('installing_native_hooks')
        for a,old,new in manifest['emulatorOnlyHooks']:
            if self.io.read(a)!=old:raise RuntimeError('AF hook changed '+hex(a))
            self.write(a,new);self.sync_hook(a)
            self.hold_boundary('native_hook_'+str(a),park=True)
        self.phase_to('verifying_gated');self.verify();self.idle()
        self.hold_boundary('before_native_release')
        # 所有 hooks 可见后才开放原厂 AF；不释放任何仍可能执行的代码或堆块。
        self.phase_to('releasing_native_gate');self.write(c.control,2)
        self.write(GATE_HOOK,c.bootstrap_hooks[GATE_HOOK][0]);self.sync_hook(GATE_HOOK)
        self.phase_to('restoring_cache_slot');self.quiet();self.write(ARG,ORIG_ARG);self.write(CB,ORIG_CB);self.quiescent()
        if self.io.read(GATE_HOOK)!=c.bootstrap_hooks[GATE_HOOK][0] or self.io.read(WAKE_HOOK)!=c.bootstrap_hooks[WAKE_HOOK][0]:
            raise RuntimeError('temporary entries not restored')
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG:raise RuntimeError('cache callback not restored')
        self.verify_flash();self.idle()
        self.phase_to('installed_observation_until_restart')
        self.persist(phase=self.phase,installed=True,mode='native_af_observation',predictionActuation=False,
            speedOverrides=False,nativeFinePreserved=True,flashCodePreserved=True,hardwareRequests=self.io.requests if self.io.is_hardware else 0,
            requests=self.io.requests,writeRequests=self.io.writes,allHandlesClosed=self.io.closed)
    def verify(self):
        c=self.c;m=c.candidate
        self.verify_flash()
        for a,v in c.candidate_words.items():
            if a>=m['state_start']:continue
            if a not in self.cache_verified or self.io.read(a)!=v:raise RuntimeError('body verification '+hex(a))
        for a,old,new in m['emulatorOnlyHooks']:
            if a not in self.cache_verified or self.io.read(a)!=new:raise RuntimeError('hook verification '+hex(a))
        if self.io.read(c.exec_ack)!=EXEC_MAGIC:raise RuntimeError('owned execution ACK lost')
        state=m['symbols']['na_adapter'];capture=m['symbols']['nc_capture']
        for a,v in {state:0,state+4:0,state+8:0,m['symbols']['na_speed_overrides']:0,
                    capture:0x3150434e,capture+4:2,capture+24:1}.items():
            if self.io.read(a)!=v:raise RuntimeError('initial observation state '+hex(a))
    def verify_flash(self):
        for a,v in self.c.flash_expected.items():
            if self.io.read(a)!=v:raise RuntimeError('resident HFS1 code changed '+hex(a))
