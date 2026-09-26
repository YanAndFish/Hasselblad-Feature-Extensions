"""生成机械候选固定白名单；生成过程只读构建与本模块已审查源文件。"""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parents[1]

def prepare():
    assert Path.cwd().resolve()==HERE.parents[1]
    build=json.loads((HERE/'build/mechanical-sync-capture/target-build.json').read_text(encoding='utf-8'))
    symbols=build['hook_entries']
    entries={0x21409c:symbols['mechanical_sync_clear_hook'],0x21410c:symbols['mechanical_sync_start_hook'],
             0x213e60:symbols['mechanical_sync_status_hook'],0x213ef8:symbols['mechanical_sync_status_hook'],
             0x2143e4:symbols['mechanical_sync_finish_hook']}
    originals={0x21409c:0xeb0091df,0x21410c:0xeb0091c3,0x213e60:0xeb0092cd,0x213ef8:0xeb0092a7,0x2143e4:0xeb00916c}
    s=(HERE/'research/farm_sync_loader.py').read_text(encoding='utf-8')
    route=(HERE/'research/farm_route7_loader.py').read_text(encoding='utf-8')
    s=s.replace('GFS3','GMS1').replace('build/farm-sync-capture','build/mechanical-sync-capture')
    s=s.replace('PAYLOAD_START, PAYLOAD_BYTES, RECORD, RECORD_SIZE = 0x2B2880, 1660, 0x2b2d98, 356',
                f"PAYLOAD_START, PAYLOAD_BYTES, RECORD, RECORD_SIZE = {build['base']}, {build['payload_bytes']}, {build['record_address']}, 364")
    s=re.sub(r'^PAYLOAD_SHA = .+$','PAYLOAD_SHA = '+repr(build['payload_sha256']),s,flags=re.M)
    s=s.replace('MAGIC = 0x33534647','MAGIC = 0x31534d47')
    s=re.sub(r'^HOOK_ENTRIES = .+$','HOOK_ENTRIES = '+repr(entries),s,flags=re.M)
    s=re.sub(r'^ORIGINAL_HOOKS = .+$','ORIGINAL_HOOKS = '+repr(originals),s,flags=re.M)
    s=s.replace('(0xEB000000 if a == 0x21409C else 0xEA000000)','0xEB000000')
    a=s.index('AF_ENTRY_POINTS ='); b=s.index('AF_SPEEDS =',a)
    ra=route.index('AF_ENTRY_POINTS ='); rb=route.index('AF_SPEEDS =',ra)
    s=s[:a]+route[ra:rb]+'''PREVIOUS_HOOKS=(0x1c4318,0x1ce150,0x1c8874,0x1c8950,0x1c52a0,0x1ca0b4,0x1c4380,0x1c4458,0x1c44f4)
AF_CODE=tuple(sorted(set(AF_CODE)|{p for a in PREVIOUS_HOOKS for p in range(a&~31,(a&~31)+32,4)}))
'''+s[b:]
    a=s.index('ZERO_RANGES ='); b=s.index('ZERO_WORDS =',a)
    s=s[:a]+'ZERO_RANGES = ((0x2b26a0,0x2b4000),)\n'+s[b:]
    a=s.index('def offline_ready():'); b=s.index('\ndef request(',a)
    s=s[:a]+'''def offline_ready():
    """源码、两个 ELF、装载故障模型、FPGA 模型和七路接收程序全部绑定当前字节。"""
    try:
        output=HERE/'build/mechanical-sync-capture'
        arm=json.loads((output/'validation.json').read_text(encoding='utf-8'))
        loader=json.loads((output/'loader-validation.json').read_text(encoding='utf-8'))
        fpga=json.loads((output/'fpga-validation.json').read_text(encoding='utf-8'))
        app=json.loads((HERE/'build/mechanical-sync-candidate/manifest.json').read_text(encoding='utf-8'))
        if not all(r.get('passed') for r in (arm,loader,fpga)) or loader.get('tests',0)<7: return False
        if not app.get('checks',{}).get('passed') or len(app.get('availableSources',[]))!=7: return False
        if arm.get('payload_sha256')!=PAYLOAD_SHA or loader.get('payload_sha256')!=PAYLOAD_SHA: return False
        payload()
        for variant in ('simulation','target'):
            check=arm.get(variant,{})
            if not check.get('passed') or check.get('tests')!=8: return False
            if hashlib.sha256((output/(variant+'.elf')).read_bytes()).hexdigest()!=check['elf_sha256']: return False
        for report,key in ((arm,'source_hashes'),(loader,'source_hashes'),(fpga,'source_hashes'),(app,'sourceHashes')):
            if not report.get(key): return False
            for name,digest in report[key].items():
                if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest: return False
        for name,meta in app['files'].items():
            if hashlib.sha256((HERE/'build/mechanical-sync-candidate'/name).read_bytes()).hexdigest()!=meta['sha256']: return False
        return True
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        return False

'''+s[b:]
    s=s.replace('self.requests >= 5000','self.requests >= 12000')
    old='''        for address in AF_SPEEDS:
            if self.io.read(address) != 5000:
                raise RuntimeError("manual restart/original AF required")'''
    new='''        self.af_speeds=[self.io.read(address) for address in AF_SPEEDS]
        if len(set(self.af_speeds))!=1 or self.af_speeds[0] not in (3800,4500,5000):
            raise RuntimeError("unsupported or inconsistent AF speed baseline")'''
    assert s.count(old)==1; s=s.replace(old,new)
    s=s.replace('"original_af_and_empty_arena_verified": True,','"original_af_and_empty_arena_verified": True, "af_speeds": self.af_speeds,')
    s=s.replace('any(self.io.read(a) != 5000 for a in AF_SPEEDS)',
                '[self.io.read(a) for a in AF_SPEEDS] != self.record["af_speeds"]')
    s=s.replace('仅允许手动重启后的原厂 AF 状态','要求空白区、原厂指令及一致的既有 AF 速度；不修改速度')
    (HERE/'research/mechanical_sync_loader.py').write_text(s,encoding='utf-8')
    tests=(HERE/'CodeTests/test_farm_sync_loader.py').read_text(encoding='utf-8')
    tests=tests.replace('research/farm_sync_loader.py','research/mechanical_sync_loader.py').replace('GFS1','GMS1').replace('双入口','五入口').replace('both_hooks','all_hooks')
    extra='''    def test_existing_3800_and_4500_speeds_are_preserved(self):
        for speed in (3800,4500):
            io=FakeIO()
            for a in m.AF_SPEEDS: io.memory[a]=speed
            loader=MemoryLoader(io)
            loader.prepare(FARM,m.HERE/'build/mechanical-model-only-no-file-is-written.json')
            loader.probe(); loader.install_disarmed(); loader.arm(); loader.unhook()
            self.assertEqual([io.memory[a] for a in m.AF_SPEEDS],[speed]*3)
            self.assertFalse(any(a in m.AF_SPEEDS for a,v in io.trace))

'''
    tests=tests.replace('    def test_fixed_write_scope_and_no_before_prepare_writes(self):',extra+'    def test_fixed_write_scope_and_no_before_prepare_writes(self):')
    (HERE/'CodeTests/test_mechanical_sync_loader.py').write_text(tests,encoding='utf-8')
    return {'entries':entries,'payload_sha256':build['payload_sha256'],'hardware_requests':0}

if __name__=='__main__': print(prepare())
