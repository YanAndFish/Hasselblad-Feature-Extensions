"""双 IRQ 前置装载阶段：固定 RAM 白名单、任务命令和代码退出边界。

目前构造器只接受离线模型；没有 USB transport 或自动安装入口。
既有驻留版本仍须先经过用户协调的重启边界，不能覆盖其执行区。
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'research'))
import mechanical_irq_loader as capture

ROOT,old,pre=capture.ROOT,capture.old,capture.pre
BASE,DESC,CB,ARG=capture.BASE,capture.DESC,capture.CB,capture.ARG
ORIG_CB,ORIG_ARG,NOOP=capture.ORIG_CB,capture.ORIG_ARG,capture.NOOP
CLEAN,INVALIDATE=capture.CLEAN,capture.INVALIDATE
CLEAN_RANGE,INVALIDATE_RANGE,SGIR,SELF15=capture.CLEAN_RANGE,capture.INVALIDATE_RANGE,capture.SGIR,capture.SELF15
PROBE,THUNK=capture.PROBE,capture.THUNK
OUT=HERE/'build/mechanical-irq-candidate'
BUILD=json.loads((OUT/'irq-stage-build.json').read_text(encoding='utf-8'))
PLAN=json.loads((OUT/'irq-pl-word-plan.json').read_text(encoding='utf-8'))
START,SIZE,ENTRIES=BUILD['base'],BUILD['bytes'],BUILD['entries']
RECORD,DOWNLOAD=ENTRIES['mechanical_irq_stage_record'],ENTRIES['mechanical_irq_download_state']
HOOK_NAMES={0x22b910:'mechanical_irq_reset_call_guard',0x22ceb8:'mechanical_irq_download_call_guard',
    0x22cd90:'mechanical_irq_ready_branch_guard',0x1e2264:'mechanical_irq_stage_message'}
def branch(address,target,link=True):return (0xeb000000 if link else 0xea000000)|(((target-address-8)//4)&0xffffff)
ORIGINAL_HOOKS={0x22b910:branch(0x22b910,0x22b4fc),0x22ceb8:branch(0x22ceb8,0x22b800),
    0x22cd90:0xe30b32e4,0x1e2264:branch(0x1e2264,0x1e1964)}
NEW_HOOKS={a:branch(a,ENTRIES[name],a!=0x22cd90) for a,name in HOOK_NAMES.items()}
HOOK_WORDS=tuple(sorted({p for a in HOOK_NAMES for p in range(a&~31,(a&~31)+32,4)}))
# 新任务实际调用的原厂关闭函数与睡眠入口窗口也绑定固定 FARM 字节。
ORIGINAL_CALL_WORDS=tuple(range(0x22e3d4,0x22e6e4,4))+tuple(range(0x187bd8,0x187c50,4))
CACHE_RANGES=((START,SIZE),)+tuple((a&~31,32) for a in HOOK_NAMES)
EXTRA_READ=(0x2129004,0x2129008,0x2b20cc,0x6db2c4)+tuple(0x2b4000+i*4 for i in range(0x21,0x27))
READ_SET=capture.READ_SET|frozenset(HOOK_WORDS+ORIGINAL_CALL_WORDS+EXTRA_READ)
LIVE_LOADER_ENABLED=False

def payload():
    if Path.cwd().resolve()!=ROOT.resolve():raise RuntimeError('工作区不匹配')
    data=(OUT/'irq-stage.bin').read_bytes()
    if len(data)!=SIZE or hashlib.sha256(data).hexdigest()!=BUILD['sha256']:raise RuntimeError('阶段程序不匹配')
    for name,digest in BUILD['sourceHashes'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('阶段源码已变化')
    if not (START==0x2b26a0 and START+SIZE<=0x2b4000):raise RuntimeError('阶段执行区越界')
    if any(data[BASE-START:BASE+64-START]):raise RuntimeError('阶段程序与 SGI 暂存区重叠')
    return data

def allowed_writes():
    values={CB:{ORIG_CB,NOOP,CLEAN,INVALIDATE,BASE},ARG:{ORIG_ARG,BASE,DESC},SGIR:{SELF15}}
    values.update({a:{v,NEW_HOOKS[a]} for a,v in ORIGINAL_HOOKS.items()})
    for a in range(BASE,BASE+64,4):values[a]={0}
    for a,data in ((BASE,PROBE),(BASE,THUNK),(START,payload())):
        for off in range(0,len(data),4):values.setdefault(a+off,{0}).add(struct.unpack_from('<I',data,off)[0])
    values[DESC].update(a for a,n in CACHE_RANGES)
    values[DESC+4].update(n for a,n in CACHE_RANGES)
    values[DESC+8].update((CLEAN_RANGE,INVALIDATE_RANGE));values[DESC+12].add(1)
    return values

WRITE_VALUES=allowed_writes()

def request(kind,address=None,value=None,size=512):
    if type(size) is not int or size not in (512,1024):raise ValueError('packet size')
    if kind=='version' and address is None and value is None:body=bytes.fromhex('0d000801')
    elif kind=='read' and type(address) is int and address in READ_SET and value is None:
        body=bytes.fromhex('f4000801')+struct.pack('<I',address)
    elif kind=='write' and type(address) is int and type(value) is int and value in WRITE_VALUES.get(address,()):
        body=bytes.fromhex('f2000801')+struct.pack('<II',address,value)
    elif kind=='stage' and address is None and type(value) is int and value in (0xa0,0xa1,0xa2,0xa3,0xaf):
        body=bytes.fromhex('1b020801')+bytes([value])
    else:raise ValueError('不在固定阶段白名单内')
    return body+bytes(size-len(body))

class Stager(capture.Loader):
    def prepare(self,farm,destination):
        payload() # 任何 I/O 之前核对当前阶段来源。
        super().prepare(farm,destination)
        for address in HOOK_WORDS+ORIGINAL_CALL_WORDS:
            if self.io.read(address)!=struct.unpack_from('<I',farm,address-0x100000)[0]:raise RuntimeError('阶段调用点非原厂基线')
        for address,value in ORIGINAL_HOOKS.items():
            if struct.unpack_from('<I',farm,address-0x100000)[0]!=value:raise RuntimeError('原厂机器码常量不匹配')
        if self.io.read(0x2129004)!=PLAN['bytes'] or self.io.read(0x2129008)!=0x2129040:raise RuntimeError('缓存描述符不匹配')
        for section in range(0x21,0x27):
            if self.io.read(0x2b4000+section*4)!=(section<<20|0xc02):raise RuntimeError('缓存映射不匹配')
        if not self.io.read(0x6db2c4):raise RuntimeError('原厂资源锁尚未建立')
        self.record.update(stage='irq_stage_prepared',payload_sha256=BUILD['sha256'],payload_base=START,
            payload_bytes=SIZE,record_address=RECORD,original_hooks=ORIGINAL_HOOKS,new_hooks=NEW_HOOKS,
            original_stage_calls={a:struct.unpack_from('<I',farm,a-0x100000)[0] for a in ORIGINAL_CALL_WORDS},
            fpga_configured=False,task_retired=False,task_barrier_confirmed=False,arena_cleared=False)
        self.save()

    def write(self,address,value):
        if not self.saved:raise RuntimeError('没有恢复记录')
        request('write',address,value)
        self.record['in_flight']={'address':address,'value':value};self.save()
        self.io.exchange('write',address,value)
        if address!=SGIR and self.io.read(address)!=value:raise RuntimeError('写后核对失败')
        self.record['in_flight']=None

    def range_cache(self,start,size,function):
        if (start,size) not in CACHE_RANGES or function not in (CLEAN_RANGE,INVALIDATE_RANGE):raise ValueError('缓存操作范围错误')
        self.quiet()
        for a,v in ((DESC,start),(DESC+4,size),(DESC+8,function),(DESC+12,0)):self.write(a,v)
        self.write(ARG,DESC);self.write(CB,BASE);self.write(SGIR,SELF15);self.quiet()
        if self.io.read(DESC+12)!=1:raise RuntimeError('缓存操作未完成')

    def install_disarmed(self):
        if not self.record.get('probe_executed') or self.io.read(pre.AF_IDLE)&255:raise RuntimeError('阶段安装前提不符')
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG or any(self.io.read(a) for a in range(BASE,BASE+64,4)):
            raise RuntimeError('SGI 暂存区未归还')
        self.record['stage']='installing_irq_stage';self.save()
        data=payload()
        for off in range(0,len(data),4):self.write(START+off,struct.unpack_from('<I',data,off)[0])
        self.upload_thunk();self.sync_code(START,SIZE)
        # 完整代码和默认透传入口先就绪，最后接入任务入口。
        for a,v in ORIGINAL_HOOKS.items():
            if self.io.read(a)!=v or self.io.read(pre.AF_IDLE)&255:raise RuntimeError('阶段激活前状态改变')
            self.write(a,NEW_HOOKS[a]);self.sync_code(a&~31,32)
        self.clean_scratch();self.record.update(stage='irq_stage_installed',installed=True)
        self.verify();self.save()

    def verify(self):
        if not self.record.get('installed') or self.record.get('task_retired'):raise RuntimeError('阶段未处于安装状态')
        if any(self.io.read(a)!=v for a,v in NEW_HOOKS.items()):raise RuntimeError('阶段入口不匹配')
        if any(self.io.read(int(a))!=v for a,v in self.record['original_stage_calls'].items()):
            raise RuntimeError('原厂关闭或睡眠入口已变化')
        if self.io.read(CB)!=ORIG_CB or self.io.read(ARG)!=ORIG_ARG or any(self.io.read(a) for a in range(BASE,BASE+64,4)):
            raise RuntimeError('SGI 暂存区不匹配')
        data=payload();mutable={DOWNLOAD,*range(RECORD,RECORD+28,4),*range(BASE,BASE+64,4)}
        # 命令前后激活值必须回到 payload 中的 0，不把此值列入可忽略区域。
        for off in range(0,len(data),4):
            if START+off not in mutable and self.io.read(START+off)!=struct.unpack_from('<I',data,off)[0]:raise RuntimeError('阶段代码不匹配')
        if self.io.read(pre.AF_IDLE)&255:raise RuntimeError('AF 非空闲')

    def command(self,operation):
        if operation not in (0xa0,0xa1,0xa2,0xa3):raise ValueError('阶段命令不匹配')
        self.verify();request('stage',None,operation)
        self.record['in_flight']={'stage_command':operation};self.save()
        status=self.io.exchange('stage',None,operation)
        values=[self.io.read(RECORD+i*4) for i in range(7)]
        if values[0]!=0x32504749 or values[1]!=operation or status not in (0,1) or (status==0)!=(values[2]==0):
            raise RuntimeError('任务回复与完成记录不匹配')
        result=dict(zip(('magic','command','result','cache_state','configured','fault','power_state'),values))
        self.record.update(in_flight=None,last_task_result=result);self.save()
        return result

    def configure(self):
        result=self.command(0xa0)
        if result['result'] or result['cache_state']!=0 or result['configured'] or result['fault'] or result['power_state'] not in (0,1):
            raise RuntimeError('缓存或资源状态不允许配置；没有发送配置命令')
        result=self.command(0xa1)
        success=result['result']==0 and result['cache_state']==1 and result['configured']==1 and not result['fault'] and self.io.read(DOWNLOAD)==2
        self.record.update(fpga_configured=success,fpga_image_sha256=PLAN['candidateSha256'] if success else None,
            requires_restart=bool(result['fault']),stage='irq_stage_configured' if success else 'irq_stage_configuration_rejected')
        self.save();return success

    def retire_and_clear(self):
        result=self.command(0xa3)
        if result['result'] or any(self.io.read(a)!=v for a,v in ORIGINAL_HOOKS.items()):raise RuntimeError('任务入口撤销未确认')
        self.record.update(task_retired=True,stage='irq_stage_retired');self.save()
        request('stage',None,0xaf)
        self.record['in_flight']={'original_task_barrier':0xaf};self.save()
        if self.io.exchange('stage',None,0xaf)!=1:raise RuntimeError('原厂拒绝回复边界未确认')
        self.record.update(task_barrier_confirmed=True,in_flight=None);self.save()
        # 资源锁内已撤销所有引用；同一原任务已经处理下一条消息，主机才清空代码。
        for off in range(0,SIZE,4):self.write(START+off,0)
        self.upload_thunk();self.sync_code(START,SIZE);self.clean_scratch()
        if any(self.io.read(a) for a in old.ZERO_WORDS):raise RuntimeError('临时区未完全归还')
        if any(self.io.read(a)!=v for a,v in ORIGINAL_HOOKS.items()):raise RuntimeError('原厂入口已变化')
        self.record.update(installed=False,arena_cleared=True,stage='irq_stage_arena_returned',
            irq_capture_may_follow=bool(self.record.get('fpga_configured')))
        self.save()
