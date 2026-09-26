"""记录已安装基线的固定恢复证据与组合接口边界；仅核对电脑文件。"""
from pathlib import Path
import hashlib
import json
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def run():
    stable=ROOT/'x1d/wireless-flash/build/formal-flash-package/stable-success-20260912T125921Z'
    snapshot=read(stable/'snapshot.sha256.json')
    for name,wanted in snapshot.items():assert sha((stable/name).read_bytes())==wanted,name
    joint_path=stable.parent/'joint-completion-20260912T131218Z.json';joint=read(joint_path)
    assert joint['completed'] and joint['holdReleased'] and joint['userControlsReleased']
    assert joint['flashInstallationSha256']==snapshot['installation-20260912T125921Z.json']
    af=ROOT/joint['afJournal'];assert af.is_file()
    evidence=[stable/'snapshot.sha256.json',stable/'installation-20260912T125921Z.json',
              stable/'formal-capture-recovery-20260912T125921Z.json',joint_path,af]
    source=(HERE/'joint/joint_runtime.cpp').read_text(encoding='utf-8')
    assert 'qRegisterResourceData' not in source and 'registerResource' not in source
    backend=(HERE/'joint/backend.sh').read_text(encoding='utf-8')
    assert 'systemctl restart "$role"' in backend
    assert 'for service in msg2dbus-farm storage-daemon;' in backend and '/tmp/hbl-x1d-rp' not in backend
    report={'offlineCoexistenceContractAudited':True,'cameraAccess':False,'currentTargetStateConfirmed':False,
            'protectedBaseline':'stable-success-20260912T125921Z + joint-completion-20260912T131218Z',
            'recoveryEvidenceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in evidence},
            'afJournalPrefixAsReportedByRoot':joint['afJournalAudit'],
            'afJournalChainRevalidatedHere':False,
            'permittedServiceMutations':['configstore','jpeg-daemon'],
            'protectedProcesses':['msg2dbus-farm','storage-daemon'],
            'workerRegistration':'same-process=1, pid=msg2dbus-farmPID, recorded master/radio-held/radio-busy=0',
            'workerRegistrationIsLiveState':False,
            'latestRootReportedBootState':'battery replacement cold boot; previous temporary flash paths/drop-ins gone; root must rebuild and verify this boot before replay prepare',
            'workerStatusWriterSourceSha256':sha((ROOT/'x1d/wireless-flash/native/formal_worker.cpp').read_bytes()),
            'coordinatorOwned':['unique RCC','GUI and msg2dbus-farm drop-ins/preload','shared hold lifecycle','FARM/AF RAM and callbacks'],
            'oldStandaloneInstallerCompatibleWithInstalledFlash':False,
            'sharedWindowInterface':'x1d/combined-runtime/native/install_window.h::hbl_combined_window_active()',
            'remainingInputs':['final main.qml path and SHA-256 after composition','final shared system-check path and SHA-256'],
            'sourceHashes':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in [Path(__file__),HERE/'joint/backend.sh',HERE/'joint/joint_runtime.cpp',HERE/'joint/joint_policy.h',HERE/'tools/compose_joint_resources.py']}}
    out=HERE/'artifacts/joint-tests';out.mkdir(parents=True,exist_ok=True)
    (out/'coexistence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'coexistenceContract':'audited','fixedSnapshotFiles':len(snapshot),'cameraAccess':False}))

if __name__=='__main__':run()
