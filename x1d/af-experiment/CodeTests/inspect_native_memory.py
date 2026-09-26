"""固定 FARM 的布局与原生分配器证据；不访问相机，不分配实机地址。"""
import hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
FARM=FarmApplication()
assert FARM.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
BUILD=HERE/'build/native-memory-study'
REGIONS=[('startup_clear',0x10a174,0x10a1f8),('native_allocate',0x184a60,0x184d0c),
         ('native_free',0x184d0c,0x184e2c),('heap_initialize',0x184e2c,0x184f90),
         ('heap_insert',0x184f90,0x1850e4),('suspend_scheduler',0x188370,0x1883a0),
         ('resume_scheduler',0x188424,0x188624)]
def main():
    BUILD.mkdir(parents=True,exist_ok=True)
    sections=[]
    for name,start,end in REGIONS:
        sections.append({'name':name,'start':start,'endExclusive':end,
                         'sha256':hashlib.sha256(FARM.read(start,end-start)).hexdigest()})
    mmu=[{'base':section<<20,'imageDescriptor':FARM.word(0x2b4000+4*section),
          'sectionDescriptor':FARM.word(0x2b4000+4*section)&3==2,
          'executeNever':bool(FARM.word(0x2b4000+4*section)&16)} for section in range(2,7)]
    report={'kind':'offline-native-memory-evidence','baselineSha256':FARM.sha256,'hardwareRequests':0,
        'actualAllocationPerformed':False,'allocatedCameraRange':None,
        'fixedImage':{'base':FARM.base,'endExclusive':FARM.base+len(FARM.data)},
        'startupClearLiterals':{hex(a):hex(FARM.word(a)) for a in range(0x10a180,0x10a194,4)},
        'largeZeroRunsInImageNotFreeProof':[{'start':FARM.base+m.start(),'endExclusive':FARM.base+m.end()}
             for m in re.finditer(b'\x00{1024,}',FARM.data)],
        'sharedFlashRangeExcluded':[0x2b26a0,0x2b4000],
        'allocator':{'entry':0x184a60,'freeEntry':0x184d0c,'initEntry':0x184e2c,
            'backingStart':0x2baca8,'backingEndExclusive':0x6baca8,'backingBytes':0x400000,
            'blockHeaderBytes':8,'allocationAlignment':8,'allocatedBit':0x80000000,
            'freeListHead':0x6baca8,'endSentinelPointer':0x6bacb0,'freeBytes':0x6bacb4,
            'minimumEverFreeBytes':0x6bacb8,'allocatedBitGlobal':0x6bacbc,
            'schedulerSuspend':0x188370,'schedulerResume':0x188424,'allocationFailureHook':0x2209ac},
        'mappingInFactoryImageNotLive':mmu,'regions':sections,
        'limitations':['堆区已经由原厂分配器管理，不能选择一段直接覆盖',
            '仅可研究在任务上下文申请独立块；不得从 SGI/IRQ 调用会操作调度器的分配器',
            '当前堆状态、映射和最大连续空闲块未知；尚未发生实际申请',
            '需要一次性申请、边界/缓存核对、存续期管理、失败处理和完整装载事务'],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (BUILD/'memory-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BUILD/'memory-evidence.asm').write_text('\n\n'.join('; '+name+'\n'+FARM.disassembly(a,b-a)
                              for name,a,b in REGIONS)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('allocator','mappingInFactoryImageNotLive','startupClearLiterals')},ensure_ascii=False))
if __name__=='__main__':main()
