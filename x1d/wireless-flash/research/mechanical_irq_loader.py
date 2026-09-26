"""双 IRQ 的 RAM 安装/解除状态机。当前只允许离线模型，没有实机 transport。

旧采集 payload 必须经过重启边界释放，不能在运行中覆盖其 arena。
本模块不加载 FPGA；未来组合装载器必须先提供已验证的配置装载与恢复证据。
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'research'))
import mechanical_sync_loader as old

ROOT,common,pre=old.ROOT,old.common,old.pre
BASE,DESC,CB,ARG=old.BASE,old.DESC,old.CB,old.ARG
ORIG_CB,ORIG_ARG,NOOP=old.ORIG_CB,old.ORIG_ARG,old.NOOP
CLEAN,INVALIDATE=old.CLEAN,old.INVALIDATE
CLEAN_RANGE,INVALIDATE_RANGE,SGIR,SELF15=old.CLEAN_RANGE,old.INVALIDATE_RANGE,old.SGIR,old.SELF15
PROBE,PROBE_MAGIC,THUNK=old.PROBE,old.PROBE_MAGIC,old.THUNK
CALL_THUNK=struct.pack('<8I',0xe92d4010,0xe1a04000,0xe8940007,0xe12fff32,
                       0xe584000c,0xe3a00001,0xe5840010,0xe8bd8010)
OUT=HERE/'build/mechanical-irq-candidate'
BUILD=json.loads((OUT/'irq-target-build.json').read_text(encoding='utf-8'))
PAYLOAD_START,PAYLOAD_BYTES=BUILD['base'],BUILD['payloadBytes']
SYMBOLS=BUILD['entries']
RECORD=SYMBOLS['mechanical_sync_record']
MAGIC=0x32494d47
BOTH=0x0c000000
ORIGINAL_HOOKS=old.ORIGINAL_HOOKS
HOOK_SYMBOLS={0x21409c:'mechanical_sync_clear_hook',0x21410c:'mechanical_sync_start_hook',
    0x213e60:'mechanical_sync_status_hook',0x213ef8:'mechanical_sync_status_hook',0x2143e4:'mechanical_sync_finish_hook'}
NEW_HOOKS={a:0xeb000000|(((SYMBOLS[name]-a-8)//4)&0xffffff) for a,name in HOOK_SYMBOLS.items()}
CACHE_RANGES=((PAYLOAD_START,PAYLOAD_BYTES),)+tuple((a&~31,32) for a in HOOK_SYMBOLS)
FUNCTIONS=tuple(SYMBOLS[n] for n in ('mechanical_irq_setup','mechanical_sync_cancel_old','mechanical_irq_restore'))
EXTRA_READ=(0xf8f01108,0xf8f01208,0xf8f01308,0xf8f01458,0xf8f01858,0xf8f01c14,0xf8f00108,
    0x2a52cc,0x2a52d0,0x2a52d4,0x2a52d8)
READ_SET=old.READ_SET|frozenset(EXTRA_READ)
LIVE_LOADER_ENABLED=False

def payload():
    value=(OUT/'irq-target.bin').read_bytes()
    if len(value)!=PAYLOAD_BYTES or hashlib.sha256(value).hexdigest()!=BUILD['payloadSha256']:
        raise ValueError('双 IRQ ARM 构建字节不匹配')
    for name,digest in BUILD['sourceHashes'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('双 IRQ ARM 源码已变化')
    return value

def allowed_writes():
    values={CB:{ORIG_CB,NOOP,CLEAN,INVALIDATE,BASE},ARG:{ORIG_ARG,BASE,DESC},SGIR:{SELF15}}
    values.update({a:{v,NEW_HOOKS[a]} for a,v in ORIGINAL_HOOKS.items()})
    for a in range(BASE,BASE+64,4): values[a]={0}
    for a,data in ((BASE,PROBE),(BASE,THUNK),(BASE,CALL_THUNK),(PAYLOAD_START,payload())):
        for i in range(0,len(data),4): values.setdefault(a+i,{0}).add(struct.unpack_from('<I',data,i)[0])
    values[DESC].update([RECORD,*[a for a,n in CACHE_RANGES]])
    values[DESC+4].update(n for a,n in CACHE_RANGES)
    values[DESC+8].update((CLEAN_RANGE,INVALIDATE_RANGE,*FUNCTIONS))
    values[DESC+12].add(1); values[DESC+16].add(1)
    values[RECORD+4].add(1)
    return values

WRITE_VALUES=allowed_writes()

def request(kind,address=None,value=None,size=512):
    if type(size) is not int or size not in (512,1024): raise ValueError('packet size')
    if kind=='version' and address is None and value is None: body=bytes.fromhex('0d000801')
    elif kind=='read' and type(address) is int and address in READ_SET and value is None:
        body=bytes.fromhex('f4000801')+struct.pack('<I',address)
    elif kind=='write' and type(address) is int and type(value) is int and value in WRITE_VALUES.get(address,()):
        body=bytes.fromhex('f2000801')+struct.pack('<II',address,value)
    else: raise ValueError('outside fixed IRQ RAM scope')
    return body+bytes(size-len(body))

class Loader(old.Loader):
    def __init__(self,io):
        if getattr(io,'offline_model',False) is not True:
            raise RuntimeError('FPGA 组合装载尚未完成，当前仅接受离线模型')
        super().__init__(io)

    def prepare(self,farm,destination):
        # 离线身份校验必须先于首次设备/模型读取。
        if self.saved or Path.cwd().resolve()!=ROOT.resolve() or hashlib.sha256(farm).hexdigest()!=pre.FARM_SHA:
            raise RuntimeError('workspace/source mismatch')
        payload()
        for name,digest in (("read_usb_link_once.py",pre.HOST_SHA),("usb_diagnostic_contract.py",pre.CONTRACT_SHA)):
            if hashlib.sha256((ROOT/'x1d/tools'/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('host transport changed')
        # 所有新增 guard 均先读，失败时尚未发生写入。
        for a in (0xf8f01108,0xf8f01208,0xf8f01308):
            if self.io.read(a)&BOTH: raise RuntimeError('两个 IRQ 已被占用或活动')
        if self.io.read(0xf8f00108)&7>2: raise RuntimeError('GIC binary point 不兼容')
        for a,value in ((0x2a52cc,ORIG_CB),(0x2a52d0,ORIG_ARG),(0x2a52d4,ORIG_CB),(0x2a52d8,ORIG_ARG)):
            if self.io.read(a)!=value: raise RuntimeError('IRQ 槽非原厂默认状态')
        super().prepare(farm,destination)
        self.record.update(payload_sha256=BUILD['payloadSha256'],record_address=RECORD,
                           irq_configuration_installed=False,fpga_configured=False,offline_model=True)
        self.save()

    def write(self,address,value):
        if not self.saved: raise RuntimeError('no saved recovery record')
        request('write',address,value)
        self.record['in_flight']={'address':address,'value':value}; self.save()
        self.io.exchange('write',address,value)
        if address!=SGIR and self.io.read(address)!=value: raise RuntimeError('write readback mismatch')
        self.record['in_flight']=None

    def range_cache(self,start,size,function):
        if (start,size) not in CACHE_RANGES or function not in (CLEAN_RANGE,INVALIDATE_RANGE):
            raise ValueError('cache range outside fixed IRQ code')
        self.quiet()
        for a,v in ((DESC,start),(DESC+4,size),(DESC+8,function),(DESC+12,0)): self.write(a,v)
        self.write(ARG,DESC); self.write(CB,BASE); self.write(SGIR,SELF15); self.quiet()
        if self.io.read(DESC+12)!=1: raise RuntimeError('cache operation incomplete')

    def call_irq(self,name):
        function=SYMBOLS.get(name)
        if function not in FUNCTIONS: raise ValueError('non-IRQ function rejected')
        self.quiet()
        for i in range(0,len(CALL_THUNK),4): self.write(BASE+i,struct.unpack_from('<I',CALL_THUNK,i)[0])
        self.line_cache(CLEAN); self.line_cache(INVALIDATE)
        for a,v in ((DESC,RECORD),(DESC+4,0),(DESC+8,function),(DESC+12,0),(DESC+16,0)): self.write(a,v)
        self.write(ARG,DESC); self.write(CB,BASE); self.write(SGIR,SELF15); self.quiet()
        if self.io.read(DESC+16)!=1: raise RuntimeError('IRQ helper did not return')
        result=self.io.read(DESC+12)
        if name!='mechanical_sync_cancel_old' and result!=1: raise RuntimeError('IRQ helper rejected current state')

    def install_disarmed(self):
        if not self.record.get('probe_executed') or self.io.read(pre.AF_IDLE)&255:
            raise RuntimeError('installation precondition')
        if any(self.io.read(a) for a in range(BASE,BASE+64,4)):
            raise RuntimeError('scratch not restored')
        self.record['stage']='installing_irq_disarmed'; self.save()
        data=payload()
        for i in range(0,len(data),4): self.write(PAYLOAD_START+i,struct.unpack_from('<I',data,i)[0])
        self.upload_thunk(); self.sync_code(PAYLOAD_START,PAYLOAD_BYTES)
        self.call_irq('mechanical_irq_setup')
        self.record['irq_configuration_installed']=True; self.save()
        self.upload_thunk()
        for a,value in ORIGINAL_HOOKS.items():
            if self.io.read(a)!=value or self.io.read(pre.AF_IDLE)&255: raise RuntimeError('activation baseline changed')
            self.write(a,NEW_HOOKS[a]); self.sync_code(a&~31,32)
        self.clean_scratch(); self.record.update(stage='irq_installed_disarmed',installed=True)
        self.verify(0); self.save()

    def verify(self,armed):
        if any(self.io.read(a)!=v for a,v in NEW_HOOKS.items()): raise RuntimeError('IRQ hook mismatch')
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG or any(self.io.read(a) for a in range(BASE,BASE+64,4)):
            raise RuntimeError('scratch/SGI callback mismatch')
        if self.io.read(RECORD)!=MAGIC or self.io.read(RECORD+4)!=armed or self.io.read(RECORD+8)!=0 or self.io.read(RECORD+76)!=MAGIC:
            raise RuntimeError('IRQ record mismatch')
        for a,v in ((0x2a52cc,SYMBOLS['mechanical_irq_hold']),(0x2a52d0,RECORD),
                    (0x2a52d4,SYMBOLS['mechanical_irq_idle']),(0x2a52d8,RECORD)):
            if self.io.read(a)!=v: raise RuntimeError('IRQ ownership mismatch')
        if any(self.io.read(a)&BOTH for a in (0xf8f01108,0xf8f01208,0xf8f01308)):
            raise RuntimeError('IRQ not idle')
        data=payload()
        for i in range(0,RECORD-PAYLOAD_START,4):
            if self.io.read(PAYLOAD_START+i)!=struct.unpack_from('<I',data,i)[0]: raise RuntimeError('IRQ code differs')
        if self.io.read(pre.AF_IDLE)&255: raise RuntimeError('AF active')

    def arm(self):
        if not self.record.get('installed') or not self.record.get('fpga_configured'):
            raise RuntimeError('必须先取得双 IRQ FPGA 配置成功证据')
        self.verify(0); self.write(RECORD+4,1)
        self.record.update(stage='armed_for_user_exposures',armed=True); self.save()

    def unhook(self):
        if not self.record.get('installed') or any(self.io.read(a)!=v for a,v in NEW_HOOKS.items()):
            raise RuntimeError('not the recorded IRQ installation')
        self.write(RECORD+4,0); self.record['armed']=False
        if self.io.read(pre.AF_IDLE)&255: raise RuntimeError('AF active')
        self.call_irq('mechanical_sync_cancel_old')
        self.upload_thunk()
        for a,v in ORIGINAL_HOOKS.items(): self.write(a,v); self.sync_code(a&~31,32)
        self.call_irq('mechanical_irq_restore'); self.clean_scratch()
        if any(self.io.read(a)!=v for a,v in ORIGINAL_HOOKS.items()): raise RuntimeError('hook restoration mismatch')
        for a,v in ((0x2a52cc,ORIG_CB),(0x2a52d0,ORIG_ARG),(0x2a52d4,ORIG_CB),(0x2a52d8,ORIG_ARG)):
            if self.io.read(a)!=v: raise RuntimeError('IRQ restoration mismatch')
        self.record.update(stage='irq_removed_payload_retained',installed=False,irq_configuration_installed=False,
            safe_to_overwrite_payload_without_restart=False,fpga_restore_still_separate=True)
        self.save()
