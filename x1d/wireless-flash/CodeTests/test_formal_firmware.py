"""正式候选：编码、真实灯端分支、功率/同步类型隔离及共享缓冲恢复。全部离线。"""
from pathlib import Path
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
import build_formal_firmware as build
from test_manual_power_candidate import Machine,STATE,CONTEXT,PHY,D11,RECEIVER_SHA,render
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as arm

def lamp_check(frames):
    firmware=(HERE/'build/receiver-reference/AD400pro_V1.50.bin').read_bytes()
    assert hashlib.sha256(firmware).hexdigest()==RECEIVER_SHA
    cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    cpu.mem_map(0,0x20000);cpu.mem_write(0x3000,firmware)
    cpu.mem_map(0x20000000,0x10000)
    stop=0x1f000; flash=[]; writes=[]
    def code(u,address,size,_):
        if address==stop: u.emu_stop(); return
        if address==0xda14: flash.append(address);u.emu_stop();return
        assert (0xc134<=address<0xc478 or 0xdef6<=address<0xdf10 or 0xdc00<=address<0xdd30),hex(address)
    def write(u,access,address,size,value,_):
        assert 0x20000000<=address<0x20010000,hex(address)
        if address<0x2000e000: writes.append((address,size,value))
    cpu.hook_add(UC_HOOK_CODE,code);cpu.hook_add(UC_HOOK_MEM_WRITE,write)
    def invoke(address,command,value):
        flash.clear();writes.clear()
        cpu.reg_write(arm.UC_ARM_REG_SP,0x2000fff0);cpu.reg_write(arm.UC_ARM_REG_LR,stop|1)
        for reg,val in zip((arm.UC_ARM_REG_R0,arm.UC_ARM_REG_R1,arm.UC_ARM_REG_R2),(address,command,value)):
            cpu.reg_write(reg,val)
        cpu.emu_start(0xc135,stop+2,count=3000)
        assert cpu.reg_read(arm.UC_ARM_REG_PC) in (stop,0xda14)
    power_cases=0
    for index,frame in enumerate(frames[:5*82]):
        for matches in (True,False):
            cpu.mem_write(0x20000000,bytes(0x2000))
            target=frame[9]
            cpu.mem_write(0x20000123,bytes((target if matches else 0x0a+(target-0x0a+1)%5,)))
            cpu.mem_write(0x20000132,b'\x01');cpu.mem_write(0x20000133,b'\xfe')
            invoke(target,0xbc,frame[11])
            assert not flash
            assert writes==([(0x20000133,1,frame[11])] if matches else [])
            assert cpu.mem_read(0x20000133,1)[0]==(frame[11] if matches else 254)
            power_cases+=1
    trigger_cases=0
    for group in range(5):
        for active in (False,True):
            for address in (0x0a+group,0x0a+(group+1)%5,0x50):
                cpu.mem_write(0x20000000,bytes(0x2000))
                cpu.mem_write(0x20000123,bytes((0x0a+group,)))
                cpu.mem_write(0x20000132,b'\x01');cpu.mem_write(0x20000162,b'\x01')
                # 先让参考固件自己处理功率/关闭消息，再处理普通引闪。
                invoke(0x0a+group,0xbc,40 if active else 255)
                assert not flash
                invoke(address,0xb4,9)
                assert bool(flash)==(active and address in (0x50,0x0a+group)),(group,active,address)
                trigger_cases+=1
    return power_cases,trigger_cases

def run():
    assert Path.cwd().resolve()==ROOT
    out=build.OUT
    manifest=json.loads((out/'firmware-build.json').read_text(encoding='utf-8'))
    blob=(out/'formal-wltest.bin').read_bytes();assert hashlib.sha256(blob).hexdigest()==manifest['sha256']
    for name,digest in manifest['sourceHashes'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    baseline,counts,lut,prefix=build.power.inputs()
    expected=json.loads((out/'expected-hashes.json').read_text(encoding='ascii'))
    assert hashlib.sha256((out/'expected-hashes.json').read_bytes()).hexdigest()==manifest['expectedHashesSha256']
    lut_path=out/'reference-lut.bin';lut_path.write_bytes(struct.pack('<1024I',*lut))
    source=HERE/'CodeTests/godox_formal_wave.test.c';binary=out/'godox_formal_wave.test.exe'
    compiler=ROOT/'.research-cache/x1d-1.25.0/toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    env=dict(os.environ)
    for key,name in [('ZIG_GLOBAL_CACHE_DIR','global-cache'),('ZIG_LOCAL_CACHE_DIR','local-cache'),('TEMP','tmp'),('TMP','tmp')]:env[key]=str(out/name)
    subprocess.run([str(compiler),'cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],env=env,check=True,capture_output=True,timeout=60)
    lines=subprocess.run([str(binary),str(lut_path)],check=True,capture_output=True,text=True,timeout=30).stdout.splitlines()
    assert len(lines)==build.FIRE_INDEX+1
    frames=[]
    for i,line in enumerate(lines):
        raw,hash_value=line.split();frames.append(bytes.fromhex(raw))
        assert frames[-1]==build.frame(i,prefix) and int(hash_value,16)==expected[i]
    power_cases,trigger_cases=lamp_check(frames)
    print(str(build.FIRE_INDEX+1)+' waveform vectors and reference receiver branches passed.',flush=True)
    checks=[]
    def check(name,condition):assert condition,name;checks.append(name)
    m=Machine(blob)
    check('default-disabled-marker',m.invoke(0)==0x5854 and m.invoke(40)==9 and m.invoke(48)==9 and m.starts==0)
    allowed={0,14,15,16,17,18,19,20,26,27,40,48}
    for selector in list(set(range(512))-allowed)+[512+build.FIRE_INDEX,8191,11392,0xffff,0xffffffff]:
        assert m.invoke(selector)==0xfffd
    check('legacy-selector-rejection',not m.calls and not m.sample_writes and not m.starts)
    for index in (0,80,81,82,409,410,411,491,492,1230,1311,1312,1313,1342,1343,build.FIRE_INDEX):
        m=Machine(blob);assert m.invoke(26)==1
        selector=14 if index==build.FIRE_INDEX else 512+index
        check('prepare-'+str(index),m.invoke(selector)==1 and m.starts==0)
        check('samples-'+str(index),m.samples==render(build.runs(index,counts,prefix),lut) and m.get(STATE+4)==expected[index])
        rejected=48 if index==build.FIRE_INDEX else 40
        check('wrong-type-'+str(index),m.invoke(rejected)==3 and m.starts==0)
        accepted=40 if index==build.FIRE_INDEX else 48
        check('send-'+str(index),m.invoke(accepted)==1 and m.starts==1)
        check('release-'+str(index),m.invoke(27)==1 and m.lock_depth==0)
    m=Machine(blob);assert m.invoke(26)==1 and m.invoke(14)==1
    for group in range(5):
        assert m.invoke(512+group*82+40)==1 and m.invoke(48)==1
        check('sync-rejected-during-power-'+str(group),m.invoke(40)==3 and m.starts==group+1)
    check('restore-sync-before-fire',m.invoke(14)==1 and m.get(STATE+4)==expected[build.FIRE_INDEX] and m.invoke(40)==1 and m.starts==6)
    check('power-rejected-after-restore',m.invoke(48)==3 and m.starts==6)
    assert m.invoke(27)==1
    for name,address,value in [('hash',STATE+4,0),('expected',CONTEXT+16,0),('index',CONTEXT+12,build.FIRE_INDEX+1),('not-ready',CONTEXT+8,0)]:
        m=Machine(blob);assert m.invoke(26)==1 and m.invoke(14)==1;m.put(address,value)
        check('reject-'+name,m.invoke(40)==3 and m.starts==0)
        assert m.invoke(27)==1
    m=Machine(blob);assert m.invoke(26)==1;m.tamper=True
    check('sample-corruption-disables-both',m.invoke(14)==13 and m.invoke(40)==3 and m.invoke(48)==3 and m.starts==0)
    assert m.invoke(27)==1
    m=Machine(blob);assert m.invoke(26)==1 and m.invoke(14)==1;m.setup_busy=True
    check('phy-busy-cleans-up',m.invoke(40)==8 and m.starts==0 and m.get(D11+0x492,2)==2 and m.get(CONTEXT+8)==0)
    assert m.invoke(27)==1
    report={'passed':True,'firmwareSha256':manifest['sha256'],'waveformVectors':build.FIRE_INDEX+1,
            'referenceReceiverSha256':RECEIVER_SHA,'referencePowerCases':power_cases,'referenceBroadcastAndOffCases':trigger_cases,
            'referenceTriggerStopsBeforePhysicalFlashFunction':True,'checks':checks,'checkCount':len(checks),
            'sharedBufferRestoredBeforeSync':True,'hardwareRequests':0,'installed':False,'lampReceptionVerified':False,
            'sourceHashes':{str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__),source,HERE/'CodeTests/test_manual_power_candidate.py')}}
    (out/'firmware-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','waveformVectors','referencePowerCases','referenceBroadcastAndOffCases','checkCount','hardwareRequests','installed')}))

if __name__=='__main__':run()
