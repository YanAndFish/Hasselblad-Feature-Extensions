"""完整归档的最小差异与原厂资源路径配对；不启动设备或 UI。"""
import hashlib,io,json,sys,tarfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];AF=HERE.parent
def contents(path):
    with tarfile.open(path) as archive:return {m.name:(archive.extractfile(m).read(),m.mode) for m in archive if m.isfile()}
class CompositionTests(unittest.TestCase):
    def test_exact_frozen_components_and_only_intended_replacements(self):
        old=contents(AF/'delivery-r5/inputs/af-only.tar.gz');new=contents(HERE/'inputs/af-only.tar.gz')
        changed={n for n in old if n in new and old[n][0]!=new[n][0]}
        self.assertEqual(changed,{'common.sh','af/libhbl-af-ui.so','af/libhbl-af-bus.so','af-only-ui.rcc','manifest.sha256'})
        self.assertEqual(set(new)-set(old),set())
        self.assertFalse(set(old)-set(new))
        for name,source in [('af/libhbl-af-ui.so',HERE/'ui/linux-build/libhbl-af-ui.so'),
                            ('af/libhbl-af-bus.so',HERE/'bus/linux-build/libhbl-af-bus.so'),
                            ('af-only-ui.rcc',HERE/'ui/build/resources/af-only-ui.rcc')]:
            self.assertEqual(new[name][0],source.read_bytes())
        for name in ('system-check','libhbl-af-only.so','hold-file.check','baseline.sha256','run.sh'):
            self.assertEqual(new[name][0],old[name][0])
        self.assertEqual(new['bus-local-check'][1],0o700)
    def test_first_start_uses_single_owned_dropins_and_original_resource_path(self):
        install=(HERE/'inputs/install.sh').read_text(encoding='utf-8')
        common=(HERE/'inputs/common.sh').read_text(encoding='utf-8')
        self.assertIn("'Environment=HBL_AF_UI_R4_ENABLE=0'",install)
        self.assertNotIn('95-hbl',install+common)
        self.assertIn('backend-r5.status',common);self.assertNotIn('backend-r2.status',common)
        self.assertEqual(install.count('systemctl restart victory-gui'),1)
        self.assertEqual(install.count('systemctl restart msg2dbus-farm'),1)
        self.assertNotIn('bus.pid',common+install)
        old=(AF/'bus-roundtrip-r3/local_check.cpp').read_text(encoding='utf-8')
        self.assertEqual((HERE/'local_check.cpp').read_text(encoding='utf-8'),old.replace('/tmp/hbl-af-bus-r3/local-check','/tmp/hbl-x1d-combined/local-check'))
        source=(HERE/'ui/settings_ui.cpp').read_text(encoding='utf-8')
        self.assertIn('!std::strcmp(v,"1") && file==QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc")',source)
    def test_original_farm_runtime_builder_and_recovery_contract_preserved(self):
        import sys
        sys.path.insert(0,str(HERE));import runtime,range_contract
        m=range_contract.verify_variant();self.assertEqual(len(m['emulatorOnlyHooks']),15)
        c=runtime.AfOnlyContract(nonce=42)
        self.assertIn(0x19d5c0,c.allowed);self.assertEqual(c.allowed[0x19d5c0],{0xe24bd008})
        for n in ('session.py','recovery.py','linux_command.py','transfer.py'):
            before=(AF/'delivery-r5'/n).read_text(encoding='utf-8').replace('ui-interaction-r4','ui-probe-r6').replace('bus-roundtrip-r3','bus-reply-r6') if n=='session.py' else (AF/'delivery-r5'/n).read_text(encoding='utf-8')
            self.assertEqual((HERE/n).read_text(encoding='utf-8'),before)
        source=(HERE/'session.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('loader.install('),1)
        self.assertNotIn('AS_QUERY',source);self.assertNotIn('AS_APPLY',source)
        self.assertIn('same-linux-manifest',source)
