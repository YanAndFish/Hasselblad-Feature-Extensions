"""离线验证构建失败状态与输入身份；不需要固件或工具链。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from build_contract import PREPARED_SHA256, TABLE_SHA256, validate_radio_tables, write_report


class BuildContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def run_failure(self, script, *args):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS/script), *map(str, args)],
                                capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)

    def test_generator_invalidates_previous_success_before_reading_input(self):
        write_report(self.folder/'radio-tables.json', {'passed': True})
        self.run_failure('generate_radio_tables.py', '--prepared-image', self.folder/'missing.bin',
                         '--output', self.folder)
        report = json.loads((self.folder/'radio-tables.json').read_text())
        self.assertIs(report['passed'], False)
        self.assertTrue(report['runId'])

    def test_worker_invalidates_previous_success_before_checking_inputs(self):
        write_report(self.folder/'worker-build.json', {'passed': True, 'compiled': True})
        self.run_failure('build_x1d_worker.py', '--zig', 'unavailable-compiler',
                         '--qtbase', self.folder, '--target-root', self.folder,
                         '--radio-tables', self.folder, '--build-dir', self.folder)
        report = json.loads((self.folder/'worker-build.json').read_text())
        self.assertIs(report['passed'], False)
        self.assertIs(report['compiled'], False)

    def test_core_invalidates_previous_success_before_checking_tables(self):
        write_report(self.folder/'core-validation.json', {'passed': True})
        self.run_failure('build_core.py', '--compiler', 'unavailable-compiler',
                         '--radio-tables', self.folder, '--build-dir', self.folder)
        self.assertIs(json.loads((self.folder/'core-validation.json').read_text())['passed'], False)

    def test_self_consistent_replacement_does_not_pass_baseline_check(self):
        files = {}
        for name in TABLE_SHA256:
            data = b'/* synthetic replacement */\n'
            (self.folder/name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
        write_report(self.folder/'radio-tables.json', {'passed': True, 'waveCount': 1345,
                     'inputSha256': PREPARED_SHA256, 'files': files})
        with self.assertRaisesRegex(ValueError, 'supported baseline'):
            validate_radio_tables(self.folder)

    def test_wrong_input_identity_rejected_before_headers_are_read(self):
        write_report(self.folder/'radio-tables.json', {'passed': True, 'waveCount': 1345,
                     'inputSha256': '0'*64, 'files': dict(TABLE_SHA256)})
        with self.assertRaisesRegex(ValueError, 'manifest'):
            validate_radio_tables(self.folder)


if __name__ == '__main__':
    unittest.main()
