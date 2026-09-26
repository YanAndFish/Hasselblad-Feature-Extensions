"""Full JPEG 输出增量：不接管原厂 RAW 回放，不执行设备操作。"""
from pathlib import Path
import hashlib, io, json, struct, sys, tarfile
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
ROOT = P.parents[3]
sys.path.insert(0, str(ROOT/'x1d/tools'))
from binary import ArmElf
from patch_full_jpeg import build as full_build
from patch_jpeg_failure import build as failure_build

def sha(b): return hashlib.sha256(b).hexdigest()

def components():
    config, cm = full_build()
    jpeg, jm = failure_build()
    elf = ArmElf(jpeg)
    # ImxEncoderWorker 构造函数保存编码质量的 r7。原厂调用者传入 jpg_quality。
    at = 0x22490
    assert elf.word(at) == 0xe1a07003  # mov r7,r3
    out = bytearray(jpeg)
    struct.pack_into('<I', out, elf.offset(at, 4), 0xe3a07055) # mov r7,#85
    return config, bytes(out), dict(config=cm, jpegFailure=jm,
        qualityAddress=at, quality=85, qualityBefore='mov r7,r3',
        targetBytesApprox=10000000, targetSizeMeasured=False)

def build():
    out=P/'build/full-jpeg-output'; stage=out/'stage'; files=stage/'files'
    files.mkdir(parents=True, exist_ok=True)
    tx=json.loads((out/'transaction-validation.json').read_text())
    assert tx['passed'] and tx['scriptSha256']==sha((P/'full-jpeg-output-install.sh').read_bytes())
    config,jpeg,meta=components()
    latest=P/'build/focus-delivery-repair/stage/files'
    original_manifest=(latest/'manifest.sha256').read_bytes()
    added={'configstore-full':config, 'jpeg-daemon-full':jpeg,
        'full-jpeg-config.conf':b'[Service]\nExecStart=\nExecStart=/opt/hbl-af-only-v1/configstore-full\n',
        'full-jpeg-encoder.conf':b'[Service]\nExecStart=\nExecStart=/opt/hbl-af-only-v1/jpeg-daemon-full\n'}
    for n,b in added.items(): (files/n).write_bytes(b)
    baseline=(latest/'baseline.sha256').read_bytes()
    for n in ['usr/bin/configstore','usr/bin/jpeg-daemon','lib/systemd/system/configstore.service','lib/systemd/system/jpeg-daemon.service']:
        b=(ROOT/'.research-cache/x1d-1.25.0/baseline'/n).read_bytes()
        baseline+=(sha(b)+'  /'+n+'\n').encode()
    (files/'baseline.sha256').write_bytes(baseline)
    lines=[]
    for line in original_manifest.decode().splitlines():
        h,n=line.split('  ',1)
        lines.append((sha(baseline) if n=='baseline.sha256' else h)+'  '+n)
    for n,b in added.items(): lines.append(sha(b)+'  '+n)
    manifest=('\n'.join(lines)+'\n').encode()
    (files/'manifest.sha256').write_bytes(manifest)
    (stage/'old-pin').write_text(sha(original_manifest)+'\n',newline='\n')
    (stage/'new-pin').write_text(sha(manifest)+'\n',newline='\n')
    (stage/'repair.sh').write_bytes((P/'full-jpeg-output-install.sh').read_bytes())
    (stage/'run.sh').write_bytes(b'#!/bin/sh\nexit 0\n')
    members=['files/'+n for n in [*added,'baseline.sha256','manifest.sha256']]+['old-pin','new-pin','repair.sh','run.sh']
    checks=''.join(sha((stage/n).read_bytes())+'  '+n+'\n' for n in sorted(members))
    for n in ['manifest.sha256','repair-manifest.sha256']:(stage/n).write_text(checks,newline='\n')
    members+=['manifest.sha256','repair-manifest.sha256']
    with tarfile.open(out/'repair.tgz','w:gz') as tar:
        for n in members:
            b=(stage/n).read_bytes(); info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o600
            tar.addfile(info,io.BytesIO(b))
    package=dict(bytes=(out/'repair.tgz').stat().st_size,packageSha256=sha((out/'repair.tgz').read_bytes()),
        oldPin=sha(original_manifest),newPin=sha(manifest),quality=85,targetSizeMeasured=False,
        rawPlaybackUnchanged=True,fullJpegOnCameraVerified=False,installed=False,components=meta)
    (out/'package.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
    installer=(P/'build/focus-delivery-repair/install.py').read_text().replace('focus-delivery-repair','full-jpeg-output').replace('/tmp/hbl-focus-delivery','/tmp/hbl-full-jpeg-output')
    installer=installer.replace("s=Lines('full-jpeg-output');", "proof=json.loads((O/'validation.json').read_text());assert proof['passed'] and proof['packageSha256']==json.loads((O/'package.json').read_text())['packageSha256']\ns=Lines('full-jpeg-output');")
    installer=installer.replace('cropScaling=False,session=s.summary()', 'cropScaling=False,fullJpegOutput=True,jpegQuality=85,targetSizeMeasured=False,session=s.summary()')
    (out/'install.py').write_text(installer,newline='\n')
    return package

if __name__=='__main__':print(json.dumps(build()))
