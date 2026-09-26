"""执行候选 ARM provider/GL 检查/许可生命周期；设备、GL 驱动与同步为显式替身。"""
import ctypes as C
import json
from pathlib import Path
from run_provider import ProviderMachine, jpeg, marker, metadata, sha, TEXTURE_DELETE, FALLBACK
from arm_machine import HERE, X1D

CREATE="_ZNK12_GLOBAL__N_17Texture13createTextureEP12QQuickWindow"
GPU_DELETE="_ZN12_GLOBAL__N_18UploadedD0Ev"

class StableMachine(ProviderMachine):
    def __init__(self):
        self.gl_names={};self.gl_next=1;self.gl_error=0;self.reject_upload=False
        self.max_gpu=0;self.gl_binding=93;self.alignment=8;self.uploads=0;self.max_texture=8192
        self.cancel_on_decode=False
        super().__init__()
        self.context=self.allocate(16,True)
        self.hash_seed=self.allocate(4,True);self.uc.mem_write(self.hash_seed,b'0\0')
        self.refcount=self.allocate(12,True);self.put(self.refcount,1);self.put(self.refcount+4,0xffffffff)
        for name,fn in {
            "_ZN14QOpenGLContext14currentContextEv":lambda:self.ret(self.context),
            "_ZNK14QOpenGLContext7isValidEv":lambda:self.ret(1),
            "_ZNK14QOpenGLContext9functionsEv":lambda:self.ret(1),
            "_ZNK14QOpenGLContext12hasExtensionERK10QByteArray":lambda:self.ret(1),
            "_ZN14QOpenGLContext10areSharingEPS_S0_":lambda:self.ret(0),
            "_ZN15QtSharedPointer20ExternalRefCountData9getAndRefEPK7QObject":self.weak_ref,
            "_ZN10QSGTextureC2Ev":lambda:self.ret(self.arg(0)),
            "_ZN10QSGTextureD2Ev":lambda:self.ret(),
            "_ZN10QSGTexture17updateBindOptionsEb":lambda:self.ret(),
            "_ZNK10QSemaphore9availableEv":lambda:self.ret(self.permits),
        }.items():self.bind(name,fn)
        self.callbacks.update({"glGetIntegerv":self.gl_integer,"glGetError":self.get_error,"glGenTextures":self.gen,
            "glDeleteTextures":self.delete,"glBindTexture":self.bind_texture,"glPixelStorei":self.pixel_store,
            "glTexImage2D":self.upload,"glTexParameteri":lambda:self.ret(),"glFinish":lambda:self.ret()})
    def weak_ref(self):self.put(self.refcount,self.word(self.refcount)+1);self.ret(self.refcount)
    def gl_integer(self):
        self.put(self.arg(1),{0x0d33:self.max_texture,0x8069:self.gl_binding,0x0cf5:self.alignment}[self.arg(0)]);self.ret()
    def get_error(self):value=self.gl_error;self.gl_error=0;self.ret(value)
    def gen(self):
        assert self.arg(0)==1;self.put(self.arg(1),self.gl_next);self.gl_names[self.gl_next]=0;self.gl_next+=1;self.ret()
    def delete(self):
        assert self.arg(0)==1;del self.gl_names[self.word(self.arg(1))];self.ret()
    def bind_texture(self):assert self.arg(0)==0xde1;self.gl_binding=self.arg(1);self.ret()
    def pixel_store(self):assert self.arg(0)==0xcf5;self.alignment=self.arg(1);self.ret()
    def upload(self):
        assert [self.arg(i) for i in (0,1,2,5,6,7)]==[0xde1,0,0x80e1,0,0x80e1,0x1401]
        self.uploads+=1
        if self.reject_upload:self.gl_error=0x505
        else:self.gl_names[self.gl_binding]=self.arg(3)*self.arg(4)*4
        self.max_gpu=max(self.max_gpu,sum(self.gl_names.values()));self.ret()
    def select_files(self,data,record=None):
        if self.record:self.call("_ZN11QJsonObjectD1Ev",[self.record]);self.free(self.record)
        self.record=self.json_object(record) if record else None
        self.record_accepted=bool(record)
        self.files={"/card0/folder/a.jpg":data,"/card0/folder/a.3FR":b"RAW-MUST-NOT-BE-READ"}
    def request(self,kind="preview",source="/card0/folder/a.3FR"):
        return super().request(kind,source)
    def selected(self,source):
        value=self.qstring(source);self.call("_ZN3X1D16selectFullSourceERK7QString",[value]);self.drop_string(value)
    def observe_decode(self,uc,at,size,context):
        super().observe_decode(uc,at,size,context)
        if self.cancel_on_decode:
            # GUI 线程换源的时间点替身；运行中的 ARM 解码函数继续执行并检查取消。
            slot=self.native_symbols['_ZN12_GLOBAL__N_17currentE']
            old=self.word(slot);new=self.word(self.next_source)
            if self.word(old)!=0xffffffff:
                self.put(old,self.word(old)-1)
                if self.word(old)==0:self.free(old)
            self.put(new,self.word(new)+1);self.put(slot,new)
            self.cancel_on_decode=False
    def shim(self,uc,at,size,context):
        name=self.entries[at]
        if name=='getenv' and self.cstring(self.arg(0))=='QT_HASH_SEED':self.ret(self.hash_seed)
        elif name=="__aeabi_idiv":
            a,b=C.c_int32(self.arg(0)).value,C.c_int32(self.arg(1)).value
            self.ret(abs(a)//abs(b)*(-1 if (a<0)!=(b<0) else 1))
        elif name=="memchr":
            data=bytes(self.uc.mem_read(self.arg(0),self.arg(2)));idx=data.find(bytes([self.arg(1)&255]));self.ret(0 if idx<0 else self.arg(0)+idx)
        else:super().shim(uc,at,size,context)

def image(w=640,h=480,color=(65,110,160),orientation=1):
    main=jpeg((w,h),color)
    return main[:2]+marker(0xe1,b"Exif\0\0"+metadata(orientation,b"112233445566778899aabbccddeeff00"))+main[2:]

def run():
    m=StableMachine();cases=[]
    def done(name):cases.append(name);print(name,flush=True)
    data=image();m.select_files(data)
    texture,size=m.request();assert texture not in (0,FALLBACK) and size==(640,480),(texture,size)
    im=m.image_copy(texture);ptr=m.pixel_pointer(im);assert ptr
    assert not any('.3fr' in p.lower() for p,_,_ in m.reads)
    done('legacy-jpeg-without-completion-record-zero-raw-reads')
    m.drop_image(im);m.call(TEXTURE_DELETE,[texture])
    for i in range(24):
        m.select_files(image(color=(i*7%255,90,160)))
        texture,size=m.request('fullsize');assert texture not in (0,FALLBACK) and m.permits==0
        old=m.image_copy(texture);ptr=m.pixel_pointer(old)
        m.reject_upload=i%4==3
        gpu=m.call(CREATE,[texture,1]);assert bool(gpu)==(not m.reject_upload)
        assert m.gl_binding==93 and m.alignment==8
        after=m.image_copy(texture);assert m.pixel_pointer(after)==0;m.drop_image(after)
        m.call(TEXTURE_DELETE,[texture]);assert m.permits==0 and ptr in m.live
        m.drop_image(old)
        if gpu:
            assert m.permits==0
            count=len(m.fallback_calls);busy,_=m.request('fullsize');assert busy==0 and len(m.fallback_calls)==count
            m.call(GPU_DELETE,[gpu])
        assert m.permits==1 and not m.gl_names and ptr not in m.live
    done('24-switch-upload-failure-and-cpu-gpu-reference-release-cycles')
    m.reject_upload=False
    m.select_files(data[:-2]);assert m.request()[0]==0
    m.select_files(data);m.file_failure=lambda *a:True;assert m.request()[0]==0;m.file_failure=None
    assert not m.fallback_calls
    done('jpeg-truncation-and-storage-error-never-fall-through-to-raw')
    m.select_files(data,{'pending':True});reads=len(m.reads);assert m.request()[0]==0 and len(m.reads)==reads+1
    m.select_files(data,{'jpegPath':'/card1/folder/a.jpg','rawPath':'/card0/folder/a.3FR'});assert m.request()[0]==0
    done('pending-write-and-cross-card-record-conflict-rejected')
    m.select_files(data);m.selected('/card0/folder/new.3FR');reads=len(m.reads);assert m.request('fullsize')[0]==0 and len(m.reads)==reads
    m.selected('/card0/folder/a.3FR');m.fail_alloc_size=640*480*4;assert m.request('fullsize')[0]==0 and m.permits==1;m.fail_alloc_size=0
    done('stale-full-request-and-allocation-failure-release')
    m.next_source=m.qstring('/card0/folder/cancelled.3FR');m.cancel_on_decode=True
    assert m.request('fullsize')[0]==0 and m.permits==1
    m.drop_string(m.next_source);m.selected('/card0/folder/a.3FR')
    texture,size=m.request('fullsize');m.max_texture=256
    assert m.call(CREATE,[texture,1])==0 and m.permits==1 and not m.gl_names
    m.call(TEXTURE_DELETE,[texture]);m.max_texture=8192
    done('source-switch-during-codec-and-texture-limit-rejection-remain-bounded')
    print('running-full-jpeg-scaled-decode',flush=True)
    m.select_files(image(8176,6128));texture,size=m.request();assert size==(1022,766) and texture not in (0,FALLBACK),size
    im=m.image_copy(texture);ptr=m.pixel_pointer(im);assert m.live[ptr][0]==1022*766*4
    m.drop_image(im);m.call(TEXTURE_DELETE,[texture])
    done('8176x6128-jpeg-decodes-directly-to-1022x766')
    print('running-full-resolution-decode',flush=True)
    texture,size=m.request('fullsize');assert size==(8176,6128) and texture not in (0,FALLBACK)
    gpu=m.call(CREATE,[texture,1]);assert gpu and m.permits==0
    m.call(TEXTURE_DELETE,[texture]);assert m.permits==0
    m.call(GPU_DELETE,[gpu]);assert m.permits==1
    done('full-resolution-preserved-and-gpu-lifetime-holds-budget')
    m.call('_ZN12_GLOBAL__N_18ProviderD0Ev',[m.provider])
    assert not [n for n,_ in m.live.values() if n>=640*480*4]
    assert not any('.3fr' in p.lower() for p,_,_ in m.reads)
    report={'passed':True,'cases':cases,'cameraAccess':False,'gpuDriverExecuted':False,
      'realArm':['candidate provider/container/pixels/budget/checked upload','original Qt 5.5.1 QImage/JSON','original TurboJPEG'],
      'replaced':['Storage File replies and record lookup','libc/synchronization','QSGTexture base and QObject context lifetime boundary','GL functions'],
      'rawReadCount':0,'glUploads':m.uploads,'maximumMockGpuBytes':m.max_gpu,'moduleHashes':m.module_hashes,
      'sourceHashes':{str(p.relative_to(X1D.parent)).replace('\\','/'):sha(p.read_bytes()) for p in [Path(__file__),HERE/'CodeTests/run_provider.py',HERE/'CodeTests/arm_machine.py',*sorted((HERE/'native').glob('*'))] if p.is_file()}}
    out=HERE/'artifacts/stable-tests';out.mkdir(parents=True,exist_ok=True);(out/'provider.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'cases':len(cases),'rawReads':0}))
if __name__=='__main__':run()
