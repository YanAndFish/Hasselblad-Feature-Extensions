"""生成早期接收器生命周期离线候选；不访问相机，不接入稳定构建。"""
from pathlib import Path
import sys,io,struct,hashlib
P=Path(__file__).resolve().parent;ROOT=P.parents[3];assert Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT/'.research-cache/x1d-1.25.0/python'))
from elftools.elf.elffile import ELFFile
out=P/'build/controller-first';blob=(out/'staged_adapter.bin').read_bytes()
e=ELFFile(io.BytesIO((out/'staged_adapter.elf').read_bytes()))
sy={s.name:s['st_value']-0x2b2880 for s in e.get_section_by_name('.symtab').iter_symbols()}
firmware=(P/'build/fast-start-research/farm-1.25.0.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest()=='317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca'
ranges=[(0x100770,0x100930),(0x1009c0,0x1009e0),(0x10a270,0x10a3ac),(0x10acac,0x10acb8),(0x1e0a50,0x1e0b80),(0x1e164c,0x1e1888),(0x1e1e1c,0x1e22cc),(0x238ef8,0x238f3c),(0x23ac64,0x23ae20),(0x23cfa4,0x23d1d0),(0x23d464,0x23d61c),(0x2b2478,0x2b2678),(0x1e80d0,0x1e82e0),(0x236a14,0x236a58),(0x160dac,0x160e08)]
h=['#pragma once','static const uint32_t earlyImage[]={'+','.join('0x%08xu'%w for w in struct.unpack('<%dI'%(len(blob)//4),blob))+'};']
for key,name in [('hbl_batch_adapter','earlyContextOffset'),('hbl_batch_decode','earlyDecodeOffset'),('hbl_batch_read_dispatch','earlyDispatchOffset')]:h.append('static const uint32_t '+name+'='+str(sy[key])+'u;')
h+=['static const uint32_t earlyDependencies[][2]={']
for start,end in ranges:
 for a in range(start,end,4):h.append('{0x%xu,0x%xu},'%(a,struct.unpack_from('<I',firmware,a-0x100000)[0]))
h+=['};'];(out/'early_data.h').write_text('\n'.join(h)+'\n',encoding='utf-8')
s=(P/'native/boot_loader.cpp').read_text(encoding='utf-8').replace('"boot_batch.h"','"../../native/boot_batch.h"').replace('"../build/','"../')
s=s.replace('#include <cstring>','#include <cstring>\n#include "early_data.h"')
s=s.replace('    bool afOnly;','    bool afOnly;\n    bool earlyFixed=false,earlyOriginalVerified=false;')
s=s.replace('return heap+hbl_batch_heap_offset;', 'return earlyFixed?0x2b2880u:heap+hbl_batch_heap_offset;')
s=s.replace('return adapterBase()+hbl_batch_adapter_offset;', 'return adapterBase()+(earlyFixed?earlyContextOffset:hbl_batch_adapter_offset);')
s=s.replace('uint32_t offset=a==wake?hbl_batch_read_dispatch_offset:hbl_batch_decode_offset;', 'uint32_t offset=earlyFixed?(a==wake?earlyDispatchOffset:earlyDecodeOffset):(a==wake?hbl_batch_read_dispatch_offset:hbl_batch_decode_offset);')
s=s.replace('if(a&3 || a==sgir)return false;', 'if(a&3 || a==sgir)return false;\n        if(earlyFixed)for(const auto &row:earlyDependencies)if(a==row[0])return true;')
s=s.replace('(owned && contains(a,adapterBase(),sizeof(adapter)))','((owned || earlyFixed) && contains(a,adapterBase(),sizeof(adapter)))')
s=s.replace('wantsAdapter() && owned', 'wantsAdapter() && (owned || earlyFixed)')
s=s.replace('if(phase==PrepareBatch && contains(a,adapterBase(),sizeof(adapter)))', 'if(earlyFixed && adapterInstalled && phase==PrepareBatch && a==adapterContext()+4)return owned && v==heap;\n            if(earlyFixed && adapterInstalled && phase==PrepareBatch && a==adapterContext()+8)return owned && v==1;\n            if(earlyFixed && phase==RemoveWake && a==wake)return v==adapterBranch(wake);\n            if(phase==PrepareBatch && contains(a,adapterBase(),sizeof(adapter)))')
s=s.replace('while(i<N && n<20) {items[n++]={table[i].address,table[i].value,~0u};++i;}', '''while(i<N && n<20) {
                const uint32_t a=table[i].address,v=table[i].value;++i;
                if(earlyFixed && adapterInstalled && contains(a,adapterBase(),sizeof(adapter))) {
                    if(!earlyOriginalVerified || v)return fail();
                    continue; // 首次零区证明与下方不可变镜像核对共同覆盖。
                }
                items[n++]={a,earlyFixed && adapterInstalled && (a==wake || a==0x23acac)?adapterBranch(a):v,~0u};
            }
            if(!n)continue;''')
s=s.replace('(phase==Allocate || phase==Body || phase==FlashBody)', '(phase==Body || phase==FlashBody)')
s=s.replace('        if(!owned || !batch->batchSession()', '''        if(earlyFixed && adapterInstalled) {
            return owned && step(PrepareBatch,"enable-owned-af-batch") && eq(adapterContext()+12,0) && eq(adapterContext()+32,0) &&
                write(adapterContext()+4,heap) && write(adapterContext()+8,1);
        }
        if((!owned && !earlyFixed) || !batch->batchSession()''')
s=s.replace('!step(PrepareBatch,"prepare-batch-adapter")', '!step(PrepareBatch,earlyFixed?"prepare-early-batch-adapter":"prepare-batch-adapter")')
s=s.replace('std::memcpy(adapter,hbl_batch_image,sizeof(adapter));', 'static_assert(sizeof(earlyImage)==sizeof(adapter),"adapter storage size");\n        std::memcpy(adapter,earlyFixed?earlyImage:hbl_batch_image,sizeof(adapter));\n        if(!earlyFixed) {')
s=s.replace('const unsigned ctx=hbl_batch_adapter_offset/4;', '}\n        const unsigned ctx=(earlyFixed?earlyContextOffset:hbl_batch_adapter_offset)/4;')
s=s.replace('adapter[ctx]=1;adapter[ctx+1]=heap;adapter[ctx+2]=1;', 'adapter[ctx]=1;adapter[ctx+1]=heap;adapter[ctx+2]=earlyFixed?0:1;')
needle='        if(!expected(hbl_boot_expected))return false;'
replacement='''        if(afOnly && wantsAdapter() && batch->earlyBootstrapAllowed()) {
            earlyFixed=true;
            for(const auto &row:earlyDependencies)if(!eq(row[0],row[1]))return false;
            for(const auto &g:hbl_flash_guards)if(!eq(g.address,g.value,g.mask))return false;
            for(uint32_t a=scratch;a<scratch+64;a+=4)if(!eq(a,0))return false;
            for(uint32_t a=adapterBase();a<adapterBase()+sizeof(adapter);a+=4)if(!eq(a,0))return false;
            earlyOriginalVerified=true;
            if(!idle() || !step(Preflight,"early-bootstrap-verified") || !step(Cache,"early-cache-probe") ||
               !probe() || !park() || !prepareAdapter() || !step(Cleanup,"early-cache-cleanup") || !cleanup() ||
               !step(Preflight,"factory-preflight"))return false;
        }
        if(!expected(hbl_boot_expected))return false;
        if(earlyFixed) {
            HblBootCompare chunk[20];size_t n=0;
            for(uint32_t off=0;off<earlyContextOffset;off+=4) {
                chunk[n++]={adapterBase()+off,adapter[off/4],~0u};
                if(n==20){if(!compare(chunk,n))return false;n=0;}
            }
            if(n && !compare(chunk,n))return false;
            if(!eq(adapterContext(),1) || !eq(adapterContext()+4,0) || !eq(adapterContext()+8,0) ||
               !eq(adapterContext()+12,0) || !eq(adapterContext()+24,batch->batchSession()) || !eq(adapterContext()+32,0))return false;
        }'''
assert s.count(needle)==1;s=s.replace(needle,replacement)
s=s.replace('!eq(a,h.original) || !write(a,h.replacement)', '!eq(a,earlyFixed && a==wake?adapterBranch(wake):h.original) || !write(a,h.replacement)')
s=s.replace('!write(wake,h.original)', '!write(wake,earlyFixed?adapterBranch(wake):h.original)')
(out/'early_loader.cpp').write_text(s,encoding='utf-8')
print('candidate generated; dependency closure and lifecycle validation pending')
