"""固定 X1D II 1.5.2 离线对照；不执行包内程序、不访问相机。"""
from pathlib import Path
import ast,hashlib,importlib.util,json,re,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'build/x1d-ii-reference'
SOURCE=OUT/'X1D_II_50C_v1_5_2.cim'
EXPECTED_SHA='1bb69d26627d3af69dec75fd78653cd9769bd205f54ee4d6b1c5beae87b98cda'
spec=importlib.util.spec_from_file_location('baseline_constants',ROOT/'x1d/tools/prepare_baseline.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
from Crypto.Cipher import AES

def run():
 if Path.cwd().resolve()!=ROOT:raise ValueError('workspace mismatch')
 d=SOURCE.read_bytes()
 if len(d)!=233878016 or mod.sha(d)!=EXPECTED_SHA:raise ValueError('input identity')
 ref=ROOT/'.research-cache/reference-source.txt'
 raw=ref.read_bytes() if ref.exists() else mod.fetch(mod.REFERENCE,65536)
 c=mod.reference_constants(raw)
 stamp=re.search(rb'(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})',d[:128])
 if not stamp or not d.startswith(b'VHABCIM\r\n'):raise ValueError('header')
 y,mo,da,h,mi,se=map(int,stamp.groups())
 iv=hashlib.md5(c['IV_SALT']+bytes([y//100,y%100,mo,da,h,mi,se])+bytes(9)).digest()
 def dec(offset,size):
  if offset<128 or size<=0 or offset+((size+15)//16)*16>len(d):raise ValueError('range')
  out=bytearray()
  for pos in range(0,size,4096):
   n=min(4096,size-pos)
   out.extend(AES.new(c['STATIC_KEY'],AES.MODE_CBC,iv).decrypt(d[offset+pos:offset+pos+((n+15)//16)*16])[:n])
  return bytes(out)
 table=dec(128,0x2000)
 if int.from_bytes(d[60:64],'big')!=3 or int.from_bytes(d[68:72],'big')!=len(d):raise ValueError('container')
 private=hashlib.md5(hashlib.md5(d[0x200:]+c['MAGIC_HASH_SALT']).digest()+table[32:384]).digest()
 if private!=table[16:32]:raise ValueError('private checksum')
 count=int.from_bytes(table[60:64],'big')
 if not 1<=count<=16:raise ValueError('entry count')
 entries=[];payload={}
 for m in re.finditer(rb'\x00{16,}(?P<name>[\x20-\x7e]{3,})\x00',table):
  begin=m.start()-24
  if begin<0:continue
  off,size,digest=struct.unpack_from('>II16s',table,begin)
  name=m.group('name').decode()
  if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',name):continue
  if off<0x200 or off>=len(d):continue
  if name in payload:raise ValueError('duplicate')
  blob=dec(off,size)
  if hashlib.md5(blob+c['MAGIC_HASH_SALT']).digest()!=digest:raise ValueError('entry checksum')
  entries.append({'name':name,'offset':off,'bytes':size,'sha256':mod.sha(blob)})
  payload[name]=blob
 if len(entries)!=count:raise ValueError('entry count mismatch')
 for name,blob in payload.items():
  p=OUT/name
  if p.exists() and p.read_bytes()!=blob:raise ValueError('existing content mismatch')
  if not p.exists():p.write_bytes(blob)
 report={'source_firmware':'official X1D II 1.5.2','sha256':EXPECTED_SHA,'private_checksum_verified':True,'entries':entries,'camera_access':False}
 (OUT/'container-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report))
if __name__=='__main__':run()

