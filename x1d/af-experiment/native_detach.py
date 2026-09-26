"""撤销当前原厂 AF 观察入口，保留驻留内存和引闪；默认 report 完全离线。"""
import argparse,hashlib,json,sys
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
from native_install import *
from native_loader import NativeIO,readiness,failure
from r3_install_journal import InstallJournal

class ObservationContract(NativeContract):
    def __init__(self,record,manifest,blob,farm=None):
        super().__init__(farm,nonce=record['bootstrapNonce'])
        if (record.get('contractSha256')!=self.identity or not record.get('installed') or
            record.get('phase')!='installed_observation_until_restart' or record.get('inFlight') is not None or
            record.get('cacheInFlight') is not None or not record.get('allHandlesClosed') or
            record.get('mode')!='native_af_observation' or record.get('predictionActuation') is not False or
            record.get('speedOverrides') is not False):raise ValueError('completed observation installation required')
        self.installation=record;response=record['allocationResponse']
        self.bind(response,(0,response[10]|0x80000000),manifest,blob)
        # 撤销只允许恢复原厂入口、临时 gate 和共享缓存辅助；没有主体或分配结果写入。
        shared=set(range(SCRATCH,SCRATCH+64,4))|{CB,ARG,SGIR}
        hooks={a for a,old,new in manifest['emulatorOnlyHooks']}
        own={GATE_HOOK,WAKE_HOOK,self.control,self.count,self.sent}
        self.allowed={a:values for a,values in self.allowed.items() if a in shared|hooks|own}
        self.allowed[CB].discard(self.exec_probe);self.allowed[ARG].discard(self.exec_ack)
        for a,old,new in manifest['emulatorOnlyHooks']:self.allowed[a]={old}
        self.allowed[self.control]={0,2};self.allowed[self.count]={0};self.allowed[self.sent]={0}
        self.native_hook_addresses=hooks
    def check_write_phase(self,phase,a):
        if phase in ('new','preflight','prepared','original_af_restored_memory_retained'):
            raise ValueError('writes denied in current phase')
        if a in self.native_hook_addresses and phase!='detaching_native_hooks':raise ValueError('detach hook phase')
        if a in (self.control,self.count,self.sent) and phase not in ('preparing_detach_gate','releasing_native_gate'):
            raise ValueError('detach control phase')
        if a in (GATE_HOOK,WAKE_HOOK) and phase not in ('preparing_detach_gate','removing_wake_entry','releasing_native_gate'):
            raise ValueError('detach temporary hook phase')
        if phase=='restoring_shared_scratch' and not SCRATCH<=a<SCRATCH+64:raise ValueError('scratch restoration only')

class ObservationDetach(NativeLoader):
    def preflight(self):
        if self.phase!='new':raise RuntimeError('new detach session required')
        c=self.c;m=c.candidate;self.phase_to('preflight');self.hold_initial();self.io.exchange('version')
        for a,(mask,value) in c.guards.items():
            if self.io.read(a)&mask!=value:raise RuntimeError('detach preflight guard '+hex(a))
        expected=dict(c.expected);expected.update(c.bootstrap_words)
        expected.update({c.request+4*i:v for i,v in enumerate(c.allocation)})
        expected[c.control]=2;expected[c.sent]=1;expected.pop(c.count)
        expected.update({a:new for a,old,new in m['emulatorOnlyHooks']})
        expected.update({a:v for a,v in c.candidate_words.items() if a<m['state_start']})
        for index,(a,value) in enumerate(sorted(expected.items())):
            if index%256==0:self.hold_boundary('detach_preflight_'+str(index))
            if self.io.read(a)!=value:raise RuntimeError('resident observation code/state changed '+hex(a))
        if not self.io.read(c.count):raise RuntimeError('previous idle ACK missing')
        raw=c.allocation[8]
        if tuple(self.io.read(a) for a in (raw-8,raw-4))!=(0,c.allocation[10]|0x80000000):raise RuntimeError('heap ownership changed')
        self.verify_observation_state()
        c.scratch_before={a:self.io.read(a) for a in range(SCRATCH,SCRATCH+64,4)}
        # 恢复当前窗口开始时的共享内容；回执值在探针期间仍禁止主机写入。
        self.flash_sequence=self.io.read(c.flash['record']+12);self.idle();self.phase_to('prepared')
    def verify_observation_state(self):
        c=self.c;s=c.candidate['symbols'];bank=s['na_config_bank']
        if self.io.read(s['na_adapter']+8)!=0 or self.io.read(s['na_speed_overrides'])!=0:
            raise RuntimeError('detach requires unchanged observation mode')
        if self.io.read(bank)!=2:raise RuntimeError('configuration publication changed')
        for a in range(bank+8,bank+80,4):
            if self.io.read(a)!=c.candidate_words[a]:raise RuntimeError('observation configuration changed')
        if self.io.read(c.exec_ack)!=EXEC_MAGIC:raise RuntimeError('owned execution proof changed')
    def attach(self,journal):
        super().attach(journal)
        self.persist(operation='detach_native_observation',parentInstallationSha256=digest(self.c.installation),
            allocationResponse=self.c.allocation,candidate=self.c.candidate,
            allocated=self.c.installation['allocated'],memoryWillBeRetained=True,
            recovery='retain code/heap and current gate state; inspect both event chains; coordinate with flash task before any further action')
    def gate(self):
        if self.phase!='cache_ready':raise RuntimeError('cache probe required')
        self.hold_boundary('before_detach_gate',park=True)
        c=self.c;self.idle();self.verify_observation_state();self.phase_to('preparing_detach_gate')
        # 保留 READY 请求和其安装代次；原厂 nr_reserve 见 READY 立即返回，不会再次分配。
        for a in (c.count,c.sent,c.control):self.write(a,0)
        for a in (GATE_HOOK,WAKE_HOOK):
            old,new=c.bootstrap_hooks[a]
            if self.io.read(a)!=old:raise RuntimeError('temporary entry changed')
            self.write(a,new);self.sync_hook(a)
        self.phase_to('waiting_detach_idle')
        for _ in range(64):
            if self.io.read(c.count) and self.io.read(c.sent)==1:break
        else:raise RuntimeError('detach idle ACK missing')
        if [self.io.read(c.request+4*i) for i in range(13)]!=c.allocation:raise RuntimeError('allocation response changed')
        if self.io.read(c.control)!=0:raise RuntimeError('detach gate lost')
        self.idle();self.gated=True;self.persist(detachIdleAcknowledged=True)
        self.phase_to('removing_wake_entry');self.write(WAKE_HOOK,c.bootstrap_hooks[WAKE_HOOK][0]);self.sync_hook(WAKE_HOOK)
    def detach(self):
        if not self.gated or self.phase!='removing_wake_entry':raise RuntimeError('acknowledged detach gate required')
        self.hold_boundary('before_detach_hooks',park=True)
        c=self.c;self.phase_to('detaching_native_hooks')
        for a,old,new in c.candidate['emulatorOnlyHooks']:
            if self.io.read(a)!=new:raise RuntimeError('native AF entry changed '+hex(a))
            self.write(a,old);self.sync_hook(a)
            self.hold_boundary('detach_hook_'+str(a),park=True)
        self.phase_to('verifying_detached_hooks')
        for a,old,new in c.candidate['emulatorOnlyHooks']:
            if self.io.read(a)!=old:raise RuntimeError('original AF entry not restored')
        self.verify_flash();self.idle()
        self.hold_boundary('before_detach_release')
        self.phase_to('releasing_native_gate');self.write(c.control,2)
        self.write(GATE_HOOK,c.bootstrap_hooks[GATE_HOOK][0]);self.sync_hook(GATE_HOOK)
        self.phase_to('restoring_cache_slot');self.quiet();self.write(ARG,ORIG_ARG);self.write(CB,ORIG_CB);self.quiescent()
        self.phase_to('restoring_shared_scratch')
        for a,value in c.scratch_before.items():c.allowed[a]={value}
        for a,value in c.scratch_before.items():self.write(a,value)
        self.quiescent()
        for a,v in ((GATE_HOOK,c.bootstrap_hooks[GATE_HOOK][0]),(WAKE_HOOK,c.bootstrap_hooks[WAKE_HOOK][0]),(CB,ORIG_CB),(ARG,ORIG_ARG)):
            if self.io.read(a)!=v:raise RuntimeError('temporary/shared entry restoration failed')
        self.verify_flash();self.idle()
        self.phase_to('original_af_restored_memory_retained')
        self.persist(phase=self.phase,installed=False,removed=True,nativeAfEntriesRestored=True,
            flashCodePreserved=True,heapFreed=False,residentMemoryRetained=True,automaticRestart=False,
            hardwareRequests=self.io.requests if self.io.is_hardware else 0,
            requests=self.io.requests,writeRequests=self.io.writes,allHandlesClosed=self.io.closed)

def load_contract(path):
    path=path.resolve()
    if not path.is_relative_to(HERE/'recovery'):raise ValueError('current AF recovery path required')
    c=NativeContract();record=InstallJournal.read_record(path,c.identity)
    if record['journalAudit']['incompleteTail']:raise ValueError('incomplete installation event chain')
    m=record['candidate'];folder=HERE/'build/native-capture-r1'/f"{m['base']:08x}"
    if json.loads((folder/'capture-manifest.json').read_text(encoding='utf-8'))!=m:raise ValueError('installed manifest changed')
    return ObservationContract(record,m,(folder/'candidate.bin').read_bytes(),c.farm)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('report','detach'),nargs='?',default='report')
    p.add_argument('--journal',type=Path);args=p.parse_args()
    if args.journal is None:
        if args.action!='report':raise ValueError('completed installation journal required')
        print(json.dumps({'hardwareRequests':0,'requires':'成功的本轮观察装载记录；后续仍需引闪主任务审查和独占窗口',
            'restores':'原厂 AF 入口和临时回调；代码/堆块保留，不重启相机'}));return
    c=load_contract(args.journal)
    if args.action=='report':
        print(json.dumps({'hardwareRequests':0,'contractSha256':c.identity,'nativeEntries':len(c.candidate['emulatorOnlyHooks']),
            'payloadBase':c.candidate['base'],'memoryRetained':True,'heapFreed':False}));return
    if not readiness(c):raise RuntimeError('current offline validation required; no USB opened')
    loader=ObservationDetach(c,NativeIO(c));journal=None
    try:
        loader.preflight();stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
        journal=InstallJournal(HERE/'recovery'/('native-detach-'+stamp+'.json'),c.identity,backend='fixed_usb');loader.attach(journal)
        loader.probe();loader.gate();loader.detach()
        print(json.dumps({'phase':loader.phase,'hardwareRequests':loader.io.requests,'allHandlesClosed':loader.io.closed,'heapFreed':False}));return
    except BaseException as error:
        failure(loader,journal,error)
        print(json.dumps({'phase':loader.phase,'hardwareRequests':loader.io.requests,'writeRequests':loader.io.writes,
            'allHandlesClosed':loader.io.closed,'automaticRetry':False}));raise
    finally:
        if journal:journal.close()

if __name__=='__main__':main()
