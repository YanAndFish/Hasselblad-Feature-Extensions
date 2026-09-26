"""从使用者显式提供的固定无线输入生成本地表；不下载、连接设备或分发输入。"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import uuid
from build_contract import PREPARED_SHA256, TABLE_SHA256, atomic_write, write_report

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'x1d/wireless-flash/research'))
from build_manual_power import wave_hash

EXPECTED = PREPARED_SHA256

def generate(prepared_image, output):
    output.mkdir(parents=True,exist_ok=True)
    run_id = str(uuid.uuid4())
    write_report(output/'radio-tables.json', {'passed':False,'runId':run_id,'deviceAccess':False})
    data = prepared_image.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise ValueError('Unsupported prepared input: SHA-256 does not match the supported baseline')
    base = 0x180000
    runs = [struct.unpack_from('<HHI', data, 0x215c00-base+8*i) for i in range(96)]
    if any(n != 160+(i in (0,25,51,76)) or reserved or step not in (261686886,275105382)
           for i,(n,reserved,step) in enumerate(runs)):
        raise ValueError('Input modulation layout mismatch')
    lut = struct.unpack_from('<1024I', data, 0x214c00-base)
    if wave_hash(runs, lut) != 0x0e77be41:
        raise ValueError('Input waveform verification failed')
    prefix = b'\xaa'*4+(0xc368//6).to_bytes(2,'big')*2
    hashes = []
    for index in range(1345):
        if index == 1344: tail = bytes((0xa9,0x50,0xb4,9))
        elif index >= 1312:
            group,on = divmod(index-1312,2)
            tail = bytes((0xa9,0x0a+group if group<6 else group-6,0xd3,on))
        else:
            group,value = divmod(index,82)
            tail = bytes((0xa9,0x0a+group if group<6 else group-6,0xbc,255 if value==81 else value))
        frame = prefix+tail
        encoded = [(n,0,261686886 if frame[i//8] & (1 << (7-i%8)) else 275105382)
                   for i,(n,_,_) in enumerate(runs)]
        hashes.append(wave_hash(encoded,lut))
    if not all(hashes): raise ValueError('Unexpected zero hash')
    output.mkdir(parents=True,exist_ok=True)
    def header(name,values):
        symbol = 'hbl_formal_'+name
        guard = 'HBL_FORMAL_'+name.upper()+'_H'
        text = '#ifndef '+guard+'\n#define '+guard+'\n#include <stdint.h>\n'
        text += 'static const uint32_t '+symbol+'['+str(len(values))+']={\n'
        text += ',\n'.join('    '+','.join('0x%08xu'%x for x in values[i:i+8]) for i in range(0,len(values),8))
        text += '\n};\n#endif\n'
        path = output/('formal_flash_'+name+'.h')
        payload = text.encode('ascii')
        if hashlib.sha256(payload).hexdigest() != TABLE_SHA256[path.name]:
            raise ValueError('Generated table differs from the supported baseline: '+path.name)
        atomic_write(path, payload)
        return path.name,hashlib.sha256(path.read_bytes()).hexdigest()
    files = dict([header('hashes',hashes),header('lut',lut)])
    report = {'passed':True,'runId':run_id,'inputSha256':digest,'files':files,'waveCount':len(hashes),
              'deviceAccess':False,'redistributionApproved':False}
    write_report(output/'radio-tables.json',report)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=generate(args.prepared_image,args.output)
    print('Generated',report['waveCount'],'local verification entries; input and output are not public assets')

if __name__=='__main__':main()
