"""双中断实机前置核对：仅固定 RAM/GIC 读取，无写入或配置入口。"""
import hashlib
import struct
from pathlib import Path
import mechanical_irq_stage_loader as stage
usb=stage.old.usb
RESOURCE_STATES=tuple(0x6dae18+44*i+12 for i in range(26))
RESOURCE_21_METADATA=tuple(0x6dae18+44*21+i for i in (0,24,28,36))

def request(kind,address=None,size=512):
    if kind not in ('version','read'):raise ValueError('前置核对只允许读取')
    if kind=='read' and type(address) is int and address in RESOURCE_STATES+RESOURCE_21_METADATA:
        if type(size) is not int or size not in (512,1024):raise ValueError('读取长度不匹配')
        data=bytes.fromhex('f4000801')+struct.pack('<I',address)
        return data+bytes(size-len(data))
    return stage.request(kind,address,None,size)

class ReadUsb(usb.NativeWinUsb):
    def __init__(self,kind,address):
        request(kind,address);self.args=kind,address;super().__init__()
    def write_query(self,size):
        if not self.prepared or self.sent or size!=self.packet_size:raise usb.UsbFailure('USB_REQUEST_DENIED')
        packet=request(*self.args,size)
        buf,count=usb.c.create_string_buffer(packet,size),usb.U32()
        self.sent=True
        self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buf,size,usb.c.byref(count),None),'USB_WRITE')
        return count.value

class ReadIO:
    def __init__(self):
        if Path.cwd().resolve()!=stage.ROOT.resolve():raise RuntimeError('工作区不匹配')
        for name,digest in (('read_usb_link_once.py',stage.pre.HOST_SHA),('usb_diagnostic_contract.py',stage.pre.CONTRACT_SHA)):
            if hashlib.sha256((stage.ROOT/'x1d/tools'/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('接口源码变化')
        self.requests=0;self.writes=0;self.failed=False;self.closed=True;self.entries=[]
    def exchange(self,kind,address=None):
        request(kind,address)
        if self.failed or self.requests>=2500:raise RuntimeError('本轮读取已停止')
        t=ReadUsb(kind,address);row={'kind':kind,'address':address,'ok':False}
        try:
            size=usb.validate_interface(t.open());t.prepare()
            if t.write_query(size)!=size:raise RuntimeError('读取请求未完整发送')
            value=stage.pre.reply(kind,t.read_reply(size),size)
            row.update(ok=True,value=value);return value
        except Exception:
            self.failed=True;raise
        finally:
            self.requests+=int(t.sent);self.closed=all(t.close().values())
            row.update(submitted=int(t.sent),closed=self.closed);self.entries.append(row)
            if not self.closed:self.failed=True;raise RuntimeError('USB 关闭未完成')
    def read(self,address):return self.exchange('read',address)
