"""冻结当前离线证据与来源；不导入或执行任何设备入口。"""
import hashlib, json, sys, unittest
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from settings_upgrade import FirstInstallContract, UpgradeContract, read_json
from test_candidate import CandidateTests, FARM
from test_stop_path import StopPathTests

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    first = FirstInstallContract(FARM)
    historical = UpgradeContract(FARM)
    candidate = read_json(HERE / 'build/00800000/capture-manifest.json')
    transactions = read_json(HERE / 'build/upgrade-tests.json')
    if not transactions['passed'] or transactions['candidateSha256'] != candidate['payload_sha256']:
        raise ValueError('current transaction model evidence required')
    if transactions['relocatedSha256'] != sha(HERE / 'build/002bacc0/candidate.bin'):
        raise ValueError('relocated evidence changed')
    for name, expected in transactions['sourceSha256'].items():
        if sha(HERE / name) != expected:
            raise ValueError('transaction test source changed: ' + name)
    client = read_json(HERE / 'linux-build/client-build.json')
    for name, expected in client['sourceHashes'].items():
        if sha(HERE / name) != expected:
            raise ValueError('Qt source changed: ' + name)
    for name, expected in client['outputs'].items():
        if sha(HERE / 'linux-build' / name) != expected['sha256']:
            raise ValueError('Qt library changed')
    page = read_json(HERE / 'build/page-tests/validation.json')
    if not page['passed'] or page['qmlSha256'] != sha(HERE / 'SettingsPage.qml'):
        raise ValueError('current page validation required')
    suite = unittest.TestSuite()
    for case in (CandidateTests, StopPathTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise ValueError('ARM protocol/path checks failed')
    paths = [p for p in HERE.iterdir() if p.suffix in ('.c', '.h', '.cpp', '.S', '.qml', '.py')]
    paths += list((HERE / 'CodeTests').glob('*.py'))
    for relative in ('build/00800000/candidate.bin', 'build/00800000/capture-manifest.json',
        'build/002bacc0/candidate.bin', 'build/002bacc0/capture-manifest.json',
        'build/upgrade-tests.json', 'build/stop-path-tests.json', 'build/page-tests/validation.json',
        'linux-build/client-build.json', 'linux-build/libhbl-af-ui.so', 'linux-build/libhbl-af-bus.so',
        'installed-baseline/source-manifest.json', 'installed-baseline/audited-installation.json'):
        paths.append(HERE / relative)
    for name, value in read_json(HERE / 'installed-baseline/source-manifest.json').items():
        p = HERE / 'installed-baseline' / name
        if sha(p) != value['sha256']:
            raise ValueError('frozen observation input changed')
        paths.append(p)
    paths += [HERE.parent / name for name in ('native_install.py', 'native_loader.py', 'native_hold.py', 'r3_install_journal.py')]
    from settings_hold import CHECKER
    paths.append(ROOT / CHECKER)
    report = {'passed': True, 'hardwareRequests': 0, 'offlineFirstInstallReady': True,
        'offlineUpgradeReady': True, 'offlineRollbackReady': True,
        'firstInstallContractSha256': first.identity, 'historicalUpgradeContractSha256': historical.identity,
        'candidateSha256': candidate['payload_sha256'], 'nativeTests': result.testsRun,
        'transactionTests': transactions['tests'], 'qtDesktopPagePassed': True,
        'targetQtRuntimeVerified': False, 'actualTimingActionsConnected': False,
        'supported': ['三个默认原厂速度及五/四/五档手动速度', '远端优先及有限折返',
                      '可选抗噪判向，默认关闭', '两个绝对提前量独立保存回读，尚未实际介入'],
        'physicalPrerequisites': ['root 独占新组合窗口且 checker 当前成功', '正式 HFS1 已先安装且空闲',
            'root 验证目标 Qt/组合资源，AF 设置页在装载期间不查询', '完整现场预检、原厂申请、缓存和执行回执'],
        'files': {str(p.relative_to(HERE)) if p.is_relative_to(HERE) else str(Path(__import__('os').path.relpath(p, HERE))): sha(p)
                  for p in paths}}
    target = HERE / 'build/delivery-validation.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
