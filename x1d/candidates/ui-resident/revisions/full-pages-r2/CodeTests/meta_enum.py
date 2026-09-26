"""从固定 victory-gui 的 QMetaObject 数据直接读取 SystemState 枚举。"""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[4]
BIN=ROOT/'.research-cache/x1d-1.25.0/baseline/usr/bin/victory-gui';EXPECTED_SHA='d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b'
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert sha(BIN)==EXPECTED_SHA
    with BIN.open('rb') as stream:
        elf=ELFFile(stream)
        def offset(address):
            segment=next(v for v in elf.iter_segments() if v['p_vaddr']<=address<v['p_vaddr']+v['p_filesz'])
            return segment['p_offset']+address-segment['p_vaddr']
        symbol=next(v for v in elf.get_section_by_name('.dynsym').iter_symbols() if v.name=='_ZN20SystemManagerProxyUI16staticMetaObjectE')
        stream.seek(offset(symbol['st_value']));words=struct.unpack('<6I',stream.read(24));string_base,meta_base=words[1],words[2]
        stream.seek(offset(meta_base));header=struct.unpack('<14I',stream.read(56));enum_count,enum_offset=header[8],header[9]
        stream.seek(offset(meta_base)+enum_offset*4);definitions=[struct.unpack('<4I',stream.read(16)) for _ in range(enum_count)]
        def string(index):
            entry=string_base+index*16;stream.seek(offset(entry)+4);size=struct.unpack('<I',stream.read(4))[0]
            stream.seek(offset(entry)+12);relative=struct.unpack('<i',stream.read(4))[0]
            stream.seek(offset(entry+relative));return stream.read(size).decode('ascii')
        enums={}
        for name_index,flags,count,data_offset in definitions:
            stream.seek(offset(meta_base)+data_offset*4);pairs=[struct.unpack('<2I',stream.read(8)) for _ in range(count)]
            enums[string(name_index)]={string(key):value for key,value in pairs}
    expected={'StateBoot':0,'StateConfig':1,'StateUp':2,'StateUpgrade':3,'StateStandby':4,'StateShutdown':5,'StatePrepareShutdown':7,'StateFail':6}
    assert enums['SystemState']==expected
    report={'passed':True,'binarySha256':EXPECTED_SHA,'class':'SystemManagerProxyUI','enum':'SystemState','values':expected,
        'method':'ELF dynamic staticMetaObject pointers + Qt5 32-bit moc metadata','hardwareRequests':0,'targetRuntimeRead':False,
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),BIN]}}
    out=HERE/'build/meta-enum-validation.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'values':expected,'hardwareRequests':0}))
if __name__=='__main__':main()
