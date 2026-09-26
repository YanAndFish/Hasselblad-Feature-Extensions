"""固定官方1.25.0 FARM中CF回复枚举证据；只读离线输入，没有设备访问。"""
import sys,json
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'x1d/tools'))
from farm_diagnostic_binary import FarmApplication

def main():
    f=FarmApplication()
    assert f.sha256=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
    assert f.read(0x1a0ecc,20)==bytes.fromhex('60311be50430d3e5080053e303f19f97700200ea')
    rows=[]
    for status,entry,load,address,label in (
        (0,0x1a0f04,0x1a0f58,0x247534,'Reached'),
        (1,0x1a1578,0x1a15cc,0x247680,'Near Limit'),
        (2,0x1a163c,0x1a1690,0x2476a0,'Far Limit'),
        (3,0x1a1700,0x1a1754,0x2476bc,'Jammed')):
        assert f.word(0x1a0ee0+status*4)==entry
        text=f.read(address,80).split(b'\0')[0].decode('ascii')
        assert text=='%sPosition resp = '+label
        ins=f.instructions(load,8)
        assert [(i.mnemonic,i.op_str) for i in ins]==[
            ('movw',f'r2, #{hex(address&65535)}'),('movt','r2, #0x24')]
        rows.append({'status':status,'meaning':label,'branch':hex(entry),'messageAddress':hex(address),
                     'message':text,'addressLoad':f.disassembly(load,8)})
    result={'firmware':'X1D 1.25.0 FARM','sha256':f.sha256,'hardwareRequests':0,
        'handler':'0x1a0ebc','statusByteOffset':4,'cases':rows,
        'limitation':'固定原厂二进制的枚举映射；不测量镜头物理端点或推定其他状态含义'}
    out=HERE/'build/native-cf-limits.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
