from pathlib import Path
import sys,io,struct
P=Path(__file__).resolve().parent;O=P/'build/hub-boot';ROOT=P.parents[3]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
sy={s.name:s['st_value'] for s in ELFFile(io.BytesIO((O/'staged_adapter.elf').read_bytes())).get_section_by_name('.symtab').iter_symbols()}
blob=(O/'staged_adapter.bin').read_bytes();size=len(blob)
old=(P/'build/minimal-boot/early_data.h').read_text(encoding='utf-8');deps=old[old.index('static const uint32_t earlyDependencies'):]
(O/'early_data.h').write_text('#pragma once\nstatic const uint32_t earlyImage[]={'+','.join(hex(x)+'u' for x in struct.unpack('<'+'I'*(size//4),blob))+'};\n'+''.join('static const uint32_t '+n+'='+str(sy[k]-0x2b2880)+'u;\n' for n,k in [('earlyContextOffset','hbl_batch_adapter'),('earlyDecodeOffset','hbl_batch_decode'),('earlyDispatchOffset','hbl_batch_read_dispatch')])+deps,encoding='utf-8')
b=lambda a,t:0xeb000000|(((t-a-8)//4)&0xffffff)
replacements=[(0x2b2880+1672+12,sy['hbl_batch_adapter']+12),(0x2b2880+1672+32,sy['hbl_batch_adapter']+32),(b(0x23acac,0x2b2880+48),b(0x23acac,sy['hbl_batch_decode'])),(b(0x1e2224,0x2b2880+572),b(0x1e2224,sy['hbl_batch_read_dispatch']))]
s=(P/'native/af_merged_init.c').read_text(encoding='utf-8').replace('build/merged-boot/','build/hub-boot/')
for a,b in replacements:s=s.replace(hex(a),hex(b))
(P/'native/af_hub_init.c').write_text(s,encoding='utf-8')
s=(P/'CodeTests/merged_init_arm_check.py').read_text(encoding='utf-8').replace('build/merged-boot','build/hub-boot')
for a,b in replacements:s=s.replace(str(a),str(b))
(P/'CodeTests/hub_init_arm_check.py').write_text(s,encoding='utf-8')