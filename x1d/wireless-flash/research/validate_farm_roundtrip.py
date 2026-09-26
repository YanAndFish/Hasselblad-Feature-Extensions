"""固定 1.25.0 回显接收处理的离线复核；外部队列仅模拟。"""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'x1d/tools'))
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from binary import ArmElf
from audit_usb_diagnostic_path import INPUTS
from farm_diagnostic_binary import FarmApplication
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

def validate():
    if Path.cwd().resolve()!=ROOT: raise RuntimeError('Workspace mismatch')
    farm=FarmApplication()
    assert farm.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    modules={}
    for name in ('bridge','tunnel'):
        path,digest=INPUTS[name]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        modules[name]=ArmElf(path.read_bytes())
    bridge,tunnel=modules['bridge'],modules['tunnel']
    checks=[]
    for module,address,mnemonic,operand in (
        (farm,0x1e21a0,'movw','r2, #0x30f'),(farm,0x1e21a8,'beq','#0x1e22ac'),
        (farm,0x1e22b4,'bl','#0x1e1e1c'),(farm,0x1e1e38,'mov','r2, #0x310'),
        (farm,0x1e1e68,'bl','#0x15ed40'),(farm,0x1e1e74,'bl','#0x1e80d0'),
        (bridge,0x34600,'mov','r1, #1'),(bridge,0x345dc,'bl','#0x18da4'),
        (bridge,0x4e1b8,'movw','r1, #0x30f'),(bridge,0x4e1d8,'strb','r7, [r0, #4]'),
        (bridge,0x4e1dc,'strb','r2, [r1, #5]!'),(bridge,0x4e1e8,'cmp','r3, #0xff'),
        (bridge,0x4db98,'bl','#0x18fc0'),
        (bridge,0x54f08,'cmp','r0, #0x310'),(bridge,0x54f24,'b','#0x4f96c'),
        (bridge,0x4f990,'cmp','r2, r3'),(bridge,0x4f9b0,'cmp','r0, r1'),
        (bridge,0x4f9c4,'mov','r1, #1'),(bridge,0x4f9dc,'movw','r1, #0x30f'),
        (bridge,0x4f9e0,'bl','#0x4ef4c'),(bridge,0x4f238,'mov','r0, r4')):
        item=module.instructions(address,4)[0]
        # 动态 PLT 的调用地址另核符号，避免把猜测当事实。
        if address==0x4db98:
            assert bridge.name(int(item.op_str[1:],0))=='_ZNK12QDBusMessage15setDelayedReplyEb'
        else:
            assert (item.mnemonic,item.op_str)==(mnemonic,operand),(hex(address),item.op_str)
        checks.append({'address':hex(address),'bytes':bytes(item.bytes).hex(),'mnemonic':item.mnemonic,'operand':item.op_str})
    for ident,name,size in ((783,b'testd_test_method_req',257),(784,b'testd_test_method_resp',255)):
        assert tunnel.read(tunnel.word(0x4ae16034+4*ident),len(name)+1)==name+b'\0'
        assert tunnel.word(0x4adf8234+4*ident)==size
        assert farm.word(0x29d938+4*ident)==size
    cases=[]
    for pattern in (bytes(range(255)),bytes(reversed(range(255)))):
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(0x100000,0x1c0000); u.mem_write(0x100000,farm.data)
        u.mem_map(0x800000,0x10000)
        packet=struct.pack('<HBB',783,5,1)+bytes((0,255))+pattern
        u.mem_write(0x800000,packet)
        replies=[]; calls=[]
        def code(uc,address,size,_):
            if address==0x808000: uc.emu_stop(); return
            if address==0x15ed40:
                dst,src,length=(uc.reg_read(r) for r in (arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2))
                assert src==0x800006 and length==255 and 0x80e000<=dst<0x80f000
                uc.mem_write(dst,bytes(uc.mem_read(src,length)))
                calls.append('memcpy-model'); uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR)); return
            if address==0x1e80d0:
                src=uc.reg_read(arm.UC_ARM_REG_R0)
                replies.append(bytes(uc.mem_read(src,259))); calls.append('queue-model')
                uc.reg_write(arm.UC_ARM_REG_PC,uc.reg_read(arm.UC_ARM_REG_LR)); return
            assert 0x1e1e1c<=address<0x1e1e80 or 0x1e0a50<=address<0x1e0ad4,hex(address)
        def memory(uc,access,address,size,value,_):
            assert 0x80e000<=address and address+size<=0x80f000,hex(address)
        u.hook_add(UC_HOOK_CODE,code); u.hook_add(UC_HOOK_MEM_WRITE,memory)
        u.reg_write(arm.UC_ARM_REG_R0,0x800000); u.reg_write(arm.UC_ARM_REG_SP,0x80f000)
        u.reg_write(arm.UC_ARM_REG_LR,0x808000)
        u.emu_start(0x1e1e1c,0x808004,count=200)
        assert u.reg_read(arm.UC_ARM_REG_PC)==0x808000 and u.reg_read(arm.UC_ARM_REG_SP)==0x80f000
        assert replies==[struct.pack('<HBB',784,1,5)+pattern]
        assert calls==['memcpy-model','queue-model']
        assert bytes(u.mem_read(0x800000,len(packet)))==packet
        cases.append({'echoBytes':255,'replyDestination':5,'outsideStackInstructionWrites':0})
    out=HERE/'build/farm-roundtrip-probe'; out.mkdir(exist_ok=True)
    report={'passed':True,'firmware':'official X1D 1.25.0','farmSha256':farm.sha256,
            'msg2dbusSha256':INPUTS['bridge'][1],'checks':checks,'receiverCases':cases,
            'queueAndMemcpyModeled':True,'hardwareRequests':0,'transmitMeasured':False,
            'linuxRequest':{'service':'com.hasselblad.farm','path':'/farm','interface':'com.hasselblad.linkstatus','method':'testMethod','argument':0},
            'replyContentVerifiedByFactoryHandler':True,'requestBodyBytes':257,'replyBodyBytes':255}
    (out/'static-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'passed':True,'checks':len(checks),'receiverCases':len(cases),'hardwareRequests':0}

if __name__=='__main__': print(validate())
