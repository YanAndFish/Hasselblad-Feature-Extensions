"""冻结 AF 独立交付；复核原组合输入而不覆盖其报告，不建立设备连接。"""
import hashlib, json, os, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from af_only_install import AfOnlyContract, read_json
from settings_loader import readiness as combined_readiness

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    combined = combined_readiness()
    if combined is None:
        raise ValueError('frozen common AF sources/evidence changed')
    tests = read_json(HERE / 'build/af-only-tests.json')
    if not tests['passed'] or tests['hardwareRequests'] != 0:
        raise ValueError('offline AF-only transaction evidence required')
    for name, expected in tests['sourceSha256'].items():
        if sha(HERE / name) != expected:
            raise ValueError('AF-only tested source changed: ' + name)
    if (tests['candidateSha256'] != combined['candidateSha256'] or
            tests['relocatedSha256'] != sha(HERE / 'build/002bacc0/candidate.bin')):
        raise ValueError('AF candidate evidence changed')
    c = AfOnlyContract()
    files = dict(combined['files'])
    paths = [HERE / name for name in tests['sourceSha256']]
    paths += [Path(__file__), HERE / 'build/delivery-validation.json', HERE / 'build/af-only-tests.json']
    # 模型使用现有原厂 ARM 测试实现；核对它与已冻结来源相同。
    frozen = read_json(HERE / 'installed-baseline/source-manifest.json')
    for name, value in frozen.items():
        if name.startswith('x1d/af-experiment/CodeTests/') and name.endswith('.py'):
            path = ROOT / name
            if sha(path) != value['sha256']:
                raise ValueError('original ARM model source changed: ' + name)
            paths.append(path)
    for path in paths:
        files[os.path.relpath(path, HERE)] = sha(path)
    report = {'passed': True, 'standaloneAf': True, 'requiresInstalledHfs1': False,
        'hardwareRequests': 0, 'offlineFirstInstallReady': True, 'offlineRollbackReady': True,
        'firstInstallContractSha256': c.identity, 'exampleNonce': c.nonce,
        'candidateSha256': tests['candidateSha256'],
        'transactionTests': tests['tests'], 'nativeTests': combined['nativeTests'],
        'qtDesktopPagePassed': combined['qtDesktopPagePassed'], 'targetQtRuntimeVerified': False,
        'actualTimingActionsConnected': False, 'protectedFactoryWords': len(c.factory_flash_expected),
        'hold': c.hold, 'supported': combined['supported'],
        'physicalPrerequisites': ['主任务独占当前开机 AF 健康窗口',
            '原厂 AF/引闪入口、零 bootstrap 和引闪预留空白区',
            '目标 Qt/AF 导航由主任务验收，AF 页面装载期间不查询',
            '现场只读预检、原厂申请、缓存可见及执行回执'], 'files': files}
    (HERE / 'build/af-only-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
