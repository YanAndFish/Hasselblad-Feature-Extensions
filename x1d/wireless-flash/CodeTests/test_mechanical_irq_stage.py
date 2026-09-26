"""实际 ARM 任务、关闭检查、回复和整图缓存；RTOS/物理操作明确使用替身。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
OUT=HERE/'build/mechanical-irq-candidate'
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
sys.path.insert(0,str(HERE/'research'))
from mechanical_irq_loading import apply_image,FARM_SHA
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

IMAGE=0x2129040;MESSAGE=0x6c37f4;STACK=0x3000000;STOP=0x3200000

class Model:
    def __init__(self,farm,build,plan,original,mode='success'):
        assert hashlib.sha256(farm).hexdigest()==FARM_SHA
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,0x1c0000);u.mem_write(0x100000,farm)
        for address,size in ((0x6b0000,0x40000),(0x2129000,0x5b4000),(STACK,0x8000)):u.mem_map(address,size)
        payload=(OUT/'irq-stage.bin').read_bytes();assert hashlib.sha256(payload).hexdigest()==build['sha256']
        u.mem_write(build['base'],payload);u.mem_write(IMAGE,original)
        self.build,self.plan,self.mode=build,plan,mode
        self.replies=[];self.queue_calls=[];self.reloads=[];self.cache_writes=[];self.cache_calls=[];self.hook_writes=[];self.cpsr=0x60000013
        self.sleeps=[];self.closes=[];self.physical_closes=[];self.deferred=[];self.held=False;self.tick=1000
        self.record=build['entries']['mechanical_irq_stage_record']
        self.active=build['entries']['mechanical_irq_guard_active'];self.active_writes=[]
        names={0x22b910:'mechanical_irq_reset_call_guard',0x22ceb8:'mechanical_irq_download_call_guard',
            0x22cd90:'mechanical_irq_ready_branch_guard',0x1e2264:'mechanical_irq_stage_message'}
        self.original_hooks={a:struct.unpack_from('<I',farm,a-0x100000)[0] for a in names}
        for a,name in names.items():self.put(a,(0xea000000 if a==0x22cd90 else 0xeb000000)|(((build['entries'][name]-a-8)//4)&0xffffff))
        if mode=='changed-hook':self.put(0x22ceb8,0)
        for address,value in ((0x2129004,len(original)),(0x2129008,IMAGE),(0x6db2c4,0x6ee000),(0x6bb46c,0)):
            self.put(address,value)
        self.put(0x2b20cc,int(mode.startswith('quiet-')))
        self.put(0x6db2c0,0x6ee100)
        if mode.startswith('quiet-'):self.put(0x6dae18+44*21+12,1)
        if mode=='quiet-scheduler-blocked':self.put(0x6badec,1)
        if mode=='quiet-already-configured':self.put(self.record+16,1)
        if mode=='quiet-previous-fault':self.put(self.record+20,1)
        for section in range(0x21,0x27):self.put(0x2b4000+section*4,section<<20|0xc02)
        if mode=='length':self.put(0x2129004,len(original)-4)
        if mode=='pointer':self.put(0x2129008,IMAGE+4)
        if mode=='mapping':self.put(0x2b4084,0x2100c0e)
        if mode=='af-active':self.put(0x6bb46c,1)
        if mode=='no-lock':self.put(0x6db2c4,0)
        if mode=='irq-context':self.cpsr=0x60000012
        if mode=='masked':self.cpsr|=0x80
        if mode=='unknown-cache':self.put(IMAGE,self.word(IMAGE)^1)
        if mode=='mixed':
            for row in plan['words'][::3]:self.put(IMAGE+row['offset'],row['after'])

        def code(uc,a,n,_):
            if a==0x22e3d4:
                assert not self.held and self.sleeps==[600]
                self.closes.append(a);return # 执行固定原厂 ARM 关闭函数。
            if a in (0x2209f4,0x18629c):raise AssertionError('不允许原断言或创建信号量')
            if a==0x236a14:result=0
            elif a==0x187bd8:
                assert not self.held and not self.queue_calls and not self.cache_writes and self.word(self.active)==0
                ticks=uc.reg_read(arm.UC_ARM_REG_R0);assert ticks==600
                self.sleeps.append(ticks);self.tick+=ticks
                if self.mode in ('quiet-release','quiet-recent','quiet-close-noop'):
                    self.put(0x6dae18+44*21+12,0)
                    self.put(0x6dae18+44*21+4,self.tick if self.mode=='quiet-recent' else 1000)
                if self.mode=='quiet-af-started':self.put(0x6bb46c,1)
                result=0
            elif a==0x22a924:result=self.tick
            elif a==0x22c784:
                assert self.closes==[0x22e3d4] and uc.reg_read(arm.UC_ARM_REG_R0)==0
                self.physical_closes.append(a)
                if self.mode!='quiet-close-noop':self.put(0x2b20cc,0)
                result=0
            elif a==0x18a020:self.deferred.append(a);result=0
            elif a in (0x239714,0x227870,0x22ab60,0x22ad5c,0x22ab30,0x22067c):result=0
            elif a in (0x186b70,0x186500):
                args=[uc.reg_read(r) for r in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2,arm.UC_ARM_REG_R3)]
                assert args==[0x6ee000,0,0,0] or (self.closes and a==0x186b70 and args==[0x6ee000,0,1000,0]),args
                self.queue_calls.append(a);result=0 if self.mode=='lock-busy' and a==0x186b70 else 1
                if a==0x186b70:
                    assert not self.held;self.held=bool(result)
                else:assert self.held;self.held=False
            elif a==0x22cc4c:
                assert self.word(self.active)==1
                current=bytes(uc.mem_read(IMAGE,len(original)))
                assert hashlib.sha256(current).hexdigest()==plan['candidateSha256']
                self.reloads.append('resource-manager-is-modeled')
                self.put(build['entries']['mechanical_irq_download_state'],0 if self.mode=='reload-noop' else 3 if self.mode=='reload-failure' else 2)
                result=1 if self.mode=='reload-failure' else 0
            elif a==0x1e80d0:
                self.replies.append(bytes(uc.mem_read(uc.reg_read(arm.UC_ARM_REG_R0),5)));result=0
            elif a in (0x10a270,0x10a354):
                start=uc.reg_read(arm.UC_ARM_REG_R0);size=uc.reg_read(arm.UC_ARM_REG_R1)
                assert size==32 and start in {address&~31 for address in names}
                self.cache_calls.append((a,start,size));result=0
            else:raise AssertionError(hex(a))
            uc.reg_write(arm.UC_ARM_REG_R0,result);uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR))
        for address in (0x2209f4,0x18629c,0x236a14,0x186b70,0x186500,0x22cc4c,0x1e80d0,0x10a270,0x10a354,
                        0x22e3d4,0x187bd8,0x22a924,0x22c784,0x18a020,0x239714,0x227870,0x22ab60,0x22ad5c,0x22ab30,0x22067c):
            u.hook_add(UC_HOOK_CODE,code,begin=address,end=address)
        values={IMAGE+r['offset']:{r['before'],r['after']} for r in plan['words']}
        def write(uc,access,a,n,v,_):
            assert n==4 and v in values.get(a,()),(hex(a),n,hex(v))
            self.cache_writes.append((a,v))
        u.hook_add(UC_HOOK_MEM_WRITE,write,begin=IMAGE,end=IMAGE+len(original)-1)
        def hook_write(uc,access,a,n,v,_):
            assert n==4 and v==self.original_hooks[a]
            assert self.queue_calls and self.queue_calls[-1]==0x186b70
            self.hook_writes.append(a)
        for address in names:u.hook_add(UC_HOOK_MEM_WRITE,hook_write,begin=address,end=address)
        def active_write(uc,access,a,n,v,_):
            assert n==4 and v in (0,1) and self.queue_calls[-1]==0x186b70
            self.active_writes.append(v)
        u.hook_add(UC_HOOK_MEM_WRITE,active_write,begin=self.active,end=self.active)

    def put(self,address,value):self.u.mem_write(address,struct.pack('<I',value))
    def word(self,address):return struct.unpack('<I',self.u.mem_read(address,4))[0]
    def run(self,command,original_handler=False,source=8,dispatcher=False):
        u=self.u;u.mem_write(MESSAGE,bytes([0x1b,2,source,1,command]))
        u.reg_write(arm.UC_ARM_REG_CPSR,self.cpsr);u.reg_write(arm.UC_ARM_REG_SP,STACK+0x7000)
        u.reg_write(arm.UC_ARM_REG_R0,MESSAGE);u.reg_write(arm.UC_ARM_REG_LR,STOP)
        entry=0x1e1964 if original_handler else self.build['entries']['mechanical_irq_stage_message']
        end=0x1e2268 if dispatcher else STOP
        u.emu_start(0x1e225c if dispatcher else entry,end,count=3000000000)
        assert u.reg_read(arm.UC_ARM_REG_PC)==end
        assert self.word(self.active)==0
        assert self.replies[-1][:4]==bytes([0x1c,2,1,source])
        return self.replies[-1][4]

def run(farm):
    assert Path.cwd().resolve()==ROOT
    build=json.loads((OUT/'irq-stage-build.json').read_text(encoding='utf-8'))
    for name,digest in build['sourceHashes'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest
    plan=json.loads((OUT/'irq-pl-word-plan.json').read_text(encoding='utf-8'))
    candidate=(OUT/'irq-pl-candidate.bin').read_bytes();original=apply_image(candidate,plan,True)
    passed=[]
    def case(name,mode='success'):return Model(farm,build,plan,original,mode)
    for command in (0xa0,0xa1,0xa2,0xa3,0xaf):
        m=case('stock-rejects');assert m.run(command,True)==1 and not m.queue_calls and not m.reloads and not m.cache_writes
    passed.append('stock-rejects-all-private-commands')
    for mode,expected in (('length',11),('pointer',11),('mapping',12),('af-active',13),('no-lock',13),('irq-context',10),('masked',10),('lock-busy',14)):
        m=case(mode,mode);assert m.run(0xa1)==1 and m.word(m.record+8)==expected and not m.reloads and not m.cache_writes
        assert m.queue_calls==([0x186b70] if mode=='lock-busy' else [])
        passed.append(mode)
    for mode,expected in (('quiet-busy',25),('quiet-recent',25),('quiet-af-started',13),
                          ('quiet-scheduler-blocked',10),('quiet-already-configured',17),('quiet-previous-fault',17),('quiet-close-noop',23)):
        m=case(mode,mode);assert m.run(0xa1)==1 and m.word(m.record+8)==expected,(mode,m.word(m.record+8))
        assert not m.reloads and not m.cache_writes and not m.held and m.word(m.record+24)==1
        expected_closes=1 if mode in ('quiet-busy','quiet-recent','quiet-close-noop') else 0
        assert len(m.closes)==expected_closes
        assert m.sleeps==([] if mode in ('quiet-scheduler-blocked','quiet-already-configured','quiet-previous-fault') else [600])
        if mode=='quiet-busy':assert m.word(0x6dae18+44*21+12)==1
        if mode in ('quiet-busy','quiet-recent'):assert not m.physical_closes and len(m.deferred)==1
        passed.append(mode)
    m=case('wrong-source');assert m.run(0xa1,source=5)==1 and not m.queue_calls and not m.reloads and not m.cache_writes
    passed.append('wrong-source')
    m=case('retire');assert m.run(0xa3,dispatcher=True)==0
    assert m.hook_writes==list(m.original_hooks) and len(m.cache_calls)==8
    assert all(m.word(a)==v for a,v in m.original_hooks.items()) and m.queue_calls==[0x186b70,0x186500]
    assert m.run(0xaf,dispatcher=True)==1 and m.word(m.record+4)==0xa3 and not m.reloads and not m.cache_writes
    passed.append('retire-under-lock-and-original-dispatcher-barrier')
    m=case('changed-hook','changed-hook');assert m.run(0xa3)==1 and m.word(m.record+8)==24 and not m.hook_writes and not m.cache_calls
    passed.append('changed-hook-retirement-refused-before-writes')
    m=case('inspect');assert m.run(0xa0)==0 and m.word(m.record+12)==0 and not m.reloads and not m.cache_writes
    assert m.queue_calls==[0x186b70,0x186500];passed.append('inspect-full-arm-sha')
    print(json.dumps({'stageCasesPassed':passed}),flush=True)
    for mode in ('success','reload-failure','reload-noop','quiet-release'):
        success=mode in ('success','quiet-release')
        m=case(mode,mode);assert m.run(0xa1)==(0 if success else 1)
        assert m.word(m.record+16)==int(success) and m.word(m.record+20)==int(mode=='reload-failure')
        expected_image=candidate if success else original
        assert bytes(m.u.mem_read(IMAGE,len(original)))==expected_image and m.word(m.record+12)==int(success)
        assert len(m.cache_writes)==(253 if success else 506) and len(m.reloads)==1
        assert m.queue_calls==[0x186b70,0x186500]*(2 if mode=='quiet-release' else 1)
        if mode=='quiet-release':assert m.sleeps==[600] and len(m.closes)==len(m.physical_closes)==1
        assert m.active_writes==[1,0]
        if mode!='reload-noop':assert m.run(0xa1)==1 and m.word(m.record+8)==17 and len(m.reloads)==1
        else:assert m.word(m.record+8)==22
        passed.append(mode+'-cache-lifecycle-checked')
        print(json.dumps({'stageCasePassed':passed[-1]}),flush=True)
    m=case('unknown-cache','unknown-cache');assert m.run(0xa1)==1 and m.word(m.record+8)==15 and not m.cache_writes and not m.reloads
    passed.append('unknown-cache')
    m=case('mixed','mixed');assert m.run(0xa2)==0 and not m.reloads and bytes(m.u.mem_read(IMAGE,len(original)))==original
    passed.append('mixed-cache-restored-without-pcap')
    report={'passed':True,'installed':False,'hardwareRequests':0,'cases':passed,'stageSha256':build['sha256'],
        'realArmCoreAndOriginalReplyHeaderExecuted':True,'realOriginalLockWrapperExecuted':True,
        'freertosQueueAndResourceReloadAreStubs':True,'physicalResourceRecoveryValidated':False,
        'stockRejectsPrivateCommandsWithoutReconfiguration':True,'successfulCacheRetainedAndFailedCacheRestored':True,
        'quietWaitRunsWithoutLockThenRealOriginalCloseChecksExecute':True,
        'busyRecentlyUsedOrAfStartedRejectedBeforeCacheWrites':True,
        'quietTicks':600,'physicalResourceCloseAndSchedulerAreStubs':True,
        'repeatConfigurationRejected':True,'floatingPointEnabledInReplay':False,
        'guardsActiveOnlyInsideLockedExplicitReload':True,
        'sourceHashes':{str(Path(__file__).relative_to(HERE)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT/'irq-stage-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.path.insert(0,str(ROOT/'x1d/tools'))
    from farm_diagnostic_binary import FarmApplication
    print(json.dumps(run(FarmApplication().data),ensure_ascii=False))
