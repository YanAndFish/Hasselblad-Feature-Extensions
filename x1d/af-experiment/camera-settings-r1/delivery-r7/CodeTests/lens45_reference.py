"""Offline fixed official XCD45P 0.1.36 input; no camera interface."""
import sys,re,hashlib,urllib.request
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path.cwd().resolve()
sys.path[:0]=[str(ROOT/"x1d/tools"),str(ROOT/".research-cache/x1d-1.25.0/python")]
from prepare_baseline import reference_constants,fetch,REFERENCE
from Crypto.Cipher import AES
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
SHA="4c3d1d00f32e0cb4cb9d849943ed7ae770c734c097773b6baed9d37604838340"
def load():
 cache=Path(__file__).resolve().parent/"output/45p-identity/reference.bin"
 if cache.exists():
  data=cache.read_bytes();assert hashlib.sha256(data).hexdigest()==SHA;return data
 url="https://cdn.hasselblad.com/firmware/XCD_Lenses_Firmware/0.1.36/X-Lens_v0_1_36.cim"
 with urllib.request.urlopen(url,timeout=45) as r:fw=r.read(408577)
 assert len(fw)==408576 and hashlib.sha256(fw).hexdigest()=="0031eeffae59cffdfcd6645acbda6326f93cbbaf7916b258ed7e89e7e43ef275"
 c=reference_constants(fetch(REFERENCE,65536))
 y,m,d,h,mi,s=map(int,re.search(rb"(\d{4})-(\d{2})-(\d{2})\r\n(\d{2}):(\d{2}):(\d{2})",fw[:128]).groups())
 iv=hashlib.md5(c["IV_SALT"]+bytes([y//100,y%100,m,d,h,mi,s])+bytes(9)).digest()
 def dec(off,n):
  return b"".join(AES.new(c["STATIC_KEY"],AES.MODE_CBC,iv).decrypt(fw[off+k:off+k+((min(4096,n-k)+15)//16)*16])[:min(4096,n-k)] for k in range(0,n,4096))
 table=dec(0x80,0x380);raw=dec(0x400,396220)
 assert hashlib.sha256(raw).hexdigest()=="ecc20185c12dd8e343c9dab334e7f82aab4ef8d2c043ed1aa0de53c4019123fa"
 assert hashlib.md5(raw+c["MAGIC_HASH_SALT"]).digest()==table[0x1ac:0x1bc]
 memory={};base=0
 for line in raw.splitlines():
  if not line:continue
  assert line[:1]==b":";v=bytes.fromhex(line[1:].decode());assert sum(v)%256==0 and len(v)==v[0]+5
  addr=int.from_bytes(v[1:3],"big");kind=v[3];body=v[4:-1]
  if kind==4:base=int.from_bytes(body,"big")<<16
  elif kind==0:
   for j,value in enumerate(body):
    a=base+addr+j;assert a not in memory;memory[a]=value
  elif kind in (1,5):pass
  else:raise ValueError(kind)
 assert min(memory)==0x8000 and max(memory)==0x2a62f and len(memory)==0x22630
 data=bytes(memory[a] for a in range(0x8000,0x2a630));assert hashlib.sha256(data).hexdigest()==SHA
 cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(data);return data
def dis(a,n):
 data=load();cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
 return "\n".join(f"{i.address:08x} {i.mnemonic:8} {i.op_str}" for i in cs.disasm(data[a-0x8000:a-0x8000+n],a))
if __name__=="__main__":print(dis(0x1f000,0x140))
