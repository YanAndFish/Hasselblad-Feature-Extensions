"""本轮双中断安装的固定传输适配；导入不连接，不自动安装或重试。

保持离线装载类的默认限制，真实适配使用独立类型与可追溯的本轮授权记录。
原厂关闭请求只发送一次；忙状态可能触发原厂延后关闭，不冒充配置成功。
"""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,struct
import mechanical_irq_stage_loader as s
import mechanical_irq_transport as read
usb=s.old.usb
ANCHORS=(0x1e1998,0x1e19a0,0x1e19c0,0x22e494,0x22e6d0)
REPORTS=('irq-capture-validation.json','irq-wire-validation.json','irq-loader-validation.json',
         'irq-cache-validation.json','irq-pcap-guard-validation.json','irq-stage-validation.json',
         'irq-stage-loader-validation.json','irq-power-down-validation.json','wake-regression-reproduction.json',
         'irq-live-adapter-validation.json')

def validate():
    if Path.cwd().resolve()!=s.ROOT.resolve():raise RuntimeError('工作区不匹配')
    quarantine=s.OUT/'live-quarantine.json'
    if quarantine.exists():
        state=json.loads(quarantine.read_text(encoding='utf-8'))
        if state.get('active'):raise RuntimeError('实机故障尚未定位，本候选已暂停再次装载')
        if state.get('release',{}).get('approvedStageSha256')!=s.BUILD['sha256']:
            raise RuntimeError('候选已变化，既有实机批次不能用于新版装载')
    return validate_evidence()

def validate_evidence():
    """只核对本机证据；此函数不解除隔离，也不允许创建或打开设备。"""
    if Path.cwd().resolve()!=s.ROOT.resolve():raise RuntimeError('工作区不匹配')
    digests={}
    for name in REPORTS:
        raw=(s.OUT/name).read_bytes();r=json.loads(raw)
        if not r['passed'] or r['hardwareRequests']!=0:raise RuntimeError('离线报告未通过')
        for field in ('stageSha256','fixedStageSha256'):
            if field in r and r[field]!=s.BUILD['sha256']:raise RuntimeError('阶段验证对应旧产物')
        if name in ('irq-pcap-guard-validation.json','wake-regression-reproduction.json'):
            guard=json.loads((s.OUT/'irq-pcap-guard-build.json').read_text(encoding='utf-8'))
            if r.get('guardSha256',r.get('fixedGuardSha256'))!=guard['sha256']:raise RuntimeError('保护验证对应旧产物')
        for source,digest in r.get('sourceHashes',{}).items():
            if hashlib.sha256((s.HERE/source).read_bytes()).hexdigest()!=digest:raise RuntimeError('验证来源改变')
        digests[name]=hashlib.sha256(raw).hexdigest()
    s.payload();s.capture.payload()
    for name,digest in (('read_usb_link_once.py',s.pre.HOST_SHA),('usb_diagnostic_contract.py',s.pre.CONTRACT_SHA)):
        if hashlib.sha256((s.ROOT/'x1d/tools'/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('USB 来源改变')
    return digests

def packet(phase,kind,address=None,value=None,size=512):
    if phase not in ('stage','capture'):raise ValueError('未知阶段')
    if type(size) is not int or size not in (512,1024):raise ValueError('未知长度')
    if kind=='power-down' and phase=='stage' and address is None and value is None:
        return bytes.fromhex('1b02080100')+bytes(size-5)
    if kind=='read' and type(address) is int and address in ANCHORS and value is None:
        return bytes.fromhex('f4000801')+struct.pack('<I',address)+bytes(size-8)
    return (s if phase=='stage' else s.capture).request(kind,address,value,size)

def reply(kind,data,size):
    if kind in ('stage','power-down'):
        if type(data) is not bytes or len(data)!=size or data[:4]!=bytes.fromhex('1c020108'):
            raise ValueError('装载阶段回复不匹配')
        if data[4] not in ((0,1,3) if kind=='power-down' else (0,1)):raise ValueError('未知回复状态')
        return data[4]
    return s.capture.common.reply(kind,data,size)

class Native(usb.NativeWinUsb):
    def __init__(self,phase,kind,address,value):
        self.args=phase,kind,address,value;packet(*self.args);super().__init__()
    def write_query(self,size):
        if not self.prepared or self.sent or size!=self.packet_size:raise usb.UsbFailure('USB_REQUEST_DENIED')
        data=packet(*self.args,size);buf,count=usb.c.create_string_buffer(data,size),usb.U32()
        self.sent=True;self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buf,size,usb.c.byref(count),None),'USB_WRITE')
        return count.value

class IO:
    offline_model=False
    def __init__(self,authorization):
        if not isinstance(authorization,str) or not authorization.strip():raise ValueError('缺少本轮明确授权记录')
        self.validation=validate();self.authorization=authorization
        self.phase='stage';self.requests=self.writes=0;self.closed=True;self.failed=False;self.entries=[]
        self.power_down_sent=False
    def exchange(self,kind,address=None,value=None):
        packet(self.phase,kind,address,value)
        if self.failed or self.requests>=40000:raise RuntimeError('本轮停止，不能自动重试')
        if kind=='power-down' and self.power_down_sent:raise RuntimeError('关闭请求只能发送一次')
        if kind=='power-down':self.power_down_sent=True
        t=Native(self.phase,kind,address,value)
        row={'phase':self.phase,'kind':kind,'address':address,'value':value,'ok':False}
        try:
            size=usb.validate_interface(t.open());t.prepare()
            if kind in ('stage','power-down'):
                timeout=usb.U32(20000)
                t.check(t.winusb.WinUsb_SetPipePolicy(t.usb,0x82,3,4,usb.c.byref(timeout)),'USB_TIMEOUT_POLICY')
            if t.write_query(size)!=size:raise RuntimeError('USB 短写')
            result=reply(kind,t.read_reply(size),size)
            row.update(ok=True,result=result);return result
        except Exception:
            self.failed=True;raise
        finally:
            self.requests+=int(t.sent);self.writes+=int(t.sent and kind in ('write','stage','power-down'))
            self.closed=all(t.close().values());row.update(sent=int(t.sent),closed=self.closed);self.entries.append(row)
            if not self.closed:self.failed=True;raise RuntimeError('USB 句柄未关闭')
    def read(self,address):return self.exchange('read',address)
    def begin_capture(self,stager):
        if stager.io is not self or self.phase!='stage' or self.failed or not self.closed:
            raise RuntimeError('阶段会话不匹配')
        if not all(stager.record.get(k) for k in ('fpga_configured','task_barrier_confirmed','arena_cleared','irq_capture_may_follow')):
            raise RuntimeError('缺少阶段完成证据')
        self.phase='capture'

class Saved:
    def save(self):
        self.record.update(offline_model=False,authorization=self.io.authorization,validation_reports=self.io.validation,
                           transport_phase=self.io.phase)
        super().save()

class Stager(Saved,s.Stager):
    def __init__(self,io):
        if type(io) is not IO or io.phase!='stage' or io.failed:raise RuntimeError('不是本轮固定实机适配')
        validate();s.old.Loader.__init__(self,io)
    def power_down_once(self,farm):
        self.verify()
        for a in ANCHORS:
            if self.io.read(a)!=struct.unpack_from('<I',farm,a-0x100000)[0]:raise RuntimeError('原厂关闭入口改变')
        self.record['in_flight']={'original_power_down':True};self.save()
        result=self.io.exchange('power-down')
        self.record.update(in_flight=None,power_down_reply=result,original_deferred_shutdown_possible=result==3)
        self.save();return result

class Capture(Saved,s.capture.Loader):
    def __init__(self,io):
        if type(io) is not IO or io.phase!='capture' or io.failed:raise RuntimeError('尚未完成 FPGA 阶段')
        validate();s.old.Loader.__init__(self,io)

def save_transport(io,name):
    path=s.OUT/name
    if Path(name).name!=name or not name.endswith('.json'):raise ValueError('记录名称不符')
    path.write_text(json.dumps({'observedAt':datetime.now(timezone.utc).isoformat(),'authorization':io.authorization,
        'requests':io.requests,'writeOrControlRequests':io.writes,'closed':io.closed,'failed':io.failed,
        'entries':io.entries,'cameraShotsTriggered':0,'agentFlashTrials':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
