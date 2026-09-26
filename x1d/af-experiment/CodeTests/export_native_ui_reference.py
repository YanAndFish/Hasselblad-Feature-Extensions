"""从实际 ARM 核心生成浏览器 ABI 对照；依赖 test_native_af 的固定版本校验。"""
import hashlib,json
from test_native_af import Case,Timing,samples,BUILD,HERE,M

def fields(value):
    return {name:getattr(value,name) for name,_ in value._fields_}

def main():
    c=Case();cases=[]
    rows=[('curve',samples(),Timing(144,2,2,1,.2)),
          ('inflight',samples(),Timing(144,2,20,1,.2,1,8,9)),
          ('reversed',samples(tuple(-20*i for i in range(5)),curve=lambda p:20000-(p+120)**2),Timing(144,2,2,1,.2)),
          ('uncalibrated',samples(),Timing(144,2,2,0,0))]
    for name,ss,t in rows:
        cases.append(dict(name=name,samples=[fields(s) for s in ss],timing=fields(t),result=fields(c.core(ss,t))))
    out=dict(payloadSha256=M['payload_sha256'],sourceSha256=M['source_sha256'],
             generatorSha256=hashlib.sha256((HERE/'CodeTests/export_native_ui_reference.py').read_bytes()).hexdigest(),cases=cases)
    (BUILD/'arm-ui-reference.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print('ARM reference:',len(cases),'cases')

if __name__=='__main__':main()
