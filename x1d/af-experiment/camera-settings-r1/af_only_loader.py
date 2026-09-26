"""固定 AF 设置装载入口。默认 report 离线；设备动作只由主任务独占执行。"""
import argparse, hashlib, json, secrets, sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode = True
from af_only_install import *
from af_only_rollback import AfOnlyRollbackContract, AfOnlyRollbackLoader
from r3_install_journal import InstallJournal
from native_loader import failure

VALIDATION = HERE / 'build/af-only-validation.json'

def readiness():
    if not VALIDATION.is_file():
        return None
    report = read_json(VALIDATION)
    if not report.get('standaloneAf') or report.get('requiresInstalledHfs1') is not False or not report.get('passed') or not report.get('offlineFirstInstallReady') or not report.get('offlineRollbackReady'):
        return None
    for name, sha in report['files'].items():
        path = (HERE / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            return None
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('report', 'first-install', 'rollback'), default='report', nargs='?')
    parser.add_argument('--journal', type=Path)
    args = parser.parse_args()
    report = readiness()
    if args.action == 'report':
        print(json.dumps({'hardwareRequests': 0, 'standaloneAf': True, 'flashInstalled': False, 'offlineReady': bool(report),
            'report': str(VALIDATION), 'actualTimingActionsConnected': False,
            'requires': '主任务当前独占 AF 健康窗口；原厂 AF/引闪入口与空白区；目标 Qt/资源由主任务验收'}, ensure_ascii=False))
        return
    if report is None:
        raise RuntimeError('current frozen offline delivery validation required; no USB opened')
    if args.action == 'rollback':
        if args.journal is None:
            raise ValueError('completed settings installation journal required')
        c = AfOnlyRollbackContract.from_journal(args.journal)
        loader = AfOnlyRollbackLoader(c, UpgradeIO(c))
    else:
        if args.journal is not None:
            raise ValueError('install creates a new journal; no resume input')
        c = AfOnlyContract(nonce=secrets.randbelow(0xffffffff) + 1)
        loader = AfOnlyLoader(c, UpgradeIO(c))
    journal = None
    try:
        loader.preflight()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        directory = HERE / 'af-only-recovery'
        directory.mkdir(exist_ok=True)
        path = directory / ('af-only-' + args.action + '-' + stamp + '.json')
        journal = InstallJournal(path, c.identity, backend='fixed_usb')
        loader.attach(journal)
        loader.persist(deliveryValidationSha256=hashlib.sha256(VALIDATION.read_bytes()).hexdigest())
        print(json.dumps({'stage': loader.phase, 'recovery': str(path)}, ensure_ascii=False), flush=True)
        loader.probe()
        if args.action == 'rollback':
            loader.stage()
            loader.restore()
        else:
            result, header = loader.stage()
            print(json.dumps({'stage': loader.phase, 'payloadBase': result[9]}), flush=True)
            from build_candidate import build
            manifest, out = build(result[9])
            loader.install(result, header, manifest, (out / 'candidate.bin').read_bytes())
        print(json.dumps({'stage': loader.phase, 'requests': loader.io.requests,
            'writeRequests': loader.io.writes, 'allHandlesClosed': loader.io.closed,
            'actualTimingActionsConnected': False}), flush=True)
    except BaseException as error:
        failure(loader, journal, error)
        print(json.dumps({'stage': loader.phase, 'requests': loader.io.requests,
            'writeRequests': loader.io.writes, 'allHandlesClosed': loader.io.closed,
            'automaticRetry': False, 'automaticRestore': False}), flush=True)
        raise
    finally:
        if journal:
            journal.close()

if __name__ == '__main__':
    main()
