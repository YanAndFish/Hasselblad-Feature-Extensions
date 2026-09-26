"""保守枚举旧AF覆盖区的直接分支、整字指针与MOVW/MOVT引用；不自动宣告可安装。"""
import sys,struct,json
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'x1d/tools'),str(ROOT/'.research-cache/x1d-1.25.0/python')]
from farm_diagnostic_binary import FarmApplication
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
RANGES=((0x19bfb8,0x19c310),(0x19c314,0x19c8ec),(0x19c8f0,0x19cc20),(0x19cc24,0x19cf5c),
        (0x19d1a0,0x19d5c8),(0x19d5cc,0x19d87c),(0x19d880,0x19d9cc),(0x19d9d0,0x19dd70))
def inside(a):return next((i+1 for i,(lo,hi) in enumerate(RANGES) if lo-4<=a<hi),None)
def classify(a):
    if inside(a):return 'covered'
    if 0x19bb94<=a<0x19d19c:return 'native_dispatch_or_cleanup'
    return 'external_candidate'
def main():
    farm=FarmApplication();rows=[];raw=farm.data;base=farm.base
    for off in range(0,len(raw)-4,4):
        a=base+off;w=struct.unpack_from('<I',raw,off)[0]
        if inside(w&~1):rows.append({'kind':'word_pointer','site':a,'target':w,'sourceClass':classify(a)})
        if w>>28!=15 and ((w>>25)&7)==5:
            d=(w&0xffffff)<<2
            if d&(1<<25):d-=1<<26
            target=a+8+d
            if inside(target):rows.append({'kind':'arm_branch','site':a,'target':target,'sourceClass':classify(a)})
        if w&0x0ff00000==0x03000000:
            reg=(w>>12)&15;low=((w>>4)&0xf000)|(w&0xfff)
            for ahead in range(4,36,4):
                if off+ahead+4>len(raw):break
                other=struct.unpack_from('<I',raw,off+ahead)[0]
                if other&0x0ff0f000==0x03400000|(reg<<12):
                    high=((other>>4)&0xf000)|(other&0xfff);target=(high<<16)|low
                    if inside(target&~1):rows.append({'kind':'arm_mov_pair','site':a,'secondSite':a+ahead,
                        'target':target,'sourceClass':classify(a)})
                    break
    # 每个半字起点保守检查Thumb32分支与MOVW/MOVT；包含ARM字节的误解码候选。
    decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    for off in range(0,len(raw)-4,2):
        a=base+off;h=struct.unpack_from('<H',raw,off)[0]
        if h&0xf800!=0xf000:continue
        ins=next(decoder.disasm(raw[off:off+4],a),None)
        if ins and ins.size==4 and ins.mnemonic.startswith('b') and ins.op_str.startswith('#0x'):
            target=int(ins.op_str[1:],16)
            if inside(target&~1):rows.append({'kind':'thumb_decode_candidate','site':a,'target':target,
                'mnemonic':ins.mnemonic,'sourceClass':classify(a)})
        if ins and ins.size==4 and ins.mnemonic=='movw':
            reg,low=ins.op_str.split(', ');low=int(low[1:],0)
            for ahead in range(4,36,2):
                other=next(decoder.disasm(raw[off+ahead:off+ahead+4],a+ahead),None)
                if not other or other.mnemonic!='movt':continue
                otherreg,high=other.op_str.split(', ')
                if otherreg!=reg:continue
                target=(int(high[1:],0)<<16)|low
                if inside(target&~1):rows.append({'kind':'thumb_mov_pair','site':a,'secondSite':a+ahead,
                    'target':target,'sourceClass':classify(a)})
                break
    # 已核对的Thumb连续指令：ARM误解码候选0x160b50位于两条Thumb指令之间。
    thumb_context=list(decoder.disasm(farm.read(0x160b46,0x20),0x160b46))
    thumb_evidence=[dict(site=i.address,bytes=i.bytes.hex(),mnemonic=i.mnemonic,operands=i.op_str)
                    for i in thumb_context]
    out=ROOT/'x1d/af-experiment/build/full-r3/overlay-references.json'
    result={'farmSha256':farm.sha256,'ranges':RANGES,'includePrecedingGuardWord':True,
        'references':rows,'thumb160b50Context':thumb_evidence,'layoutReviewed':False,
        'limitations':['原始字节的保守候选，不证明每一条都属于可执行代码',
            'MOV组合不证明寄存器中途未被改写；尚未覆盖计算跳转和已保存栈返回地址',
            '任何安装仍须冷启动后新预检与完整守卫测试，不能热覆盖旧活动栈']}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([r for r in rows if r['sourceClass']!='covered'],indent=2))
if __name__=='__main__':main()
