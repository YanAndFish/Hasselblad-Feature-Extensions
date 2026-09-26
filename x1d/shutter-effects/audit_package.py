"""复核 X1D 签名候选与原包差异，离线运行。"""
from pathlib import Path
import hashlib
import io
import json
import tarfile
import wave

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=ROOT/'x1d/patch-distribution/build/confirmed-ui-20260922-203447/stage/files'
STAGE=HERE/'build/candidate/persistent-stage-r4'
ARCHIVE=HERE/'build/candidate/x1d-ciallo-persistent-candidate-r4.tgz'
REPORT=HERE/'build/candidate/result.json'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    meta=json.loads(REPORT.read_text(encoding='utf-8'))
    assert meta['persistentPackageBuilt'] and not meta['installed'] and not meta['cameraValidated']
    files=STAGE/'files'
    old={p.name:sha(p.read_bytes()) for p in OLD.iterdir() if p.is_file()}
    new={p.name:sha(p.read_bytes()) for p in files.iterdir() if p.is_file()}
    changed={name for name in old if old[name]!=new.get(name)}
    assert changed=={'af-ui.rcc','hotspot-libhotspot-entry.so','manifest.sha256','authorization.bin'},changed
    assert set(new)-set(old)=={'ciallo.wav'}
    assert new['ciallo.wav']==meta['audioSha256']
    assert new['af-ui.rcc']==meta['sealedRccSha256']
    assert new['hotspot-libhotspot-entry.so']==meta['nativeSha256']
    assert (STAGE/'transaction-profile').read_bytes()==b'native-v1\n'
    assert (STAGE/'camera-transaction').read_bytes()==(OLD.parent/'camera-transaction').read_bytes()
    lines=(files/'manifest.sha256').read_text(encoding='ascii').splitlines()
    assert len(lines)==len(new)-2
    for line in lines:
        digest,name=line.split('  ',1)
        assert name in new and digest==new[name] and name not in ('manifest.sha256','authorization.bin')
    with tarfile.open(ARCHIVE,'r:gz') as archive:
        entries={item.name:item for item in archive.getmembers()}
        expected={p.relative_to(STAGE).as_posix() for p in STAGE.rglob('*') if p.is_file()}
        assert set(entries)==expected
        for name,item in entries.items():
            assert item.isfile() and not name.startswith('/') and '..' not in Path(name).parts
            assert sha(archive.extractfile(item).read())==sha((STAGE/name).read_bytes())
    with wave.open(io.BytesIO((files/'ciallo.wav').read_bytes()),'rb') as audio:
        duration=audio.getnframes()/audio.getframerate()
        assert 1<duration<2
    print(json.dumps({'passed':True,'unchangedPayloadFiles':len(old)-len(changed),
        'changedPayloadFiles':sorted(changed),'addedPayloadFiles':['ciallo.wav'],
        'audioDurationSec':round(duration,6),'archiveSha256':sha(ARCHIVE.read_bytes()),
        'cameraRequests':0},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
