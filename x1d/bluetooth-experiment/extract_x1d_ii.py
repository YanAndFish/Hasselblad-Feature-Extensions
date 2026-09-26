"""固定第二代 OTA 重建与文件索引，不挂载、不执行。"""
from pathlib import Path
import sys,zipfile,io,json,hashlib,re,stat
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'.research-cache/python'))
from dissect.extfs import ExtFS
OUT=HERE/'build/x1d-ii-reference'
def run():
 if Path.cwd().resolve()!=ROOT:raise ValueError('workspace')
 source=OUT/'ota.zip'
 if hashlib.sha256(source.read_bytes()).hexdigest()!='d761bdaa36bf05e11f40b08545e2a0a29f36023c29dc353a5af127e89bd965d3':raise ValueError('ota identity')
 inventory=[];selected=[]
 with zipfile.ZipFile(source) as z:
  for part,blocks in [('system',65536),('vendor',32768)]:
   lines=z.read(part+'.transfer.list').decode().splitlines()
   if lines[0]!='3' or lines[2:4]!=['0','0']:raise ValueError('transfer version')
   data=z.read(part+'.new.dat');out=bytearray(blocks*4096);pos=0
   for line in lines[4:]:
    op,nums=line.split();v=list(map(int,nums.split(',')))
    if v[0]!=len(v)-1 or v[0]%2 or op not in ['new','zero','erase']:raise ValueError('transfer')
    for a,b in zip(v[1::2],v[2::2]):
     if not 0<=a<b<=blocks:raise ValueError('range')
     if op=='new':
      n=(b-a)*4096
      if pos+n>len(data):raise ValueError('payload short')
      out[a*4096:b*4096]=data[pos:pos+n];pos+=n
   if pos!=len(data):raise ValueError('payload remainder')
   (OUT/(part+'.img')).write_bytes(out)
   fs=ExtFS(io.BytesIO(out))
   def walk(node,path):
    for child in node.iterdir():
     if child.filename in ['.','..']:continue
     name=path+'/'+child.filename
     if child.filetype==stat.S_IFDIR:walk(child,name)
     elif child.filetype==stat.S_IFREG:
      inventory.append({'partition':part,'path':name,'bytes':child.size})
      if re.search(r'(?i)(bluetooth|bt_vendor|bt_stack|\.hcd$|fpga|farm|\.bit$|build.prop$|init.*\.rc$|dji.json$|phocus|camera[-_]system|camera[-_]service|librcam|lib_usb_transfer|msg2dbus|usb_bulk|hbl|firmware)',name):
       if child.size>64*1024*1024:raise ValueError('selected file size')
       d=child.open().read()
       target=OUT/'selected'/part/name.lstrip('/')
       target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(d)
       selected.append({'partition':part,'path':name,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()})
   walk(fs.get('/'),'')
 (OUT/'filesystem-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
 (OUT/'selected-manifest.json').write_text(json.dumps(selected,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'regular_files':len(inventory),'selected':selected}))
if __name__=='__main__':run()

