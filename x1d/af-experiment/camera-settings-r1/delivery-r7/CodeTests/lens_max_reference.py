"""从官方参考包提取镜头参数；只访问公开下载，不访问相机。"""
import sys, re, json, struct, hashlib, urllib.request
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(ROOT / 'x1d/tools'), str(ROOT / '.research-cache/x1d-1.25.0/python')]
from prepare_baseline import reference_constants, fetch, REFERENCE
from Crypto.Cipher import AES
OUT = Path(__file__).resolve().parent / 'output/lens-max-reference'

def get(url):
    with urllib.request.urlopen(url, timeout=40) as response:
        data = response.read(4000001)
    assert len(data) <= 4000000
    return data

def run():
    constants = reference_constants(fetch(REFERENCE, 65536))
    results = []
    for product in (164, 168, 165, 169, 174):
        items = json.loads(get(f'https://api.hasselblad.com/products/downloads/{product}/firmware'))
        item = next(x for x in items if x['url'].endswith('.cim'))
        fw = get(item['url'])
        y,m,d,h,mi,s = map(int,re.search(rb'(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})',fw[:128]).groups())
        iv = hashlib.md5(constants['IV_SALT']+bytes([y//100,y%100,m,d,h,mi,s])+bytes(9)).digest()
        def dec(off,n):
            assert off >= 128 and n > 0 and off+((n+15)//16)*16 <= len(fw)
            return b''.join(AES.new(constants['STATIC_KEY'],AES.MODE_CBC,iv).decrypt(fw[off+k:off+k+((min(4096,n-k)+15)//16)*16])[:min(4096,n-k)] for k in range(0,n,4096))
        # 固定格式的第一个条目数据起点限定目录范围。
        table = dec(128, 0x380)
        matches = list(re.finditer(rb'\x00{16,}(?P<name>[\x20-\x7e]{3,})\x00',table))
        offsets = [struct.unpack_from('>I',table,m.start()-24)[0] for m in matches if m.start() >= 24]
        assert offsets
        table = dec(128, min(offsets)-128)
        entries = []
        folder = OUT / str(product)
        folder.mkdir(parents=True,exist_ok=True)
        for match in re.finditer(rb'\x00{16,}(?P<name>[\x20-\x7e]{3,})\x00',table):
            begin = match.start()-24
            if begin < 0: continue
            name = match.group('name').decode()
            off,n,md = struct.unpack_from('>II16s',table,begin)
            raw = dec(off,n)
            assert hashlib.md5(raw+constants['MAGIC_HASH_SALT']).digest() == md
            if not (name.startswith('LensSpecifics') or name == 'artifact.hex'): continue
            assert Path(name).name == name
            (folder/name).write_bytes(raw)
            entry = {'name':name,'sha256':hashlib.sha256(raw).hexdigest()}
            if name.startswith('LensSpecifics'):
                mem={};base=0
                for line in raw.splitlines():
                    z=bytes.fromhex(line[1:].decode());assert sum(z)%256==0 and len(z)==z[0]+5
                    if z[3]==4:base=int.from_bytes(z[4:-1],'big')<<16
                    elif z[3]==0:
                        for j,v in enumerate(z[4:-1]):
                            a=base+int.from_bytes(z[1:3],'big')+j
                            assert a not in mem;mem[a]=v
                    else: assert z[3] in (1,5)
                b=bytes(mem[a] for a in range(min(mem),max(mem)+1))
                entry.update(base=min(mem),bytes=len(b))
                offset = 0x6c if product == 164 else (0x54 if product in (165,168) else 0x6c4)
                entry.update(parameter_offset=offset,raw_parameter=struct.unpack_from('<I',b,offset)[0])
            entries.append(entry)
        row={'product':product,'version':item['version'],'url':item['url'],'package_sha256':hashlib.sha256(fw).hexdigest(),'entries':entries}
        results.append(row)
        print(json.dumps(row),flush=True)
    (OUT/'parameters.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')

if __name__ == '__main__': run()
