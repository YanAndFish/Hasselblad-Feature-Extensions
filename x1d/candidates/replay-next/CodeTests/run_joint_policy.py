"""执行实际 ARM 只读保持准入；文件元数据、时钟和 sscanf 是显式替身。"""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import subprocess
from arm_machine import ArmMachine,ArmElf,NATIVE,HEAP,SHIM,R,UC_HOOK_CODE,Uc,UC_ARCH_ARM,UC_MODE_ARM
from binary import CACHE,BASELINE
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2];OUT=HERE/'artifacts/joint-policy-tests'

class Machine(ArmMachine):
    def __init__(self,elf,case):
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.uc.mem_map(HEAP,0x10000);self.uc.mem_map(SHIM,0x100000);self.uc.mem_map(0x70000000,0x100000)
        self.uc.reg_write(R.UC_ARM_REG_C1_C0_2,0xF<<20);self.uc.reg_write(R.UC_ARM_REG_FPEXC,0x40000000)
        self.symbols={s.name:NATIVE+s['st_value'] for s in elf.symbols if s.name and s['st_value'] and s['st_shndx']!='SHN_UNDEF'}
        segments=[s for s in elf.elf.iter_segments() if s['p_type']=='PT_LOAD']
        lo=min(s['p_vaddr'] for s in segments)&~4095;hi=(max(s['p_vaddr']+s['p_memsz'] for s in segments)+4095)&~4095
        self.uc.mem_map(NATIVE+lo,hi-lo)
        for s in segments:self.uc.mem_write(NATIVE+s['p_vaddr'],s.data())
        self.imports={};self.entries={};self.last_calls=[];self.errno=HEAP;self.case=case;self.fd={};self.paths=[]
        self.relocate(elf,NATIVE);self.uc.hook_add(UC_HOOK_CODE,self.shim,begin=SHIM,end=SHIM+0xfffff)
    def shim(self,uc,at,size,context):
        name=self.entries[at];self.last_calls=(self.last_calls+[name])[-12:]
        if name=='__errno_location':self.ret(self.errno)
        elif name=='getpid':self.ret(404)
        elif name=='clock_gettime':
            assert self.arg(0)==1
            self.uc.mem_write(self.arg(1),struct.pack('<II',1000,0));self.ret()
        elif name=='__lxstat64':
            assert self.arg(0)==3;path=self.cstring(self.arg(1));self.paths.append(path)
            assert path in ['/tmp/hbl-x1d-combined','/tmp/hbl-x1d-combined/install-state','/tmp/hbl-x1d-combined/install-state/hold.release']
            if path.endswith('hold.release'):
                self.put(self.errno,13 if self.case=='release-unreadable' else 2)
                self.ret(0 if self.case=='released' else -1)
            else:
                b=bytearray(104);struct.pack_into('<III',b,16,0o40700 if self.case!='directory-symlink' else 0o120777,1,0)
                self.uc.mem_write(self.arg(2),bytes(b));self.ret()
        elif name=='open':
            path=self.cstring(self.arg(0));self.paths.append(path)
            assert path in ['/tmp/hbl-x1d-combined/install-state/hold.deadline','/tmp/hbl-x1d-combined/install-state/hold.pulse']
            assert self.arg(1)&0x8000 and self.arg(1)&0x80000 and not self.arg(1)&3
            deadline=1200001 if self.case=='deadline-changed' else 1200000
            if path.endswith('deadline'):content=f'HHD1 {deadline}\n'
            else:
                pid=403 if self.case=='wrong-pid' else 404
                pulse={'stale':997999,'future':1000001}.get(self.case,999999)
                content=f'HPI1 {pid} 1200000 {pulse}\n'
                if self.case=='extra-field':content+='unexpected'
            fd=10+len(self.fd);self.fd[fd]=content.encode();self.ret(fd)
        elif name=='__fxstat64':
            assert self.arg(0)==3;b=bytearray(104)
            struct.pack_into('<III',b,16,0o100644 if self.case=='public-file' else 0o100600,2 if self.case=='hardlink' else 1,0)
            struct.pack_into('<q',b,48,len(self.fd[self.arg(1)]));self.uc.mem_write(self.arg(2),bytes(b));self.ret()
        elif name=='read':
            b=self.fd[self.arg(0)]
            if self.case=='short-read':b=b[:-1]
            self.uc.mem_write(self.arg(1),b);self.ret(len(b))
        elif name=='close':del self.fd[self.arg(0)];self.ret()
        elif name in ('sscanf','__isoc99_sscanf'):
            text=self.cstring(self.arg(0));fmt=self.cstring(self.arg(1))
            pattern=r'HHD1\s+(\d+)\s*(\S)?' if fmt.startswith('HHD1') else r'HPI1\s+(\d+)\s+(\d+)\s+(\d+)\s*(\S)?'
            m=re.fullmatch(pattern,text)
            if not m:
                # 用例额外尾字段只需呈现 sscanf 多读到 %c 的结果。
                if self.case=='extra-field':self.ret(4);return
                self.ret(0);return
            values=m.groups();count=0
            for i,v in enumerate(values):
                if v is None:break
                if i==len(values)-1:self.uc.mem_write(self.arg(2+i),v.encode()[:1])
                else:self.uc.mem_write(self.arg(2+i),struct.pack('<I' if fmt.startswith('HPI1') and i==0 else '<Q',int(v)))
                count+=1
            self.ret(count)
        elif name in ('memcpy','memmove'):
            self.uc.mem_write(self.arg(0),bytes(self.uc.mem_read(self.arg(1),self.arg(2))));self.ret(self.arg(0))
        elif name=='memset':self.uc.mem_write(self.arg(0),bytes([self.arg(1)&255])*self.arg(2));self.ret(self.arg(0))
        else:raise AssertionError('未声明边界 '+name)

def run():
    OUT.mkdir(parents=True,exist_ok=True);source=HERE/'CodeTests/joint_policy_entry.cpp';module=OUT/'policy.so'
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(OUT/'zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(OUT/'zig-local-cache'))
    compiler=CACHE/'toolchain/zig-windows-x86_64-0.13.0/zig.exe'
    obj=OUT/'policy.o'
    subprocess.run([str(compiler),'c++','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-marm','-O2','-std=c++11',
                    '-fPIC','-c',str(source),'-o',str(obj)],cwd=ROOT,env=env,check=True)
    subprocess.run([str(compiler),'cc','-target','arm-linux-gnueabihf.2.22','-mcpu=cortex_a9','-shared','-nostdlib',
                    str(obj),str(BASELINE/'lib/libc-2.22.so'),'-o',str(module)],cwd=ROOT,env=env,check=True)
    elf=ArmElf(module.read_bytes());checks=[]
    for case in ('valid','released','release-unreadable','directory-symlink','deadline-changed','wrong-pid','stale','future','extra-field','public-file','hardlink','short-read'):
        m=Machine(elf,case);result=m.call('joint_policy_case',[],budget=100000)
        assert result==int(case=='valid'),(case,result)
        assert not m.fd,(case,m.fd)
        checks.append(case)
    m=Machine(elf,'valid')
    for a,b,c,expected in [(8192,1,1,1),(4096,1,1,0),(8192,0,1,0),(8192,1,0,0)]:
        assert m.call('joint_gpu_case',[a,b,c],budget=100000)==expected;checks.append(f'gpu-{a}-{b}-{c}')
    sources=[Path(__file__),source,HERE/'joint/joint_policy.h',HERE/'CodeTests/arm_machine.py']
    sources.extend(ROOT/p for p in ('x1d/combined-runtime/native/install_window.h','x1d/wireless-flash/native/formal_install_hold.h','x1d/wireless-flash/native/rf_local_socket.h','x1d/wireless-flash/native/rf_bridge.h'))
    report={'passed':True,'checks':checks,'armInstructionsExecuted':True,'cameraAccess':False,'realFilesOrClockUsed':False,
            'modeledBoundaries':['read-only files','ARM stat64 metadata','clock/getpid','sscanf'],
            'sourceHashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'armJointPolicyChecks':len(checks),'cameraAccess':False}))

if __name__=='__main__':run()
