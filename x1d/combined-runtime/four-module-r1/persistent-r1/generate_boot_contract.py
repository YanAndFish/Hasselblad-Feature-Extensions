"""把已核验装载合同展开为机内只读数据，不打开设备。"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def main():
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('workspace')
    source = ROOT / 'x1d/af-experiment/camera-settings-r1/delivery-r7'
    sys.path[:0] = [str(source), str(source.parent)]
    from range_contract import AfOnlyContract
    c = AfOnlyContract(profile='release', nonce=1)
    spec = importlib.util.spec_from_file_location('boot_formal_source', ROOT/'x1d/wireless-flash/research/formal_sync_loader.py')
    flash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flash)
    if not flash.offline_ready():
        raise RuntimeError('flash offline source binding')
    payload = flash.payload()
    out = HERE / 'build/boot-data'
    out.mkdir(parents=True, exist_ok=True)
    lines = ['#pragma once', '#include <stdint.h>',
             'struct HblBootPair { uint32_t address, value; };',
             'struct HblBootGuard { uint32_t address, mask, value; };',
             'struct HblBootHook { uint32_t address, original, replacement; };']
    def scalar(name, value):
        lines.append(f'static const uint32_t {name}=0x{value:08x}u;')
    def pairs(name, values):
        lines.append('static const HblBootPair '+name+'[] = {')
        lines.extend('    {0x%08xu,0x%08xu},' % (a,v) for a,v in sorted(values.items()))
        lines.append('};')
    def blob(name, data):
        lines.append('static const uint32_t '+name+'[] = {')
        values = struct.unpack('<'+'I'*(len(data)//4),data)
        for i in range(0,len(values),8):
            lines.append('    '+','.join('0x%08xu'%v for v in values[i:i+8])+',')
        lines.append('};')
    def guards(name, data):
        lines.append('static const HblBootGuard '+name+'[] = {')
        lines.extend('    {0x%08xu,0x%08xu,0x%08xu},'%(a,m,v) for a,(m,v) in sorted(data.items()))
        lines.append('};')
    def hooks(name, data):
        lines.append('static const HblBootHook '+name+'[] = {')
        lines.extend('    {0x%08xu,0x%08xu,0x%08xu},'%(a,b,n) for a,(b,n) in sorted(data.items()))
        lines.append('};')
    pairs('hbl_boot_expected',c.expected)
    guards('hbl_boot_guards',c.guards)
    blob('hbl_bootstrap_words',c.bootstrap_blob)
    hooks('hbl_bootstrap_hooks',c.bootstrap_hooks)
    scalar('hbl_bootstrap_base',c.bootstrap['base'])
    scalar('hbl_boot_request',c.request)
    scalar('hbl_boot_control',c.control)
    hooks('hbl_flash_hooks',{a:(flash.ORIGINAL_HOOKS[a],v) for a,v in flash.NEW_HOOKS.items()})
    guards('hbl_flash_guards',flash.IRQ_GUARDS)
    pairs('hbl_flash_expected',{a:c.farm.word(a) for a in set(flash.CACHE_CODE+flash.HOOK_LINES+(0x214110,0x233c7c))})
    blob('hbl_flash_words',payload)
    scalar('hbl_flash_base',flash.PAYLOAD_START)
    scalar('hbl_flash_record',flash.RECORD)
    manifest=json.loads((out/'build/release/00800000/capture-manifest.json').read_text(encoding='utf-8'))
    hooks('hbl_af_hooks',{a:(before,after) for a,before,after in manifest['emulatorOnlyHooks']})
    for name in ('af_install_ack','af_install_probe','af_identity','__state_start'):
        scalar('hbl_offset_'+name,manifest['symbols'][name]-manifest['base'])
    (out/'boot_contract_data.h').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    report={'schema':'boot-data-contract-v1','hardwareRequests':0,'afContract':c.identity,
            'afExpectedWords':len(c.expected),'flashPayloadSha256':hashlib.sha256(payload).hexdigest(),
            'headerSha256':hashlib.sha256((out/'boot_contract_data.h').read_bytes()).hexdigest(),
            'installed':False}
    (out/'contract-proof.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
