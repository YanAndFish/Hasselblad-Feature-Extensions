"""固定 ARM JSON 记录验证；原子文件提交仍需目标联调。"""
import json
from pathlib import Path
from run_stable_provider import StableMachine
from run_provider import sha
from arm_machine import HERE,X1D

def run():
    m=StableMachine();checks=[]
    good={'version':4,'closed':True,'jpegPath':'/card0/folder/a.jpg','rawPath':'/card0/folder/a.3FR','bytes':1000,'prefixBytes':100,
      'uidHash':'1'*64,'prefixHash':'2'*64,'jpegHash':'3'*64}
    def valid(value):
        obj=m.json_object(value);result=m.call('_ZN3X1D11recordValidERK11QJsonObject',[obj]);m.call('_ZN11QJsonObjectD1Ev',[obj]);m.free(obj);return bool(result)
    assert valid(good);checks.append('v4-complete-does-not-require-raw-hash')
    assert valid(dict(good,version=3,rawHash='4'*64)) and not valid(dict(good,version=3));checks.append('v3-retains-format-check-without-raw-file-read')
    for override in [{'jpegPath':'/card0/folder/a.3FR'},{'jpegPath':'/card0/../a.jpg'},{'jpegHash':'g'*64},{'bytes':0},{'prefixBytes':1001},{'closed':False}]:assert not valid(dict(good,**override)),override
    checks.append('invalid-path-hash-bounds-and-unclosed-record-refused')
    pending={'version':4,'pending':True,'rawPath':'/card0/folder/a.3FR','generation':'123-987-1'}
    assert valid(pending)
    for override in [{'generation':''},{'generation':'x'*129},{'rawPath':'/card0/folder/a.jpg'}]:assert not valid(dict(pending,**override))
    checks.append('pending-record-requires-raw-path-and-bounded-generation')
    source=m.qstring('/card0/folder/a.3FR')
    for path in ['/card1/folder/a.jpg','/card0/folder/a.3FR','/card0/folder/b.jpg']:
        obj=m.json_object(dict(good,jpegPath=path));assert not m.call('_ZN3X1D10sameSourceERK7QStringRK11QJsonObject',[source,obj]);m.call('_ZN11QJsonObjectD1Ev',[obj]);m.free(obj)
    m.drop_string(source);checks.append('provider-defense-rejects-cross-card-other-image-and-raw-as-jpeg')
    report={'passed':True,'checks':checks,'cameraAccess':False,'filePersistenceExecuted':False,'moduleHashes':m.module_hashes,
      'sourceHashes':{p.relative_to(X1D.parent).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_stable_provider.py',HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py',HERE/'native/replay_runtime.cpp']}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'records.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'checks':len(checks)}))

if __name__=='__main__':run()
