"""对已上传检查程序应用离线已验证的 ELF 布局差异；不改无线固件或 FARM。"""
from pathlib import Path
import hashlib,json,shlex

HERE=Path(__file__).resolve().parents[1]
OUT=HERE/'build/mechanical-hw-ready-candidate'
REMOTE='/tmp/hbl-wireless-flash'
def sha(data): return hashlib.sha256(data).hexdigest()

def apply(session,existing_backup=False):
    old=(OUT/'before-probe-layout-fix/netlink-probe').read_bytes()
    new=(OUT/'netlink-probe').read_bytes()
    report=json.loads((OUT/'client-build.json').read_text(encoding='utf-8'))
    if len(old)!=len(new) or sha(new)!=report['netlinkProbeSha256']: raise RuntimeError('Unexpected repair bytes')
    before=session.command('probe-before-repair','sha256sum '+REMOTE+'/netlink-probe')
    if before['output'].split()[0]!=sha(old): raise RuntimeError('Uploaded probe does not match failed layout')
    if existing_backup:
        saved=session.command('verify-probe-backup','sha256sum '+REMOTE+'/netlink-probe.before-layout-fix')
        if saved['output'].split()[0]!=sha(old): raise RuntimeError('Unexpected existing backup')
    else:
        session.command('save-probe-before-repair','d='+REMOTE+';test ! -e "$d/netlink-probe.before-layout-fix" && cp -p "$d/netlink-probe" "$d/netlink-probe.before-layout-fix"')
    differences=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
    blocks=[]
    for i in differences:
        if blocks and i-blocks[-1][1]<=8 and i-blocks[-1][0]<24: blocks[-1][1]=i+1
        else: blocks.append([i,i+1])
    for index,(start,end) in enumerate(blocks):
        encoded=''.join('\\%03o'%b for b in new[start:end])
        cmd="printf '%b' "+shlex.quote(encoded)+' > '+REMOTE+'/probe.block'
        if len(cmd)>231: raise RuntimeError('Repair command too long')
        session.command('probe-layout-data-'+str(index),cmd)
        session.command('probe-layout-block-'+str(index),'d='+REMOTE+';dd if="$d/probe.block" bs=1 seek='+str(start)+' 1<>"$d/netlink-probe" 2>/dev/null')
    verified=session.command('probe-patch-verified','sha256sum '+REMOTE+'/netlink-probe')
    if verified['output'].split()[0]!=sha(new): raise RuntimeError('Corrected probe hash mismatch')
    session.command('update-probe-manifest','sed -i s/'+sha(old)+'/'+sha(new)+'/ '+REMOTE+'/manifest.sha256')
    whole=session.command('corrected-files-verified','cd '+REMOTE+' && sha256sum -c manifest.sha256 >/dev/null && printf corrected-files-verified')
    if whole['output']!='corrected-files-verified': raise RuntimeError('Corrected file set mismatch')
    evidence={'oldSha256':sha(old),'newSha256':sha(new),'blocks':blocks,'changedBytes':len(differences),
              'before':before,'verified':verified,'allFiles':whole,'session':str(session.output.relative_to(HERE)),
              'farmWrites':0,'wirelessFirmwareWrites':0,'cameraShotsTriggered':0,'agentFlashTrials':0}
    (OUT/'probe-layout-repair.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'repaired':True,'blocks':len(blocks),'allFilesVerified':True}
