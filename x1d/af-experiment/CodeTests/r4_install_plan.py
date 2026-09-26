"""R4装载事务的离线核心；只接收测试内存后端，不包含设备适配器。"""
import sys,struct,hashlib,json
sys.dont_write_bytecode=True
from test_r4_install_barrier import BASE,COUNT,HOOK,BLOB,branch,M,BUILD
from test_r4_task_wake import WAKE_BASE,WAKE_HOOK,WAKE_BLOB,SENT,READ_HANDLER

class InstallPlan:
    def __init__(self,farm):
        assert farm.sha256==M['baseline_sha256']
        self.baseline={};self.uploads=[];self.code={};self.hooks={a:(old,new) for a,old,new in M['hooks']}
        self.gate=branch(HOOK,BASE);self.final_gate=self.hooks[HOOK][1]
        for a in range(0x2b2880,0x2b4000,4):self.baseline[a]=0
        main=(BUILD/'candidate.bin').read_bytes()
        assert hashlib.sha256(main).hexdigest()==M['payload_sha256']
        self.uploads.append((M['base'],main))
        for item in M['segments']:
            blob=(BUILD/item['file']).read_bytes();a=item['base']
            assert len(blob)==item['bytes'] and hashlib.sha256(blob).hexdigest()==item['sha256']
            assert hashlib.sha256(farm.read(a,len(blob))).hexdigest()==item['originalSha256']
            size=(len(blob)+3)&~3;old=farm.read(a,size)
            blob+=old[len(blob):]
            self.uploads.append((a,blob))
            self.baseline.update({a+i:struct.unpack_from('<I',old,i)[0] for i in range(0,size,4)})
        for a,blob in self.uploads:
            self.code.update({a+i:struct.unpack_from('<I',blob,i)[0] for i in range(0,len(blob),4)})
        for a,old,new in M['hooks']+M['speed_words']:
            assert a not in self.code
            self.baseline[a]=old
        self.baseline.update({0x6bb46c:0,COUNT:0})
        self.helper={BASE+i:struct.unpack_from('<I',BLOB,i)[0] for i in range(0,len(BLOB),4)}
        self.helper.update({WAKE_BASE+i:struct.unpack_from('<I',WAKE_BLOB,i)[0] for i in range(0,len(WAKE_BLOB),4)})
        self.helper_size=len(BLOB)+len(WAKE_BLOB)
        self.wake_original=branch(WAKE_HOOK,READ_HANDLER)|0x01000000
        assert farm.word(WAKE_HOOK)==self.wake_original
        self.baseline[WAKE_HOOK]=self.wake_original
        self.wake_hook=branch(WAKE_HOOK,WAKE_BASE)|0x01000000
        assert not set(self.helper)&set(self.code) and COUNT not in self.code
        self.af_armed=M['symbols']['af_state']+8;self.video_enabled=M['symbols']['fast_video_state']+8

class MemoryBackend:
    """分开保存数据与可执行可见版本；缓存同步仍为模型。"""
    def __init__(self,plan,fail_at=None,after_effect=False):
        self.plan=plan;self.memory=dict(plan.baseline);self.visible=dict(self.memory)
        self.fail_at=fail_at;self.after_effect=after_effect;self.operations=[]
        self.hardware_requests=0;self.gate_ack=False
    def read(self,address):return self.memory[address]
    def mutate(self,op,effect):
        n=len(self.operations)
        if n==self.fail_at and not self.after_effect:raise IOError('injected before effect')
        effect();self.operations.append(op)
        if n==self.fail_at and self.after_effect:raise IOError('injected after effect')
    def write(self,address,value):
        assert address in self.memory
        self.mutate(('write',address,value),lambda:self.memory.__setitem__(address,value))
        if self.read(address)!=value:raise RuntimeError('readback mismatch')
    def sync(self,address,size):
        assert address%4==size%4==0
        def effect():
            for a in range(address,address+size,4):self.visible[a]=self.memory[a]
        self.mutate(('cache_model',address,size),effect)
    def observe_native_idle_ack(self,counter):
        assert counter==1 and self.memory[COUNT]==0
        assert self.visible[HOOK]==self.plan.gate
        assert self.visible[WAKE_HOOK]==self.plan.wake_hook
        assert all(self.visible[a]==v for a,v in self.plan.helper.items())
        self.memory[COUNT]=counter;self.memory[SENT]=1;self.gate_ack=True

class OfflineInstaller:
    def __init__(self,plan,backend,journal=None):
        if type(backend) is not MemoryBackend:raise TypeError('offline memory backend required')
        self.plan=plan;self.io=backend;self.phase='new';self.inflight=None;self.journal=journal
    def write(self,a,value):
        self.inflight=('write',a,value)
        if self.journal:self.journal.begin(self.phase,self.inflight)
        self.io.write(a,value)
        if self.journal:self.journal.complete()
        self.inflight=None
    def sync(self,a,size):
        self.inflight=('cache_model',a,size)
        if self.journal:self.journal.begin(self.phase,self.inflight)
        self.io.sync(a,size)
        if self.journal:self.journal.complete()
        self.inflight=None
    def stage(self):
        assert self.phase=='new'
        if any(self.io.read(a)!=v for a,v in self.plan.baseline.items()):raise RuntimeError('cold baseline required')
        self.phase='staging'
        for a,v in self.plan.helper.items():self.write(a,v)
        self.sync(BASE,self.plan.helper_size);self.write(HOOK,self.plan.gate);self.sync(HOOK,4)
        self.write(WAKE_HOOK,self.plan.wake_hook);self.sync(WAKE_HOOK,4)
        self.phase='waiting_native_idle_ack'
    def install(self):
        p=self.plan;b=self.io
        if self.phase!='waiting_native_idle_ack':raise RuntimeError('stage required')
        if not b.gate_ack or b.read(COUNT)!=1 or b.read(SENT)!=1 or b.read(0x6bb46c)!=0:
            raise RuntimeError('fresh native idle barrier required')
        if b.read(HOOK)!=p.gate or b.visible[HOOK]!=p.gate:raise RuntimeError('gate changed')
        for a,v in p.baseline.items():
            if a in p.helper or a in (HOOK,COUNT,SENT,WAKE_HOOK):continue
            if b.read(a)!=v:raise RuntimeError('staged baseline changed')
        if any(b.read(a)!=v or b.visible[a]!=v for a,v in p.helper.items()):raise RuntimeError('helper changed')
        if b.read(WAKE_HOOK)!=p.wake_hook or b.visible[WAKE_HOOK]!=p.wake_hook:
            raise RuntimeError('wake entry changed')
        # ACK已证明AF到达屏障，先恢复F4原调用。helper继续保留，供可能保存的返回地址使用。
        self.phase='removing_wake_entry'
        self.write(WAKE_HOOK,p.wake_original);self.sync(WAKE_HOOK,4)
        self.phase='uploading_gated'
        for a,blob in p.uploads:
            for i in range(0,len(blob),4):self.write(a+i,struct.unpack_from('<I',blob,i)[0])
            self.sync(a,len(blob))
        self.phase='hooks_gated'
        for a,(old,new) in p.hooks.items():
            if a==HOOK:continue
            if b.read(a)!=old:raise RuntimeError('hook changed')
            self.write(a,new);self.sync(a,4)
        for a,old,new in M['speed_words']:
            if b.read(a)!=old:raise RuntimeError('speed changed')
            self.write(a,new)
        self.phase='verifying_gated'
        if any(b.read(a)!=v or b.visible[a]!=v for a,v in p.code.items()):raise RuntimeError('payload mismatch')
        if any(b.read(a)!=new or b.visible[a]!=new for a,(old,new) in p.hooks.items() if a!=HOOK):
            raise RuntimeError('hook mismatch')
        if b.read(0x6bb46c)!=0 or b.read(p.af_armed)!=0 or b.read(p.video_enabled)!=0:
            raise RuntimeError('disarmed idle required')
        self.write(p.video_enabled,2);self.write(p.af_armed,2)
        self.phase='releasing'
        self.write(HOOK,p.final_gate);self.sync(HOOK,4)
        self.phase='installed_model_only'

def visible_safety(plan,backend):
    """错误之后从可执行入口检查依赖，不使用安装器的阶段标志。"""
    visible=backend.visible
    changed_body=any(backend.memory[a]!=plan.baseline[a] for a in plan.code if a<M['base'])
    gate=visible[HOOK]
    if visible[WAKE_HOOK]==plan.wake_hook:
        if gate!=plan.gate or not all(visible[a]==v for a,v in plan.helper.items()):return False
    if changed_body and gate not in (plan.gate,plan.final_gate):return False
    if gate==plan.gate:
        if not all(visible[a]==v for a,v in plan.helper.items()):return False
    if gate==plan.final_gate:
        if visible[WAKE_HOOK]!=plan.wake_original:return False
        if not all(visible[a]==v for a,v in plan.code.items()):return False
        if not all(visible[a]==new for a,(old,new) in plan.hooks.items()):return False
        if backend.read(plan.af_armed)!=2 or backend.read(plan.video_enabled)!=2:return False
    if changed_body and not backend.gate_ack:return False
    return True
