"""完整归档的最小差异与原厂资源路径配对；不启动设备或 UI。"""
import hashlib,io,json,sys,tarfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];AF=HERE.parent
def contents(path):
    with tarfile.open(path) as archive:return {m.name:(archive.extractfile(m).read(),m.mode) for m in archive if m.isfile()}
class CompositionTests(unittest.TestCase):
    def test_exact_frozen_components_and_only_intended_replacements(self):
        old=contents(AF/'delivery-r3/inputs/af-only.tar.gz');new=contents(HERE/'inputs/af-only.tar.gz')
        changed={n for n in old if n in new and old[n][0]!=new[n][0]}
        self.assertEqual(changed,{'common.sh','install.sh','restore.sh','af/libhbl-af-ui.so','af/libhbl-af-bus.so','af-only-ui.rcc','manifest.sha256'})
        self.assertEqual(set(new)-set(old),{'bus-local-check'})
        self.assertFalse(set(old)-set(new))
        for name,source in [('af/libhbl-af-ui.so',AF/'ui-interaction-r4/linux-build/libhbl-af-ui.so'),
                            ('af/libhbl-af-bus.so',AF/'bus-roundtrip-r3/linux-build/libhbl-af-bus.so'),
                            ('af-only-ui.rcc',AF/'ui-interaction-r4/build/resources/af-only-ui.rcc')]:
            self.assertEqual(new[name][0],source.read_bytes())
        for name in ('system-check','libhbl-af-only.so','hold-file.check','baseline.sha256','run.sh'):
            self.assertEqual(new[name][0],old[name][0])
        self.assertEqual(new['bus-local-check'][1],0o700)
    def test_first_start_uses_single_owned_dropins_and_original_resource_path(self):
        install=(HERE/'inputs/install.sh').read_text(encoding='utf-8')
        common=(HERE/'inputs/common.sh').read_text(encoding='utf-8')
        self.assertIn("'Environment=HBL_AF_UI_R4_ENABLE=0'",install)
        self.assertNotIn('95-hbl',install+common)
        self.assertIn('backend-r3.status',common);self.assertNotIn('backend-r2.status',common)
        self.assertEqual(install.count('systemctl restart victory-gui'),1)
        self.assertEqual(install.count('systemctl restart msg2dbus-farm'),1)
        self.assertNotIn('bus.pid',common+install)
        old=(AF/'bus-roundtrip-r3/local_check.cpp').read_text(encoding='utf-8')
        self.assertEqual((HERE/'local_check.cpp').read_text(encoding='utf-8'),old.replace('/tmp/hbl-af-bus-r3/local-check','/tmp/hbl-x1d-combined/local-check'))
        source=(AF/'ui-interaction-r4/settings_ui.cpp').read_text(encoding='utf-8')
        self.assertIn('!std::strcmp(v,"1") && file==QStringLiteral("/tmp/hbl-x1d-combined/af-only-ui.rcc")',source)
    def test_original_farm_runtime_builder_and_recovery_contract_preserved(self):
        for n in ('runtime.py','candidate.py','rollback.py'):
            self.assertEqual((HERE/n).read_bytes(),(AF/'delivery-r3'/n).read_bytes())
        self.assertEqual((HERE/'build/002bacc0/candidate.bin').read_bytes(),(AF/'build/002bacc0/candidate.bin').read_bytes())
        source=(HERE/'session.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('loader.install('),1)
        self.assertNotIn('AS_QUERY',source);self.assertNotIn('AS_APPLY',source)
        self.assertIn('same-linux-manifest',source)
