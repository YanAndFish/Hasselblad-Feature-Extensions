"""固定官方 X1D 1.25.0：离线执行电子快门配置创建，核对 +0x74 是否被初始化。
不连接设备；全部代码和数据仅位于 Unicorn 合成内存。
"""

import struct
import unicorn
from unicorn import arm_const
def emulate_mode6_config(farm, initial_extra):
    if len(farm)!=1808280 or __import__('hashlib').sha256(farm).hexdigest()!='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca':
        raise ValueError('fixed FARM mismatch')
    if type(initial_extra) is not int or not 0 <= initial_extra <= 0xffffffff:
        raise ValueError('synthetic value must be uint32')
    u=unicorn.Uc(unicorn.UC_ARCH_ARM,unicorn.UC_MODE_ARM)
    u.mem_map(0x100000,(len(farm)+4095)&~4095,unicorn.UC_PROT_READ|unicorn.UC_PROT_EXEC)
    u.mem_write(0x100000,farm)
    u.mem_map(0x6db000,0x1000,unicorn.UC_PROT_READ|unicorn.UC_PROT_WRITE)
    u.mem_map(0x1000000,0x10000,unicorn.UC_PROT_READ|unicorn.UC_PROT_WRITE)
    cfg=0x1001000
    u.mem_write(cfg+0x74,struct.pack('<I',initial_extra))
    for r,v in ((arm_const.UC_ARM_REG_C1_C0_2,0xf<<20),(arm_const.UC_ARM_REG_FPEXC,0x40000000),(arm_const.UC_ARM_REG_R0,6),(arm_const.UC_ARM_REG_R1,0),(arm_const.UC_ARM_REG_R2,cfg),(arm_const.UC_ARM_REG_SP,0x100f000),(arm_const.UC_ARM_REG_LR,0x100f800)):
        u.reg_write(r,v)
    allowed=((0x22f9f0,0x2305cc),(0x226974,0x226b90),(0x15ed40,0x15eed4),(0x22f69c,0x22f9f0),(0x234578,0x2348f4),(0x233c84,0x2341f4))
    executed=set()
    writes=[]
    def code_guard(uc,address,size,data):
        if not any(a<=address<z for a,z in allowed):
            raise RuntimeError('unreviewed code '+hex(address))
        executed.add(address)
    def write_guard(uc,access,address,size,value,data):
        if not any(a<=address and address+size<=z for a,z in ((cfg,cfg+0xd0),(0x6db2e8,0x6db3e8),(0x100e000,0x100f000))):
            raise RuntimeError('unexpected write '+hex(address))
        writes.append((address,size))
    u.hook_add(unicorn.UC_HOOK_CODE,code_guard)
    u.hook_add(unicorn.UC_HOOK_MEM_WRITE,write_guard)
    u.emu_start(0x22f9f0,0x100f800,count=100000,timeout=1000000)
    assert u.reg_read(arm_const.UC_ARM_REG_PC)==0x100f800
    assert u.reg_read(arm_const.UC_ARM_REG_R0)==0
    assert u.reg_read(arm_const.UC_ARM_REG_SP)==0x100f000
    result=bytes(u.mem_read(cfg,0xd0))
    assert struct.unpack_from('<I',result,0x74)[0]==initial_extra
    assert not any(a<cfg+0x78 and a+s>cfg+0x74 for a,s in writes)
    assert struct.unpack_from('<I',result,0x70)[0]==2582
    assert struct.unpack_from('<I',result,0x78)[0]==6320
    assert result[0x7d]==0
    return {'initial_extra':initial_extra,'result_extra':struct.unpack_from('<I',result,0x74)[0],'h_period':2582,'v_period':6320,'rolling_flag':0,'return':0,'unique_instructions':len(executed),'extra_field_written':False,'hardware_requests':0}
