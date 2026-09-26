"""原厂 AF 观察装载器。默认 report 完全离线；install 仍要求本轮独占窗口。"""
import argparse,hashlib,json,secrets,sys,time
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
from native_install import *
from r3_install_journal import InstallJournal

BUILD=HERE/'build/native-capture-r1'
REQUEST_LIMIT=24000
TRANSPORT_HASHES={
    'read_usb_link_once.py':'8521ca8655f444c55e59f0bdacb20863816f45d90f4d80ae9a859c3b2940a2b3',
    'usb_diagnostic_contract.py':'80ce1f159fb0ffc442e1e32079411f1b77dfceae3d672d384627d9a4dc785b84'}

class NativeIO:
    is_hardware=True
    def __init__(self,contract):
        self.c=contract;self.requests=0;self.writes=0;self.closed=True;self.failed=False
        self.journal=None;self.phase='new';self.wake_live=False;self.native_type=None
        self.transfer_active=False;self.hold_permitted=False;self.hold_requests=0;self.hold_results=[]
        self.request_limit=REQUEST_LIMIT;self.clock=time.monotonic;self.segment_deadline=None
    def hold_transport(self,packet,token):
        from native_hold import transport
        return transport(self,packet)
    def check_hold(self,label):
        from native_hold import check
        return check(self,label)
    def transport(self,kind,a,v):
        if self.native_type is None:
            for name,h in TRANSPORT_HASHES.items():
                if hashlib.sha256((ROOT/'x1d/tools'/name).read_bytes()).hexdigest()!=h:
                    raise ValueError('USB transport source changed')
            import read_usb_link_once as usb
            class Packet(usb.NativeWinUsb):
                def __init__(self,c,kind,address,value):
                    self.c,self.kind,self.address,self.value=c,kind,address,value;super().__init__()
                def write_query(self,size):
                    if not self.prepared or self.sent or size!=self.packet_size:raise usb.UsbFailure('USB_REQUEST_DENIED')
                    packet=self.c.packet(self.kind,self.address,self.value,size)
                    buffer=usb.c.create_string_buffer(packet,size);count=usb.U32();self.sent=True
                    self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buffer,size,usb.c.byref(count),None),'USB_WRITE')
                    return count.value
            self.native_type=Packet
        return self.native_type(self.c,kind,a,v)
    def interface_size(self,snapshot):
        import read_usb_link_once as usb
        return usb.validate_interface(snapshot)
    def exchange(self,kind,a=None,v=None):
        self.c.packet(kind,a,v)
        if self.failed or self.transfer_active or not self.closed or self.requests>=REQUEST_LIMIT:raise RuntimeError('failed/exhausted transaction; no retry')
        if self.segment_deadline is not None and self.clock()>=self.segment_deadline:
            self.failed=True;raise RuntimeError('hold segment time budget exhausted; no retry')
        self.hold_permitted=False
        if kind=='write':
            if self.journal is None:raise RuntimeError('durable journal required')
            self.c.check_write_phase(self.phase,a)
        operation='wake_read' if kind=='read' and a==self.c.count and self.wake_live else kind
        if self.journal:
            try:self.journal.begin(self.phase,(operation,a or 0,v or 0))
            except BaseException:self.failed=True;raise
        t=None
        try:
            self.transfer_active=True;t=self.transport(kind,a,v);self.closed=False
            size=self.interface_size(t.open());t.prepare()
            if self.segment_deadline is not None and self.clock()>=self.segment_deadline:
                raise RuntimeError('hold segment expired before dispatch')
            self.requests+=1
            if kind=='write':self.writes+=1
            if t.write_query(size)!=size:raise RuntimeError('short request')
            result=self.c.reply(kind,t.read_reply(size),size)
        except BaseException:self.failed=True;raise
        finally:
            if t is not None:
                try:self.closed=all(t.close().values())
                except BaseException:self.closed=False;self.failed=True
            self.transfer_active=False
            if not self.closed:self.failed=True;raise RuntimeError('USB handle close failed')
        if self.journal:
            self.journal.record.update(requests=self.requests,writeRequests=self.writes,
                hardwareRequests=self.requests if self.is_hardware else 0,allHandlesClosed=self.closed,holdRequests=self.hold_requests)
            try:self.journal.complete()
            except BaseException:self.failed=True;raise
        return result
    def read(self,a):return self.exchange('read',a)
    def write(self,a,v):
        self.exchange('write',a,v)
        if a!=SGIR and self.read(a)!=v:self.failed=True;raise RuntimeError('RAM readback mismatch')
        if a==WAKE_HOOK:self.wake_live=v==self.c.bootstrap_hooks[WAKE_HOOK][1]

REQUIRED_FILES=('native_install.py','native_loader.py','r3_install_journal.py','native_reserve.c','native_bootstrap.S',
    'build_native_bootstrap.py','build_native_capture.py','native_capture.c','native_capture.h','native_capture_bridges.S',
    'CodeTests/test_native_memory.py','CodeTests/test_native_reserve.py','CodeTests/test_native_bootstrap.py',
    'CodeTests/test_native_task_wake.py','CodeTests/test_native_af.py','CodeTests/test_native_capture.py',
    'CodeTests/test_native_loader.py','CodeTests/test_native_sgi.py','native_capture_reader.py',
    'CodeTests/test_native_capture_reader.py','CodeTests/validate_native_install.py','build_native_reserve.py',
    'native_detach.py','CodeTests/test_native_detach.py','CodeTests/test_native_capture_concurrency.py',
    'native_hold.py','CodeTests/test_native_hold.py','CodeTests/Fixtures/NativeHold.json',
    '../tools/sutest_ram_contract.py',
    '../references/hasselblad-x1d-reverse-engineering-87b39648a962/tools/usb/x1d_usb_exec.py',
    '../references/hasselblad-x1d-reverse-engineering-87b39648a962/tools/usb/x1d_usb_pull_file.py',
    'CodeTests/inspect_native_task_ownership.py',
    'build/native-capture-r1/pre-concurrency-audit/build/native-capture-r1/00800000/capture-manifest.json',
    'build/native-capture-r1/pre-concurrency-audit/build/native-capture-r1/00800000/candidate.bin',
    '../tools/binary.py','../tools/farm_diagnostic_binary.py','../tools/read_usb_link_once.py',
    '../tools/usb_diagnostic_contract.py','CodeTests/Fixtures/InstalledHfs1.json',
    '../wireless-flash/build/formal-sync-capture/target.bin')

def readiness(c):
    if not c.hold.get('targetExecutableSha256'):return False
    path=BUILD/'loader-validation.json'
    if not path.exists():return False
    r=json.loads(path.read_text(encoding='utf-8'))
    if not r.get('passed') or not r.get('observationInstallReady') or r.get('enhancedAfReady') is not False or r.get('contractSha256')!=c.identity:return False
    return all((HERE/name).is_file() and r.get('files',{}).get(name)==hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in REQUIRED_FILES)

def failure(loader,journal,error):
    if journal is None or journal.failed:return
    record=dict(journal.record);record.update(phase=loader.phase,failureType=type(error).__name__,
        requests=loader.io.requests,writeRequests=loader.io.writes,
        hardwareRequests=loader.io.requests if loader.io.is_hardware else 0,
        allHandlesClosed=loader.io.closed,requiresReview=True,
        holdChecks=list(loader.io.hold_results),holdRequests=loader.io.hold_requests)
    try:journal.persist(record)
    except BaseException:journal.failed=True;return
    journal.record=record;journal.failed=True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('report','install'),nargs='?',default='report')
    args=p.parse_args();c=NativeContract();ready=readiness(c)
    if args.action=='report':
        print(json.dumps({'hardwareRequests':0,'contractSha256':c.identity,'observationInstallReady':ready,
            'enhancedAfReady':False,'expectedWords':len(c.expected),'payloadBytes':c.offline['end']-c.offline['base'],
            'initialMode':'原厂 AF 旁路记录；全部预判代码保留，但真实标定前不改变对焦命令',
            'requires':'当时相机/独占窗口确认、原厂代码基线、独立堆申请与缓存/取指回执'}));return
    if not ready:raise RuntimeError('current offline installation validation required; no USB opened')
    c=NativeContract(c.farm,nonce=secrets.randbelow(0xffffffff)+1)
    loader=NativeLoader(c,NativeIO(c));journal=None
    try:
        loader.preflight()
        stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
        path=HERE/'recovery'/('native-observe-'+stamp+'.json')
        journal=InstallJournal(path,c.identity,backend='fixed_usb');loader.attach(journal)
        print(json.dumps({'stage':'prepared','recovery':path.name}),flush=True)
        loader.probe();result,header=loader.stage()
        print(json.dumps({'stage':loader.phase,'payloadBase':result[9]}),flush=True)
        from build_native_capture import build
        manifest,out=build(result[9]);blob=(out/'candidate.bin').read_bytes()
        loader.install(result,header,manifest,blob)
        print(json.dumps({'stage':loader.phase,'installed':True,'predictionActuation':False,
            'hardwareRequests':loader.io.requests,'allHandlesClosed':loader.io.closed}),flush=True)
    except BaseException as error:
        failure(loader,journal,error)
        print(json.dumps({'stage':loader.phase,'hardwareRequests':loader.io.requests,
            'writeRequests':loader.io.writes,'allHandlesClosed':loader.io.closed,'automaticRetry':False}),flush=True)
        raise
    finally:
        if journal:journal.close()

if __name__=='__main__':main()
