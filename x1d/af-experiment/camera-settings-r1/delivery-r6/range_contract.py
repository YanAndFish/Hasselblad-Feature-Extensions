"""r6 两阶段试探固定来源、15 个精确入口；保留原厂只读及首次装载保护。"""
import hashlib,json
from pathlib import Path
from af_only_install import AfOnlyContract as OriginalContract,old
HERE=Path(__file__).resolve().parent
AF=HERE.parent
REVIEWED_SOURCES={'native_af.c': '7d0569b550e02f8963459121a3e4d3559e0a4493d030e3567d1b639a0054a31a', 'native_adapter.c': 'b310e26851f8c0d705168b2f1153b8ce555e003ed0832df8394ab4c458e37d86', 'native_config.c': '119522cbc36090b2b850e30b725391aa57988f9b13a3fffd6fe30e0db79ca896', 'native_camera_bridges.S': '6dc4358a6c7bf490a66a4d4ba20e700f066964af2050d4582111a38e31a031c5', 'native_capture.c': 'd058efab4c20254f437732a4a2711a5acb9800f1501a0c6982513b2513c6c433', 'native_capture_bridges.S': 'ebb56bcc15d2e16a21c10e63c6a18c9877f8f4ce0bb66ca32c48422f0d1aca98', 'settings_receiver.c': '3952705fe601ec28846879f691eadcbd69567fbac21043835d4d12db45abd437', 'rolling_direction.c': 'c111a2ce65c3f8efa9a3298504c7055c95732454ded5d013b07a0f8fe0b6ccf9', 'native_af.h': 'eacfbbd6ddb8ab3a36c3887b4345ade24821c4bb0f365e885701de157b123f3a', 'native_config.h': 'aaa93e8df32087394db58dc3ff208cac276b781df02cda2d4e3249f5c4ca61d5', 'native_capture.h': '4fceeb2687e26d96285ba5f98c8c3b43d4848ed34db1116ec280712e638d434f', 'settings_wire.h': 'a61ea356ec8f20adc5210b95a9cd7807bdd545a02bc0c8819f08f0ceee66d3fb', 'rolling_direction.h': '9e75c9466b37295a068e7f224fa0571161437bc3ae36e44098f8aadef8edf69c', 'start_phase.h': 'b6cd4139d824ed93afd85c8a65845c309a7c8f9dd42b1b1a64080923fdbbbf91', 'build_candidate.py': '563fc8b267f7be3392f9f64f69d30101e01bf90127fc8bef2cc93fc0a4eb45f4'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def verify_variant():
    m=read(HERE/'build/00800000/capture-manifest.json')
    blob=(HERE/'build/00800000/candidate.bin').read_bytes()
    original=read(AF/'build/00800000/capture-manifest.json')
    if m['source_sha256']!=REVIEWED_SOURCES:raise ValueError('reviewed r6 source identity')
    for name,digest in REVIEWED_SOURCES.items():
        if hashlib.sha256((HERE/'native'/name).read_bytes()).hexdigest()!=digest:raise ValueError('r6 source changed: '+name)
    if hashlib.sha256(blob).hexdigest()!=m['payload_sha256']:raise ValueError('variant payload changed')
    if m['requestedHeapCapacity']!=32768 or m['baseline_sha256']!=old.BASELINE_SHA:raise ValueError('variant baseline/capacity')
    hooks={(a,v) for a,v,_ in m['emulatorOnlyHooks']}
    previous={(a,v) for a,v,_ in original['emulatorOnlyHooks']}
    if len(hooks)!=15 or hooks!=previous|{(0x19d5c0,0xe24bd008)}:raise ValueError('r6 hook scope')
    return m
class AfOnlyContract(OriginalContract):
    def __init__(self,farm=None,nonce=1):
        super().__init__(farm,nonce)
        previous=self.identity;self.offline=verify_variant()
        a=0x19d5c0;factory=0xe24bd008
        if self.farm.word(a)!=factory or self.expected.get(a)!=factory:raise ValueError('direction epilogue baseline')
        if (a&~31,32) not in self.ranges:raise ValueError('direction tail shares reviewed peak cache line')
        self.allowed[a]={factory};self.reads.add(a)
        self.identity=old.digest({'schema':'af-two-stage-r6','originalContract':previous,
            'candidate':self.offline['payload_sha256'],'sources':REVIEWED_SOURCES,
            'extraHook':[a,factory],'implementation':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
