"""运行原厂 ARM 完成/析构控制流。writeFile/freeBuffer/后续队列为显式替身，无真实 D-Bus。"""
from pathlib import Path
import json
from run_stable_provider import StableMachine
from run_provider import sha
from arm_machine import HERE,X1D,UC_HOOK_CODE
from binary import ArmElf

class Factory(StableMachine):
    def __init__(self):
        super().__init__();self.factory=ArmElf.load('usr/bin/jpeg-daemon');e=self.factory
        loads=[p for p in e.elf.iter_segments() if p['p_type']=='PT_LOAD']
        lo=min(p['p_vaddr'] for p in loads)&~4095
        hi=(max(p['p_vaddr']+p['p_memsz'] for p in loads)+4095)&~4095
        self.uc.mem_map(lo,hi-lo)
        for p in loads:self.uc.mem_write(p['p_vaddr'],p.data())
        local={s.name:s['st_value'] for s in e.symbols if s.name and s['st_shndx']!='SHN_UNDEF'}
        for section in e.sections:
            if section['sh_type']!='SHT_REL':continue
            table=e.elf.get_section(section['sh_link'])
            for r in section.iter_relocations():
                symbol=table.get_symbol(r['r_info_sym']);kind=r['r_info_type']
                if kind==20:continue # 未执行的全局 COPY 数据；测试不启动原进程初始化。
                assert kind in (21,22)
                self.put(r['r_offset'],local.get(symbol.name,self.symbols.get(symbol.name,self.stub(symbol.name))))
        self.trace=[];self.returned=0
        self.logging=self.allocate(24,True)
        def logger():self.put(self.arg(0),self.logging);self.ret(self.arg(0))
        self.bind('_ZNK14QMessageLogger5debugEv',logger)
        for name in ('_ZN11QTextStreamlsERK7QString','_ZN11QTextStreamlsEi','_ZN11QTextStreamlsEc',
                     '_ZN6QDebug9putStringEPK5QCharj','_ZN6QDebugD1Ev'):
            self.bind(name,lambda:self.ret(self.arg(0)))
        self.callbacks['_ZN12StorageProxy9writeFileERK10QByteArrayyRK7QString']=self.factory_write
        self.callbacks['_ZN12StorageProxy10freeBufferEiP7QObject']=self.factory_free
        self.uc.hook_add(UC_HOOK_CODE,lambda *a:self.ret(self.logging),begin=0x1768c,end=0x1768c)
        self.uc.hook_add(UC_HOOK_CODE,lambda *a:self.next_call(),begin=0x1a538,end=0x1a538)
    def factory_write(self):
        assert self.arg(2)==self.arg(3)==0
        self.trace.append(['writeFile',self.string(self.arg(4)),self.array(self.arg(1)).decode('ascii')])
        self.ret(self.returned)
    def factory_free(self):
        assert self.arg(1)==77 and self.arg(2)==0
        self.trace.append(['freeBuffer',77]);self.ret(0)
    def next_call(self):
        assert self.word(self.arg(0)+0x10)==0
        self.trace.append(['nextCall']);self.ret()

def run():
    m=Factory();cases=[]
    for returned in (0,0x12345678):
        for buffered in (False,True):
            m.trace=[];m.returned=returned
            call=m.allocate(32,True);m.put(call,0x3a094)
            name=m.qstring('/artificial/factory.3FR');m.put(call+8,m.word(name));m.free(name)
            m.put(call+16,m.symbols['_ZN10QArrayData11shared_nullE'])
            buffer=m.allocate(8,True);m.put(buffer+4,77);m.put(call+24,buffer if buffered else 0)
            m.put(call+28,1)
            encoder=m.allocate(32,True);m.put(encoder+16,call)
            encoded=m.byte_array(b'encoded-fixture')
            m.call(0x1ae18,[encoder,encoded])
            expected=[['writeFile','/artificial/factory.JPG','encoded-fixture']]
            if buffered:expected.append(['freeBuffer',77])
            expected.append(['nextCall'])
            assert m.trace==expected and call not in m.live and m.word(encoder+16)==0,m.trace
            assert m.word(m.word(encoded))==1
            m.free(m.word(encoded));m.free(encoded);m.free(buffer);m.free(encoder)
            cases.append({'writeReturn':returned,'bufferPresent':buffered,'trace':m.trace,'callDeleted':True})
    report={'passed':True,'cameraAccess':False,'cases':cases,'firmwareSource':'X1D-50c 1.25.0',
      'factorySha256':sha(m.factory.data),'realArm':['Encoder::onEncodeFinished','ConvertCall::complete','ConvertCall deleting destructor','Qt QString and QByteArray'],
      'replaced':['logging','writeFile return (opaque null or non-null)','freeBuffer asynchronous request','next queue processing','initial object construction','libc'],
      'notValidated':['actual error watcher construction or event loop','buffer acknowledgement','capture pipeline or original busy LED cause'],
      'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_stable_provider.py',HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py']}}
    out=HERE/'artifacts/diagnosis';out.mkdir(parents=True,exist_ok=True)
    (out/'completion-execution.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'factoryCompletionCases':len(cases),'cameraAccess':False,'realDBus':False}))
if __name__=='__main__':run()
