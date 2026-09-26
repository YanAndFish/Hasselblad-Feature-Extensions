"""执行实际 ARM 控制器 main；libc/进程调用全部为内存替身，零设备及真实服务。"""
from pathlib import Path
import hashlib, io, json, struct, sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]; ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR
BIN=HERE/'build/session/native/replay-control'
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emulate(args, mode='success', uid=0, env=None):
    elf=ELFFile(io.BytesIO(BIN.read_bytes())); u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    segments=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
    lo=min(s['p_vaddr'] for s in segments)&~4095
    hi=(max(s['p_vaddr']+s['p_memsz'] for s in segments)+4095)&~4095
    u.mem_map(lo,hi-lo)
    for s in segments:u.mem_write(s['p_vaddr'],s.data())
    u.mem_map(0x1000000,0x10000);u.mem_map(0x2000000,0x20000)
    hooks={};symtab=elf.get_section_by_name('.dynsym');cursor=0x1000000
    for name in ('.rel.dyn','.rel.plt'):
        for rel in elf.get_section_by_name(name).iter_relocations():
            symbol=symtab.get_symbol(rel['r_info_sym'])
            if symbol.name:
                hooks[cursor]=symbol.name;u.mem_write(rel['r_offset'],struct.pack('<I',cursor));cursor+=4
    end=0x100f000; ptr=0x2001000
    def put(s):
        nonlocal ptr
        p=ptr;b=s.encode()+b'\0';u.mem_write(p,b);ptr+=len(b)+4;return p
    def string(p):
        b=bytearray()
        while p:
            c=u.mem_read(p,1)[0]
            if not c:break
            b.append(c);p+=1
        return b.decode()
    argv=0x2000000
    for i,s in enumerate(['replay-control']+args):u.mem_write(argv+4*i,struct.pack('<I',put(s)))
    u.mem_write(argv+4*(len(args)+1),b'\0'*4)
    env=env or {}; calls=[]; sleeps=[]; kills=[]; waits=0; handlers={};exitcode=None
    def hook(uc,address,size,data):
        nonlocal waits,exitcode
        if address==end:uc.emu_stop();return
        if address not in hooks:return
        name=hooks[address];a=[uc.reg_read(r) for r in REGS];result=0;calls.append(name)
        if name=='strcmp':result=(string(a[0])>string(a[1]))-(string(a[0])<string(a[1]))
        elif name=='getenv':result=put(env[string(a[0])]) if string(a[0]) in env else 0
        elif name=='getuid':result=uid
        elif name=='signal':handlers[a[0]]=a[1]
        elif name=='fork':result=0 if mode.startswith('child') else (-1 if mode=='fork-error' else 1234)
        elif name=='waitpid':
            assert a[0]==1234 and a[2]==1,'wait must be nonblocking and owned'
            waits+=1
            if mode in ('timeout','unreaped','interrupt'):
                result=1234 if mode!='unreaped' and waits>150 else 0
                if mode=='interrupt' and waits==1:
                    # 跳入真实信号处理器，处理完回到调用者。
                    uc.reg_write(UC_ARM_REG_R0,15);uc.reg_write(UC_ARM_REG_PC,handlers[15]);return
            else:
                result=1234
                if a[1]:uc.mem_write(a[1],struct.pack('<I',7<<8 if mode=='exit-seven' else (9 if mode=='signalled' else 0)))
        elif name=='nanosleep':
            sec,ns=struct.unpack('<II',uc.mem_read(a[0],8));assert sec==0 and ns in (100000000,200000000)
            sleeps.append(ns)
        elif name=='kill':kills.append((a[0] if a[0]<2**31 else a[0]-2**32,a[1]))
        elif name=='__errno_location':result=0x201f000
        elif name=='setsid':result=-1 if mode=='child-setsid-error' else 1234
        elif name=='setenv':assert (string(a[0]),string(a[1]),a[2]) in [('PATH','/usr/bin:/bin',1),('LC_ALL','C',1)]
        elif name=='execvp':
            assert string(a[0])=='systemctl'
            assert string(struct.unpack('<I',uc.mem_read(a[1],4))[0])=='systemctl'
            for i,s in enumerate(args,1):assert string(struct.unpack('<I',uc.mem_read(a[1]+4*i,4))[0])==s
            result=-1
        elif name=='_exit':exitcode=a[0];uc.emu_stop();return
        else:raise AssertionError('unexpected libc call '+name)
        uc.reg_write(UC_ARM_REG_R0,result&0xffffffff);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    main=next(s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='main')
    u.reg_write(UC_ARM_REG_R0,len(args)+1);u.reg_write(UC_ARM_REG_R1,argv)
    u.reg_write(UC_ARM_REG_SP,0x201e000);u.reg_write(UC_ARM_REG_LR,end)
    u.emu_start(main,end+4,count=1000000)
    assert exitcode is not None or u.reg_read(UC_ARM_REG_PC)==end,'instruction budget exhausted'
    return exitcode if exitcode is not None else u.reg_read(UC_ARM_REG_R0),calls,sleeps,kills
def run():
    assert Path.cwd().resolve()==ROOT
    checks=[]
    def check(n,v):
        assert v,n
        checks.append(n)
    accepted=[['daemon-reload']]+[[v,'victory-gui'] for v in ('start','stop','restart')]
    roles=('victory-gui','msg2dbus-farm','configstore','jpeg-daemon','storage-daemon')
    accepted += [['is-active','--quiet',r] for r in roles]+[['show','-p',p,r] for r in roles for p in ('MainPID','FragmentPath','DropInPaths','Environment')]
    for a in accepted:check('accept '+' '.join(a),emulate(a)[0]==0)
    for a in ([],['restart','msg2dbus-farm'],['start','jpeg-daemon'],['stop','storage-daemon'],['show','-p','ExecStart','victory-gui'],['daemon-reload','extra'],['reboot']):
        code,calls,_,_=emulate(a);check('reject '+repr(a),code==59 and 'fork' not in calls)
    for kwargs in ({'uid':1000},{'env':{'LD_PRELOAD':'other.so'}},{'env':{'LD_LIBRARY_PATH':'/other'}}):
        code,calls,_,_=emulate(['daemon-reload'],**kwargs);check('environment '+str(kwargs),code==60 and 'fork' not in calls)
    for mode,expected in [('fork-error',61),('exit-seven',7),('signalled',137),('child-exec-error',127),('child-setsid-error',61)]:
        check(mode,emulate(['restart','victory-gui'],mode)[0]==expected)
    for mode,expected in [('timeout',124),('unreaped',124),('interrupt',125)]:
        code,calls,sleeps,kills=emulate(['restart','victory-gui'],mode)
        check(mode,code==expected and kills==[(-1234,15),(1234,15),(-1234,9),(1234,9)] and sum(sleeps)<=16200000000)
    report={'passed':True,'checks':checks,'binarySha256':sha(BIN),'sourceSha256':sha(HERE/'session/native/control.cpp'),'testSha256':sha(Path(__file__)),
            'mode':'actual ARM main with libc process substitutes','hardwareRequests':0,'realServiceCalls':0,'targetValidated':False}
    (HERE/'build/session/control-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks),'hardwareRequests':0}))
if __name__=='__main__':run()
