"""固定 Linux hold 查询；只定义协议和单次传输，不创建/释放/续期 hold。"""
import hashlib,json,secrets,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'x1d/tools'))
MIN_REMAINING_MS=180000
SEGMENT_MS=120000
COMMAND='/tmp/hbl-wireless-flash/formal-system-check --require-held-min-ms 180000'
SUCCESS=b'system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1\n'
TIMEOUT_MS=20000
MAX_CHECKS=96

def identity():
    spec=json.loads((HERE/'CodeTests/Fixtures/NativeHold.json').read_text(encoding='utf-8'))
    if (spec['command']!=COMMAND or spec['successOutput']!=SUCCESS.decode('ascii') or
        spec['minimumRemainingMs']!=MIN_REMAINING_MS or spec['segmentBudgetMs']!=SEGMENT_MS):
        raise ValueError('hold fixed contract changed')
    for name,h in spec['sourceHashes'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=h:raise ValueError('hold checker/source identity changed: '+name)
    if spec.get('targetExecutableSha256') and spec['sourceHashes'].get('../wireless-flash/build/formal-flash-program/formal-system-check')!=spec['targetExecutableSha256']:
        raise ValueError('hold executable must be bound in sources')
    return spec

def helpers():
    # 上游仅提取三个已审阅纯函数，不执行其 main 或 USB 入口。
    if hashlib.sha256((ROOT/'x1d/tools/sutest_ram_contract.py').read_bytes()).hexdigest()!='65f92a335d3aa681aa2d3d8b56f39e655d026f97ef7af5a69b8ecc6482922abf':raise ValueError('hold framing helper changed')
    from sutest_ram_contract import _reviewed_helpers,REQUEST_HEADER,RESPONSE_HEADER
    make,crc=_reviewed_helpers();return make,crc,REQUEST_HEADER,RESPONSE_HEADER

def query(token):
    if type(token)!=int or not 1<=token<=0xffffffff:raise ValueError('hold token')
    make,crc,request,_=helpers();packet=bytearray(make(COMMAND))
    if len(packet)!=257 or packet[:5]!=request:raise ValueError('hold request framing')
    struct.pack_into('<I',packet,13,token)
    if struct.unpack_from('<I',packet,17)[0]!=crc(packet[21:]):raise ValueError('hold request CRC')
    return bytes(packet)+bytes(255)

def reply(packet,token):
    _,crc,_,response=helpers()
    if type(packet)!=bytes or len(packet)!=512 or packet[:5]!=response:raise ValueError('hold reply route/length')
    body=packet[5:257];kind,operation,echoed,checksum,result=struct.unpack_from('<5I',body)
    if (kind,operation,echoed)!=(52,0,token) or checksum!=crc(body[16:]):raise ValueError('hold reply identity/CRC')
    if result or body[20:]!=SUCCESS+bytes(232-len(SUCCESS)):raise ValueError('hold checker not ready')
    return {'matched':True,'exitCode':0,'output':SUCCESS.decode('ascii').rstrip('\n')}

def transport(io,packet):
    # 与既有 Linux 命令帧相同的 WinUSB 发送/接收；没有通用命令参数。
    import read_usb_link_once as usb
    class FixedHoldUsb(usb.NativeWinUsb):
        def write_query(self,size):
            if not self.prepared or self.sent or size!=512 or self.packet_size!=512:raise usb.UsbFailure('USB_REQUEST_DENIED')
            buffer=usb.c.create_string_buffer(packet,512);count=usb.U32();self.sent=True
            self.check(self.winusb.WinUsb_WritePipe(self.usb,2,buffer,512,usb.c.byref(count),None),'USB_WRITE')
            return count.value
        def read_reply(self,size):
            if size!=512:raise usb.UsbFailure('USB_PACKET_SIZE_UNREVIEWED')
            timeout=usb.U32(TIMEOUT_MS)
            self.check(self.winusb.WinUsb_SetPipePolicy(self.usb,0x82,3,4,usb.c.byref(timeout)),'USB_TIMEOUT_POLICY')
            buffer=usb.c.create_string_buffer(size);count=usb.U32()
            try:
                self.check(self.winusb.WinUsb_ReadPipe(self.usb,0x82,buffer,size,usb.c.byref(count),None),'USB_READ')
                return buffer.raw[:count.value]
            finally:usb.c.memset(buffer,0,size)
    return FixedHoldUsb()

def check(io,label):
    if (io.failed or io.transfer_active or not io.closed or not io.hold_permitted or io.wake_live or
        io.hold_requests>=MAX_CHECKS or io.requests>=io.request_limit or
        (io.segment_deadline is not None and io.clock()>=io.segment_deadline) or
        (io.journal and (io.journal.record.get('inFlight') is not None or io.journal.record.get('cacheInFlight') is not None))):
        io.failed=True;raise RuntimeError('hold check requires parked serial boundary')
    io.hold_permitted=False;started=io.clock();token=secrets.randbelow(0xffffffff)+1;packet=query(token)
    item={'boundary':label,'matched':False,'closed':True,'submitted':False};t=None
    try:
        if io.journal:io.journal.begin(io.phase,('hold_check',0,token))
        io.transfer_active=True;t=io.hold_transport(packet,token);io.closed=False
        if io.interface_size(t.open())!=512:raise RuntimeError('hold requires 512-byte command interface')
        t.prepare()
        if io.clock()-started>=TIMEOUT_MS/1000:raise RuntimeError('hold dispatch deadline')
        io.requests+=1;io.hold_requests+=1;item['submitted']=True
        if t.write_query(512)!=512:raise RuntimeError('short hold query')
        item.update(reply(t.read_reply(512),token))
        if io.clock()-started>=TIMEOUT_MS/1000:raise RuntimeError('stale hold reply')
    except BaseException as error:
        io.failed=True;item['errorType']=type(error).__name__;raise
    finally:
        if t is not None:
            try:io.closed=all(t.close().values())
            except BaseException:io.closed=False
            item['closed']=io.closed
            if not io.closed:io.failed=True
        io.transfer_active=False;io.hold_results.append(item)
    if not io.closed:raise RuntimeError('hold USB closure failed')
    io.segment_deadline=started+SEGMENT_MS/1000
    if io.journal:
        io.journal.record.update(holdChecks=list(io.hold_results),holdRequests=io.hold_requests,
            requests=io.requests,writeRequests=io.writes,hardwareRequests=io.requests if io.is_hardware else 0,allHandlesClosed=io.closed)
        try:io.journal.complete()
        except BaseException:io.failed=True;raise
    return item
