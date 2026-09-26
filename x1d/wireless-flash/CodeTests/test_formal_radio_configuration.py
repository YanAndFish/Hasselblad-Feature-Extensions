"""官方引闪器/接收器原始指令与动态频道候选的离线交叉核对。无设备访问。"""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import os
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
sys.path.insert(0,str(HERE/'research'))
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
from unicorn import arm_const as arm
from test_manual_power_candidate import Machine,PHY,STATE,CONTEXT,RECEIVER_SHA
import build_formal_firmware as build
TX_SHA='2e2b8a3b5ff70e62c4acddc406b055ea2625e4833a213e81863f96c0da5a911b'

def transmitter_reference():
    raw=(HERE/'build/transmitter-reference/X3pro_C_v1.22_app.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==TX_SHA
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    u.mem_map(0x08030000,0x200000);u.mem_write(0x08030000,raw)
    u.mem_map(0x20000000,0x10000)
    stop=0x0803f09a;writes=[]
    def hook(cpu,address,size,_):
        if address==stop:cpu.emu_stop();return
        if address==0x0803e71c:
            r=[cpu.reg_read(getattr(arm,'UC_ARM_REG_R'+str(i))) for i in range(3)]
            assert r[0] in (4,5) and r[2]==1
            writes.append((r[0],bytes(cpu.mem_read(r[1],1))[0]))
            cpu.reg_write(arm.UC_ARM_REG_PC,cpu.reg_read(arm.UC_ARM_REG_LR));return
        if address in (0x0803b5dc,0x0803e88c):
            cpu.reg_write(arm.UC_ARM_REG_PC,cpu.reg_read(arm.UC_ARM_REG_LR));return
        assert 0x0803f040<=address<0x0803f09a or 0x0803ce4e<=address<0x0803ce9a or 0x0803cf34<=address<0x0803cf4e or 0x0803ef90<=address<0x0803efbe,hex(address)
    u.hook_add(UC_HOOK_CODE,hook)
    ids=[]
    for id_value in range(100):
        writes.clear();u.reg_write(arm.UC_ARM_REG_R0,id_value)
        u.reg_write(arm.UC_ARM_REG_SP,0x2000fff0);u.reg_write(arm.UC_ARM_REG_LR,stop|1)
        u.emu_start(0x0803f041,stop+2,count=2000)
        assert len(writes)==2 and [x[0] for x in writes]==[4,5]
        ids.append(bytes(x[1] for x in writes))
    assert ids[0]==bytes.fromhex('c368') and ids[5]==bytes.fromhex('2091')
    groups=[]
    for group in range(16):
        u.mem_write(0x20000000,bytes(0x3000))
        u.mem_write(0x20001000,bytes((0,40,0,0xc0,0,0,0,0,0,0)))
        u.mem_write(0x20001100,bytes((0,39,0,0xc0,0,0,0,0,0,0)))
        for reg,value in ((arm.UC_ARM_REG_R4,0x20001000),(arm.UC_ARM_REG_R6,0x20001100),(arm.UC_ARM_REG_R5,group),(arm.UC_ARM_REG_SP,0x2000fff0)):
            u.reg_write(reg,value)
        u.emu_start(0x0803ce4f,0x0803ce9a,count=2000)
        address=u.reg_read(arm.UC_ARM_REG_R8);groups.append(address)
        assert u.mem_read(0x20001d07,1)==b'\x02'
        assert u.mem_read(0x20001aac,8)==bytes((0xa9,address,0xbc,40))*2
        assert u.mem_read(0x20001101,1)==b'\x28'
    assert groups==list(range(10,16))+list(range(10))
    return ids,groups

def receiver_reference():
    raw=(HERE/'build/receiver-reference/AD400pro_V1.50.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==RECEIVER_SHA
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    u.mem_map(0x08000000,0x20000);u.mem_write(0x08003000,raw)
    u.mem_map(0x20000000,0x10000)
    stop=0x0801f000;writes=[]
    def hook(cpu,address,size,_):
        if address==stop:cpu.emu_stop();return
        if address==0x0800e1fa:
            writes.append((cpu.reg_read(arm.UC_ARM_REG_R0),cpu.reg_read(arm.UC_ARM_REG_R1)))
            cpu.reg_write(arm.UC_ARM_REG_PC,cpu.reg_read(arm.UC_ARM_REG_LR));return
        if address in (0x0800df88,0x0800e2bc):
            cpu.reg_write(arm.UC_ARM_REG_PC,cpu.reg_read(arm.UC_ARM_REG_LR));return
        assert 0x0800cabc<=address<0x0800caf8 or 0x0800c134<=address<0x0800c478 or 0x0800def6<=address<0x0800df10,hex(address)
    u.hook_add(UC_HOOK_CODE,hook)
    words=[]
    for channel in range(32):
        writes.clear();u.reg_write(arm.UC_ARM_REG_R0,channel)
        u.reg_write(arm.UC_ARM_REG_SP,0x2000fff0);u.reg_write(arm.UC_ARM_REG_LR,stop|1)
        u.emu_start(0x0800cabd,stop+2,count=1000)
        assert [v[0] for v in writes]==[13,14,15]
        words.append(int.from_bytes(bytes(v[1] for v in writes),'big'))
    for group in range(10,15):
        for initial in (0,1,2):
            for on in (0,1):
                u.mem_write(0x20000000,bytes(0x3000))
                u.mem_write(0x20000123,bytes((group,)))
                u.mem_write(0x20000125,bytes((55,initial,2,44)))
                for reg,value in ((arm.UC_ARM_REG_R0,group),(arm.UC_ARM_REG_R1,0xd3),(arm.UC_ARM_REG_R2,on),(arm.UC_ARM_REG_SP,0x2000fff0),(arm.UC_ARM_REG_LR,stop|1)):
                    u.reg_write(reg,value)
                u.emu_start(0x0800c135,stop+2,count=2000)
                state=u.mem_read(0x20000126,1)[0]
                assert state==(initial if on and initial else 2 if on else 0),(group,initial,on,state)
    return words

SOURCE=r'''
#include "../../native/formal_prepared_request.h"
#include <stdio.h>
int main(void) {
    for(unsigned id=0;id<100;++id) { uint8_t f[12];if(!hbl_formal_frame_config(f,0,id)) return 1;printf("ID %u %02x%02x\n",id,f[4],f[5]); }
    for(unsigned ch=1;ch<=32;++ch) {
        printf("CH %u %u %u %u\n",ch,hbl_formal_chanspec(ch),hbl_formal_phase_step(ch,1),hbl_formal_phase_step(ch,0));
        const unsigned ids[]={0,5,99};
        for(unsigned j=0;j<3;++j) { uint32_t h=0;if(!hbl_formal_wave_hash(&h,HBL_FORMAL_FIRE_INDEX,ch,ids[j],hbl_formal_lut)) return 2;printf("HASH %u %u %u\n",ch,ids[j],h); }
    }
    for(unsigned i=0;i<HBL_FORMAL_WAVES;++i) { uint8_t f[12];hbl_formal_frame(f,i);printf("FRAME %u ",i);for(unsigned j=8;j<12;++j) printf("%02x",f[j]);puts(""); }
    return 0;
}
'''

def run():
    assert Path.cwd().resolve()==ROOT
    ids,groups=transmitter_reference();words=receiver_reference()
    out=build.OUT;source=out/'configuration-check.c';source.write_text(SOURCE,encoding='ascii')
    exe=out/'configuration-check.exe';env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:env[key]=str(out/name)
    zig=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    subprocess.run([str(zig),'cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],env=env,check=True,capture_output=True,timeout=60)
    lines=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=30).stdout.splitlines()
    hashes={};channels={};_,counts,lut,_=build.power.inputs()
    for line in lines:
        values=line.split();kind=values.pop(0)
        if kind=='ID':assert bytes.fromhex(values[1])==ids[int(values[0])]
        elif kind=='CH':
            ch,spec,one,zero=map(int,values)
            wifi=(round(Fraction(words[ch-1]*26*4,65536))-2412*4)//20+1
            expected=int(Fraction(261686886*5+2,5)+(words[ch-1]-words[4])*Fraction(26*65536,40)-(wifi-2)*Fraction(1<<32,8))
            assert spec==0x1000+wifi and one==expected and zero-one==13418496
            channels[ch]=(spec,one,zero)
        elif kind=='FRAME':
            index=int(values[0]);frame=bytes.fromhex(values[1])
            if index==build.FIRE_INDEX:assert frame==bytes((0xa9,0x50,0xb4,9))
            elif index>=build.LAMP_BASE:
                group,on=divmod(index-build.LAMP_BASE,2);assert frame==bytes((0xa9,groups[group],0xd3,on))
            else:
                group,value=divmod(index,82);assert frame==bytes((0xa9,groups[group],0xbc,255 if value==81 else value))
        elif kind=='HASH':
            ch,id_value,actual=map(int,values);spec,one,zero=channels[ch]
            frame=b'\xaa'*4+ids[id_value]*2+bytes((0xa9,0x50,0xb4,9))
            runs=[(n,0,one if frame[i//8]&(1<<(7-i%8)) else zero) for i,n in enumerate(counts)]
            assert build.power.wave_hash(runs,lut)==actual
            hashes[ch,id_value]=actual
        else:raise AssertionError(kind)
    assert len(hashes)==96 and len(channels)==32
    blob=(out/'formal-wltest.bin').read_bytes();m=Machine(blob)
    assert m.invoke(0)==0x5854 and m.invoke(8192)==9 and m.starts==0
    arm_cases=0
    for ch in range(1,33):
        id_value=(0,5,99)[ch%3];spec,_,_=channels[ch]
        m=Machine(blob);m.put(PHY+0x10e,spec,2)
        assert m.invoke(26)==1 and m.invoke(8192+(ch-1)*100+id_value)==1
        assert m.invoke(19)==ch and m.invoke(20)==id_value and m.invoke(40)==3
        assert m.invoke(14)==1 and m.get(STATE+4)==hashes[ch,id_value]
        assert m.invoke(40)==1 and m.starts==1
        assert m.invoke(8192+(ch-1)*100+id_value)==1 and m.invoke(40)==3 and m.starts==1
        assert m.invoke(14)==1
        m.put(PHY+0x10e,0x1000+(spec&255)%11+1,2)
        assert m.invoke(40)==4 and m.starts==1
        assert m.invoke(27)==1 and m.lock_depth==0
        arm_cases+=1
    report={'passed':True,'firmwareSha256':hashlib.sha256(blob).hexdigest(),'transmitterSha256':TX_SHA,
        'receiverSha256':RECEIVER_SHA,'officialIdCases':100,'officialGroupAddressAndPowerCases':16,
        'officialChannelCases':32,'officialModelingSwitchCases':30,'dynamicWaveformHashes':96,
        'armChannelAndInvalidationCases':arm_cases,'idOffSyncWord':'c368','hardwareRequests':0,
        'installed':False,'physicalExpandedChannelsMeasured':False,
        'sourceHashes':{str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),HERE/'native/godox_formal_wave.h',HERE/'native/formal_prepared_request.h')}}
    (out/'configuration-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sourceHashes','transmitterSha256','receiverSha256','firmwareSha256')}))

if __name__=='__main__':run()
