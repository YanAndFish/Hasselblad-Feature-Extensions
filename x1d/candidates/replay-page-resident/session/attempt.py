"""保留旧远端根并准备同一冻结包的新轮次；默认仅输出离线方案。"""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json,sys
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('replay_attempt_delivery',Path(__file__).with_name('delivery.py'))
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)
package=delivery.package;ROOT=package.ROOT;OUT=package.OUT
REMOTE='/tmp/hbl-replay-page'
ARCHIVE='/tmp/hbl-replay-page-a1'
PACKAGE_SHA='8d960d2309f18923d80cb7b5e1fe452fc6f225260da15d5fc87b2bb1545611ad'
EXPECTED_NAMES=['preflight.exit','preflight.log','preflight.sent','ui.exit','ui.log','ui.sent']

def command(session,label,text):
    return session.command(label,delivery.bounded(text))['output'].strip()

def inspect(session,report):
    if report['packageSha256']!=PACKAGE_SHA:raise ValueError('unexpected package revision')
    expected_manifest=report['files']['manifest.sha256']
    actual=command(session,'attempt-manifest','sha256sum '+REMOTE+'/manifest.sha256').split()
    if not actual or actual[0]!=expected_manifest:raise RuntimeError('remote package identity')
    # 直接调用已审核的只读前置检查；它在状态、drop-in、服务或健康不干净时失败。
    if command(session,'attempt-clean','sh '+REMOTE+'/install.sh preflight').splitlines()!=['replay-health-self-test-pass','replay-page-preflight-ready']:
        raise RuntimeError('original clean preflight')
    base='r='+REMOTE+';. "$r/common.sh";'
    if command(session,'attempt-phase-dir',base+'private "$r/phases"&&absent "$r/phase.lock"&&printf phase-dir-clean')!='phase-dir-clean':
        raise RuntimeError('phase directory')
    for phase in ('preflight','ui'):
        text=base+'for f in '+phase+'.sent '+phase+'.exit '+phase+'.log;do regular "$r/phases/$f"||exit 1;done;printf '+phase+'-regular'
        if command(session,'attempt-'+phase+'-records',text)!=phase+'-regular':raise RuntimeError(phase+' record integrity')
    names=command(session,'attempt-record-names','ls -1 '+REMOTE+'/phases').splitlines()
    if names!=EXPECTED_NAMES:raise RuntimeError('unexpected phase record set')
    exits=command(session,'attempt-exits','cat '+REMOTE+'/phases/preflight.exit '+REMOTE+'/phases/ui.exit').splitlines()
    if exits!=['0','62']:raise RuntimeError('unexpected completed outcomes')
    probe='r='+REMOTE+';a='+ARCHIVE+';if [ ! -e "$a" ]&&[ ! -L "$a" ]&&[ ! -e "$r/state" ]&&[ ! -L "$r/state" ];then printf archive-ready;fi'
    if command(session,'attempt-destination',probe)!='archive-ready':raise RuntimeError('archive destination or old install state')
    return {'packageSha256':PACKAGE_SHA,'oldOutcomes':{'preflight':0,'ui':62},'recordNames':names}

def archive(session,report):
    proof=inspect(session,report)
    # 单一同文件系统 rename；响应未知时只能 --observe，禁止重发。
    text='r='+REMOTE+';a='+ARCHIVE+';. "$r/common.sh";private "$r"&&absent "$a"&&absent "$r/state"&&absent "$r/phase.lock"&&mv "$r" "$a"&&printf archived'
    if command(session,'attempt-archive-once',text)!='archived':raise RuntimeError('archive outcome unknown; observe only')
    proof.update({'archived':True,'archive':ARCHIVE,'newRootPresent':False})
    return proof

def observe(session,report):
    if report['packageSha256']!=PACKAGE_SHA:raise ValueError('unexpected package revision')
    state=command(session,'attempt-observe-roots','r='+REMOTE+';a='+ARCHIVE+';[ -d "$a" ]&&[ ! -L "$a" ]&&printf archive=1||printf archive=0;[ -d "$r" ]&&[ ! -L "$r" ]&&printf " root=1"||printf " root=0"')
    if state not in ('archive=1 root=0','archive=1 root=1','archive=0 root=1'):raise RuntimeError('ambiguous root state')
    archived=state.startswith('archive=1')
    if archived:
        actual=command(session,'attempt-observe-manifest','sha256sum '+ARCHIVE+'/manifest.sha256').split()
        if not actual or actual[0]!=report['files']['manifest.sha256']:raise RuntimeError('archived package identity')
    return {'packageSha256':PACKAGE_SHA,'archived':archived,'archive':ARCHIVE if archived else None,'newRootPresent':state.endswith('root=1')}

def main(args):
    report,_=package.verify()
    if not args:
        print(json.dumps({'ready':True,'mode':'offline-plan','packageSha256':PACKAGE_SHA,'archive':ARCHIVE,
            'remoteRequests':0,'hardwareRequests':0,'next':['--archive','--observe','delivery.py --stage','delivery.py --phase preflight','delivery.py --phase ui','delivery.py --phase status']}));return
    if args not in (['--archive'],['--observe']):raise ValueError('usage: --archive | --observe')
    name='attempt-archive' if args==['--archive'] else 'attempt-observe'
    session=delivery.Session(name);result={'completed':False,'operation':args,'packageSha256':PACKAGE_SHA}
    try:
        result.update(archive(session,report) if args==['--archive'] else observe(session,report));result['completed']=True
    except BaseException as error:result['failure']=str(error);raise
    finally:
        result.update(session.summary());package.build.save(session.directory/'result.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main(sys.argv[1:])
