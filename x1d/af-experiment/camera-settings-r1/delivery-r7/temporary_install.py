"""Explicit X1D r7 release-profile RAM installation; restart removes it."""
import argparse,hashlib,json,secrets,sys
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];AF=HERE.parents[1]
if Path.cwd().resolve()!=ROOT:raise RuntimeError('Hasselblad workspace required')
sys.path[:0]=[str(HERE),str(HERE.parent),str(AF)]
import runtime
from candidate import build
from r3_install_journal import InstallJournal
from native_loader import failure

VALIDATION=HERE/'CodeTests/output/r7-temporary-release-validation.json'
class TemporaryLoader(runtime.AfOnlyLoader):
    def __init__(self,c,io):
        # This entry exists only behind the explicit install-release-temporary action.
        runtime.OriginalLoader.__init__(self,c,io)

    def hold_initial(self):
        # 用户明确授权本次不依赖 Linux GUI hold 的临时装载。
        io=self.io
        if io.requests or self.journal or io.transfer_active or not io.closed:
            raise RuntimeError('new serial transaction required')

    def hold_boundary(self,label,park=False):
        # 保留原回调恢复、SGI 完成、串行和未知结果即停检查；不伪造 hold 回执。
        io=self.io;old=runtime.old
        try:
            if (io.failed or io.transfer_active or not io.closed or io.wake_live or
                (self.journal and (self.journal.record.get('inFlight') is not None or
                                  self.journal.record.get('cacheInFlight') is not None))):
                raise RuntimeError('operation still in flight at serial boundary')
            self.quiescent()
            if park:
                if io.read(old.CB)!=old.NOOP:raise RuntimeError('cache slot changed')
                self.write(old.ARG,old.ORIG_ARG);self.write(old.CB,old.ORIG_CB);self.quiescent()
            if io.read(old.CB)!=old.ORIG_CB or io.read(old.ARG)!=old.ORIG_ARG:
                raise RuntimeError('original callback required at serial boundary')
            self.quiescent()
        except BaseException:
            io.failed=True
            raise

def validation():
    if not VALIDATION.is_file():raise RuntimeError('offline release validation missing; no USB opened')
    proof=json.loads(VALIDATION.read_text(encoding='utf-8'))
    manifest=HERE/'build/release/00800000/capture-manifest.json'
    if not proof.get('passed') or proof.get('hardwareRequests')!=0 or proof.get('tests',0)<51:
        raise RuntimeError('offline release validation failed; no USB opened')
    if proof.get('releaseManifestSha256')!=hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise RuntimeError('validated release manifest changed; no USB opened')
    for name,digest in proof.get('sources',{}).items():
        path=(HERE/name).resolve()
        if not path.is_relative_to(HERE) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('validated source changed: '+name+'; no USB opened')
    return proof

def install():
    proof=validation();contract=runtime.AfOnlyContract(nonce=secrets.randbelow(0xffffffff)+1,profile='release')
    contract.identity=runtime.old.digest({'baseContract':contract.identity,
        'temporaryInstallSource':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'guiHoldRequired':False,'authorization':'explicit-user-standby-ram-install'})
    contract.hold={'required':False,'checksPerformed':False,'userAuthorizedStandbyInstall':True}
    stamp=datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    (HERE/'recovery').mkdir(exist_ok=True)
    trace=runtime.Trace(HERE/'recovery'/('temporary-release-'+stamp+'.trace.jsonl'),contract.identity)
    io=runtime.TracedIO(contract,trace);loader=TemporaryLoader(contract,io);journal=None
    path=HERE/'recovery'/('temporary-release-'+stamp+'.json')
    try:
        print(json.dumps({'stage':'read-only-preflight','writes':0}),flush=True)
        loader.preflight()
        journal=InstallJournal(path,contract.identity,backend='fixed_usb');loader.attach(journal)
        loader.persist(profile='release',temporaryRam=True,restartRemoves=True,
            validationSha256=hashlib.sha256(VALIDATION.read_bytes()).hexdigest(),tracePath=str(trace.path.relative_to(ROOT)))
        print(json.dumps({'stage':'preflight-passed','writes':io.writes}),flush=True)
        loader.probe();result,header=loader.stage()
        manifest,out=build(result[9],profile='release')
        loader.install(result,header,manifest,(out/'candidate.bin').read_bytes())
        loader.persist(profile='release',temporaryRam=True,restartRemoves=True,eightLensPolicy=True,
            startRatioPercent=70,effectiveSamples=10,fineAdvanceMs=100,factoryFastScan=False,
            fixedFarFirst=True,allLensRules=True,eightLensRawMaximum=True)
        journal.close();journal=None
        audit=InstallJournal.read_record(path,contract.identity)
        if (not audit.get('installed') or audit.get('phase')!='installed_settings_until_restart' or
            audit.get('inFlight') is not None or audit.get('cacheInFlight') is not None or
            audit.get('requiresReview') or not audit.get('allHandlesClosed') or audit['journalAudit'].get('incompleteTail')):
            raise RuntimeError('temporary installation audit incomplete')
        print(json.dumps({'stage':'installed-temporary-release','installed':True,'restartRemoves':True,
            'hardwareRequests':io.requests,'writeRequests':io.writes,'allHandlesClosed':io.closed,
            'recovery':path.name}),flush=True)
        return 0
    except BaseException as error:
        if journal is not None:failure(loader,journal,error)
        print(json.dumps({'stage':'stopped-no-retry','errorType':type(error).__name__,'error':str(error),
            'hardwareRequests':io.requests,'writeRequests':io.writes,'allHandlesClosed':io.closed}),flush=True)
        raise
    finally:
        if journal is not None:journal.close()
        trace.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('report','install-release-temporary'),nargs='?',default='report')
    args=parser.parse_args()
    if args.action=='report':
        proof=validation();print(json.dumps({'ready':True,'profile':'release','temporaryRam':True,
            'restartRemoves':True,'hardwareRequests':0,'offlineTests':proof['tests']}));return
    install()
if __name__=='__main__':main()
