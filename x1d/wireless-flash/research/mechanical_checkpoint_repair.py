"""仅处理 Windows 本地恢复文件的短暂共享冲突；不重试 USB 传输。"""
import hashlib
from pathlib import Path
import struct
import time
from types import MethodType

import farm_probe_loader as common

HERE=Path(__file__).resolve().parents[1]

def save_with_retry(loader):
    if not loader.path or loader.path.parent!=(HERE/'build').resolve():
        raise RuntimeError('Recovery path outside module')
    for attempt in range(20):
        try:
            return common.Loader.save(loader)
        except PermissionError as error:
            if getattr(error,'winerror',None) not in (None,5,32) or attempt==19:
                raise
            loader.record['local_checkpoint_retries']=loader.record.get('local_checkpoint_retries',0)+1
            time.sleep(0.025)

def attach_and_verify_partial(loader,module):
    """当前失败必须发生于尚未提交的 payload 字的本地 checkpoint。
    先逐字读回既有前缀、零尾部及全部原入口；只有完全匹配才允许原安装函数重入。
    """
    if loader.io.failed or not loader.io.closed or not loader.saved or loader.record.get('installed') or not loader.record.get('probe_executed'):
        raise RuntimeError('Not an inert partial payload')
    if loader.record.get('stage')!='installing_disarmed': raise RuntimeError('Wrong installation stage')
    pending=loader.record.get('in_flight',{})
    address=pending.get('address',0)
    payload=module.payload()
    if address%4 or not module.PAYLOAD_START<=address<module.PAYLOAD_START+len(payload):
        raise RuntimeError('Not a pending payload word')
    if pending.get('value')!=struct.unpack_from('<I',payload,address-module.PAYLOAD_START)[0]:
        raise RuntimeError('Pending value mismatch')
    if any(loader.io.read(a)!=v for a,v in module.ORIGINAL_HOOKS.items()):
        raise RuntimeError('A capture hook is already active')
    for off in range(0,len(payload),4):
        target=module.PAYLOAD_START+off
        expected=struct.unpack_from('<I',payload,off)[0] if target<address else 0
        if loader.io.read(target)!=expected: raise RuntimeError('Partial payload mismatch')
    loader.save=MethodType(save_with_retry,loader)
    loader.record.update(checkpoint_handler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         verified_inert_prefix_bytes=address-module.PAYLOAD_START,
                         local_checkpoint_failure_before_usb=True,in_flight=None)
    loader.save()
    return {'verified_prefix_bytes':address-module.PAYLOAD_START,'all_hooks_original':True,
            'transport_retried':False,'hardware_writes':0}
