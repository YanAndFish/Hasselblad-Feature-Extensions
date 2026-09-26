"""独立 AF 包逐帧传输模型与真实 shell 解码器回读，不访问相机。"""
from pathlib import Path
import hashlib,json,shlex,subprocess,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import session
ROOT=session.ROOT
def run():
    report,data=session.package.verify()
    output=HERE/'CodeTests/output/transfer';output.mkdir(parents=True,exist_ok=True)
    original=session.transfer.Session
    class Model:
        def __init__(self,name):self.directory=output;self.failed=False;self.dispatched=set();self.calls=[];self.texts={}
        def command(self,label,command,timeout_ms=15000):
            assert 0<len(command.encode('ascii'))<=231 and '\n' not in command and '\0' not in command,(label,len(command))
            self.calls.append(label)
            if label.startswith(('d.awk-','decode.sh-','chunk-')):
                name='d.awk' if label.startswith('d.awk-') else 'decode.sh' if label.startswith('decode.sh-') else 'p64'
                self.texts[name]=self.texts.get(name,'')+shlex.split(command)[2]
            if label=='original-services':out='active\nactive'
            elif label=='helper-hash':out=hashlib.sha256(self.texts['decode.sh'].encode()).hexdigest()+'  helper'
            elif label.startswith('decode-observe'):out='0\n'+report['packageSha256']+'  archive'
            elif label=='extract-once':out='af-only-package-verified'
            elif label.endswith('-observe'):out='0\n'+session.MARKERS[label[:-8]]
            else:out=''
            return {'output':out,'closed':True}
        def summary(self):return {'requests':len(self.calls),'allHandlesClosed':True,'failed':self.failed,'dispatched':sorted(self.dispatched)}
    models=[]
    def create(name):m=Model(name);models.append(m);return m
    session.transfer.Session=create;session.time.sleep=lambda _:None
    try:session.stage()
    finally:session.transfer.Session=original
    model=models[0]
    for name,text in model.texts.items():(output/name).write_text(text,encoding='ascii',newline='\n')
    shell=Path('C:/Program Files/Git/bin/sh.exe')
    subprocess.run([str(shell),'-n',str(output/'decode.sh')],check=True)
    # 与实机相同的 classic od 分行解码，避免旧大行 awk 延迟。
    cmd='printf \'%b\' "$(od -v -c p64 | sed \'s/^[0-7]* *//\' | awk -f d.awk)" > roundtrip.tar.gz'
    subprocess.run([str(shell),'-c',cmd],cwd=output,check=True,timeout=30)
    assert (output/'roundtrip.tar.gz').read_bytes()==data
    for name in session.MARKERS:session.phase(model,name)
    proof={'passed':True,'boundedCommands':len(model.calls),'decoderRoundtrip':True,'packageSha256':report['packageSha256'],
           'sourceSha256':hashlib.sha256((HERE/'session.py').read_bytes()).hexdigest(),'hardwareRequests':0}
    (HERE/'CodeTests/output/transfer.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))
if __name__=='__main__':run()
