"""r7 按 profile 绑定原厂首次装载契约；当前仅允许离线模拟。"""
import hashlib,json
from pathlib import Path
from af_only_install import AfOnlyContract as OriginalContract,old
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def branch(a,b,link=False):
    delta=b-a-8
    if b%4 or delta%4 or not -(1<<25)<=delta<(1<<25):raise ValueError('ARM branch range')
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
def hook_spec(profile):
    spec=[(0x1a1f64,'nc_probe_bridge',True),(0x19d41c,'nc_fast_bridge',True),
          (0x19d524,'nc_fast_bridge',True),(0x19d944,'nc_fine_bridge',True),
          (0x19d9b4,'nc_fine_bridge',True),(0x19bbec,'nc_reset_bridge',True),
          (0x1a3068,'nc_accepted_entry',False),(0x1a0498,'as_near_limit_bridge',False),
          (0x19d5c0,'na_direction_tail',False),(0x19890c,'af_identity_invalid_bridge',False),
          (0x1990f8,'af_identity_publish_bridge',False),(0x19d5c8,'af_peak_bridge',False)]
    if profile=='test':spec += [(0x1f0d2c,'nc_raw_entry',False),(0x1a1b48,'nc_cv_entry',False),
                               (0x1a2130,'nc_position_entry',False),(0x1e22b4,'as_receive_bridge',True)]
    return spec
def validate_manifest(m,blob,profile,farm):
    reviewed=read(HERE/'reviewed-profile-sources.json')
    if profile not in ('release','test') or m.get('profile')!=profile:raise ValueError('explicit matching profile required')
    if m['source_sha256']!=reviewed[profile]:raise ValueError('reviewed profile sources changed')
    for name,digest in reviewed[profile].items():
        if hashlib.sha256((HERE/'native'/name).read_bytes()).hexdigest()!=digest:raise ValueError('profile source changed: '+name)
    if m['requestedHeapCapacity']!=32768 or m['baseline_sha256']!=old.BASELINE_SHA:raise ValueError('profile baseline/capacity')
    if len(blob)!=m['end']-m['base'] or len(blob)%32 or len(blob)>32768 or hashlib.sha256(blob).hexdigest()!=m['payload_sha256']:
        raise ValueError('profile payload identity')
    expected={a:(farm.word(a),branch(a,m['symbols'][name],link)) for a,name,link in hook_spec(profile)}
    actual={a:(before,after) for a,before,after in m['emulatorOnlyHooks']}
    if len(actual)!=len(m['emulatorOnlyHooks']) or actual!=expected:raise ValueError('profile hook scope/target')
    if m['debugRuntimeIncluded']!=(profile=='test') or m['deploymentReady']:raise ValueError('offline profile state')
    if profile=='release' and any(x in m['symbols'] for x in ('nc_capture','as_process','na_config_bank','na_direction')):
        raise ValueError('release contains test runtime')
    return m

class AfOnlyContract(OriginalContract):
    def __init__(self,farm=None,nonce=1,*,profile=None):
        if profile not in ('release','test'):raise ValueError('explicit profile required')
        super().__init__(farm,nonce);self.profile=profile
        previous=self.identity;old_hooks={a for a,_,_ in self.offline['emulatorOnlyHooks']}
        folder=HERE/'build'/profile/'00800000';m=read(folder/'capture-manifest.json')
        self.offline=validate_manifest(m,(folder/'candidate.bin').read_bytes(),profile,self.farm)
        new_hooks={a for a,_,_ in m['emulatorOnlyHooks']}
        for a in old_hooks-new_hooks:self.allowed.pop(a,None)
        for a,factory,_ in m['emulatorOnlyHooks']:
            self.allowed[a]={factory}
            for q in range(a&~31,(a&~31)+32,4):self.expected[q]=self.farm.word(q)
            self.ranges.add((a&~31,32))
        self.allowed[old.DESC].update(a for a,_ in self.ranges)
        self.reads.update(self.expected);self.reads.update(self.allowed)
        if profile=='release':
            self.reads.update(range(0x2adc20,0x2adc44,4))
            self.reads.add(0x6bcb7c)
        self.identity=old.digest({'schema':'af-profile-r7','profile':profile,'originalContract':previous,
            'candidate':m['payload_sha256'],'sources':m['source_sha256'],
            'implementation':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    def bind(self,r,header,manifest,blob):
        if self.candidate is not None:raise ValueError('only one allocation may be bound')
        self.allocation_header_addresses(r)
        validate_manifest(manifest,blob,self.profile,self.farm)
        if header!=(0,r[10]|0x80000000) or manifest['base']!=r[9] or manifest['end']>r[9]+32768:
            raise ValueError('original allocator ownership/bounds')
        words=old.words(manifest['base'],blob)
        if set(words)&(set(self.expected)|set(self.allowed)):raise ValueError('payload overlaps fixed regions')
        symbols=manifest['symbols']
        ack=symbols['nc_capture']+28 if self.profile=='test' else symbols['af_install_ack']
        probe=symbols['nc_execution_probe'] if self.profile=='test' else symbols['af_install_probe']
        if words.get(ack)!=0 or not probe&1 or not manifest['base']<=(probe&~1)<manifest['state_start']:
            raise ValueError('profile execution probe/ACK')
        self.candidate=manifest;self.candidate_blob=blob;self.allocation=list(r);self.candidate_words=words
        self.allowed.update({a:{v} for a,v in words.items()})
        for a,_,new in manifest['emulatorOnlyHooks']:self.allowed[a].add(new)
        self.ranges.add((manifest['base'],len(blob)))
        self.allowed[old.DESC].add(manifest['base']);self.allowed[old.DESC+4].add(len(blob))
        self.exec_ack=ack;self.exec_probe=probe
        self.allowed[old.CB].add(probe);self.allowed[old.ARG].add(ack);self.reads.update(words)
