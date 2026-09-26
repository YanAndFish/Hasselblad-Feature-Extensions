"""固定归档、命令长度、阶段唯一发送、失败不重发；USB/时钟均为替身。"""
import hashlib,io,json,sys,tarfile,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import bus_package as package
import stage,main

def run():
    report=package.read(HERE/'build/package/package.json')
    data=(HERE/'build/package/af-bus-r3.tar.gz').read_bytes()
    assert hashlib.sha256(data).hexdigest()==report['packageSha256']
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        assert len(archive.getmembers())==8
        for member in archive.getmembers():
            assert member.isfile() and member.name in report['files']
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest()==report['files'][member.name]
            assert member.mode==(0o700 if member.name.endswith('.sh') or member.name=='bus-local-check' else 0o600)
    package.verify=lambda:(report,data)
    stage.time.sleep=lambda _:None
    out=HERE/'test-build/entry';out.mkdir(parents=True,exist_ok=True)
    # main 对真实 stage 目录的限定保留；仅本用例的证据工作副本暂用同一类型目录。
    sessions=HERE/'build/sessions';sessions.mkdir(parents=True,exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory(dir=sessions,prefix='offline-entry-') as temp:
        folder=Path(temp);calls=[];created=[];mode='apply';phase='success'
        class Session:
            def __init__(self,name):
                self.directory=folder/str(len(created));self.directory.mkdir();created.append(self);self.commands=[]
            def command(self,label,command,timeout_ms=15000):
                assert len(command.encode('ascii'))<=231 and '\n' not in command and '\0' not in command
                calls.append((label,command));self.commands.append((label,command))
                value=''
                if label=='original-services':value='active\nactive'
                elif label=='helper-hash':
                    import shlex
                    helper=''.join(shlex.split(c)[2] for l,c in calls if l.startswith('decode.sh-'))
                    value=hashlib.sha256(helper.encode()).hexdigest()+' x'
                elif label.startswith('decode-observe-'):value='0\n'+report['packageSha256']+' x'
                elif label=='extract-once':value='af-bus-r3-package-verified'
                elif label=='same-bus-package':value=report['files']['manifest.sha256']+' x'
                elif label.endswith('-observe'):
                    value=('0\n'+('af-bus-r3-ready' if mode=='apply' else 'af-bus-r3-previous-bus-restored')) if phase=='success' else ('pending' if phase=='unknown' else '66\nfailed')
                return {'output':value,'closed':True,'exit_code':0}
            def summary(self):return {'allHandlesClosed':True,'failed':False,'requests':0,'mockedCommands':len(self.commands)}
        stage.transfer.Session=Session
        evidence=stage.stage();assert package.read(evidence)['staged']
        import base64,shlex
        encoded=''.join(shlex.split(c)[2] for l,c in calls if l.startswith('chunk-'))
        assert base64.b64decode(encoded)==data
        checks.append('archive, executable permissions, transfer bytes, every command within 231 bytes')
        for mode,phase in [('apply','success'),('restore','success'),('apply','failure'),('apply','unknown')]:
            if phase=='success':assert main.action(mode,evidence)['completed']
            else:
                try:main.action(mode,evidence)
                except RuntimeError:pass
                else:raise AssertionError('failure accepted')
            commands=created[-1].commands
            assert sum(l==mode+'-once' for l,_ in commands)==1
            checks.append(mode+' '+phase+' has exactly one dispatch')
        state=package.read(evidence);state['allHandlesClosed']=False
        evidence.write_text(json.dumps(state),encoding='utf-8');count=len(created)
        try:main.action('apply',evidence)
        except ValueError:pass
        else:raise AssertionError('unclosed stage accepted')
        assert len(created)==count;checks.append('incomplete stage rejected before session')
    result={'passed':True,'checks':checks,'hardwareRequests':0,'usbAndSleepMocked':True}
    (HERE/'entry-tests.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':run()
