#include "boot_session.h"
#include "boot_batch.h"
#include "formal_install_hold.h"
#include <QtCore/qsavefile.h>
#include <QtCore/qfile.h>
#include <QtCore/qbytearray.h>
#include <QtCore/qelapsedtimer.h>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <cerrno>
#include <initializer_list>

namespace {
constexpr const char *latch="/run/hbl-four-module/boot-incomplete";
uint32_t word(const char *p) {
    const auto *b=reinterpret_cast<const unsigned char *>(p);
    return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);
}
void append(QByteArray &bytes,uint32_t value) {for(unsigned i=0;i<4;++i)bytes.append(char(value>>(8*i)));}
bool save(const char *path,const QByteArray &bytes) {
    QSaveFile f(QString::fromLatin1(path));
    return f.open(QIODevice::WriteOnly) && f.write(bytes)==bytes.size() && f.commit();
}
bool syncDirectory(const char *path) {
    int fd=open(path,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return false;
    bool ok=fsync(fd)==0;return close(fd)==0 && ok;
}
uint32_t checksum(const QByteArray &bytes) {
    uint32_t c=~0u;
    for(char ch:bytes) {c^=static_cast<unsigned char>(ch);for(unsigned i=0;i<8;++i)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}
    return ~c;
}
class RuntimeIO : public HblBootBatchIO {
    bool batchOn=false,batchEver=false;
    uint32_t nonce=0,sequence=0;
    bool stopped=false,inFlight=false;
    unsigned requests=0,writes=0;
    uint32_t address=0,value=0;
    uint32_t rawPointer=0,payloadBase=0,allocationBytes=0;
    QByteArray phase="waiting";
    QByteArray reason="none";
    bool recovering=false,factoryVerified=false;
    QElapsedTimer timer;
    unsigned guiPid;
    bool holdValid() {
        char data[128],extra;unsigned pid=0;unsigned long long deadline=0,pulse=0;
        return !holdReleased() && holdRead(holdPulsePath,data,sizeof(data)) &&
            sscanf(data,"HPI1 %u %llu %llu %c",&pid,&deadline,&pulse,&extra)==3 &&
            deadline==holdReadDeadline() && holdFresh(holdNow(),deadline,pulse,pid,guiPid);
    }
    bool exchange(QByteArray request,QByteArray *reply) {
        if(stopped)return false;
        if(requests>=32000){reason="request-limit";return stop();}
        if(timer.elapsed()>360000){reason="total-timeout";return stop();}
        if(!holdValid()){reason="hold-invalid";return stop();}
        ++requests;
        if(!hbl_boot_exchange(request,reply)){reason="transport-failed";return stop();}
        if(requests%128==0 && !saveStatus("loading")){reason="status-write";return stop();}
        return true;
    }
    bool stop() {stopped=true;return false;}
    bool batchExchange(uint32_t op,uint32_t base,const HblBootCompare *items,const uint32_t *words,size_t n) {
        if(stopped || !batchOn || !nonce || sequence==0xffffffffu || !n ||
           (op==1 && (!items || n>20)) || (op==2 && (!words || n>60)))return stop();
        QByteArray query=QByteArray::fromHex("f4000501"),reply;
        for(uint32_t v:{0x31424248u,nonce,sequence,op,uint32_t(n),base,0u})append(query,v);
        for(size_t i=0;i<n;++i) {
            if(op==1){append(query,items[i].address);append(query,items[i].value);append(query,items[i].mask);}
            else append(query,words[i]);
        }
        append(query,checksum(query));
        if(!exchange(query,&reply))return false;
        if(reply.size()!=9 || reply.left(4)!=QByteArray::fromHex("f5000105") ||
           word(reply.constData()+4)!=sequence || reply.at(8)!=0){reason="batch-reply-failed";return stop();}
        ++sequence;return true;
    }
public:
    explicit RuntimeIO(unsigned pid,bool recovery):recovering(recovery),guiPid(pid) {
        timer.start();int fd=open("/dev/urandom",O_RDONLY|O_CLOEXEC);
        if(fd>=0){if(::read(fd,&nonce,4)!=4)nonce=0;if(close(fd))nonce=0;}
    }
    bool needsAdapter() const override {return true;}
    bool batchesReady() const override {return batchOn;}
    uint32_t batchSession() const override {return nonce;}
    bool activateBatches(bool enabled) override {
        if(stopped || !nonce || enabled==batchOn || (enabled && batchEver))return stop();
        batchOn=enabled;if(enabled)batchEver=true;return true;
    }
    bool compareBatch(const HblBootCompare *items,size_t n) override {
        return batchExchange(1,0,items,nullptr,n);
    }
    bool uploadBatch(uint32_t base,const uint32_t *words,size_t n) override {
        if(!factoryVerified || !inFlight || address!=base || value!=n*4 ||
           (phase!="upload-af-owned-body" && phase!="upload-flash-body"))return stop();
        writes+=unsigned(n);
        return batchExchange(2,base,nullptr,words,n);
    }
    bool version() override {
        if(!nonce){reason="session-random-unavailable";return stop();}
        QByteArray reply;
        if(!exchange(QByteArray::fromHex("0d000501"),&reply))return false;
        if(reply.size()!=196 || reply.left(4)!=QByteArray::fromHex("0e000105"))return stop();
        const char *expected[]={"827fa74","c9bb91d","abad48d"};
        for(unsigned i=0;i<3;++i) {
            const QByteArray field=reply.mid(4+i*64,64);
            if(field.indexOf('\0')!=7 || field.left(7)!=expected[i])return stop();
        }
        return true;
    }
    bool read(uint32_t a,uint32_t *v) override {
        if(!v)return stop();
        QByteArray query=QByteArray::fromHex("f4000501"),reply;append(query,a);
        if(!exchange(query,&reply))return false;
        if(reply.size()!=9 || reply.left(4)!=QByteArray::fromHex("f5000105") || reply.at(8)!=0)return stop();
        *v=word(reply.constData()+4);return true;
    }
    bool write(uint32_t a,uint32_t v) override {
        if(!factoryVerified || !inFlight || a!=address || v!=value)return stop();
        QByteArray query=QByteArray::fromHex("f2000501"),reply;append(query,a);append(query,v);
        ++writes;
        if(!exchange(query,&reply))return false;
        if(reply.size()!=5 || reply.left(4)!=QByteArray::fromHex("f3000105") || reply.at(4)!=0)return stop();
        return true;
    }
    bool checkpoint(const char *text,uint32_t a,uint32_t v,bool pending) override {
        if(stopped || !text || (inFlight && pending))return stop();
        if(!std::strcmp(text,"factory-verified")) {
            if(writes || pending)return stop();
            if(recovering && (!save("/run/hbl-four-module/boot-recovery.status","factory-baseline-verified-before-writes\n") ||
                !syncDirectory("/run/hbl-four-module")))return stop();
            factoryVerified=true;
        }
        if(!std::strcmp(text,"allocation-owned")){rawPointer=a;payloadBase=v;}
        if(!std::strcmp(text,"allocation-block"))allocationBytes=a;
        phase=text;address=a;value=v;inFlight=pending;
        return saveStatus("loading") || stop();
    }
    bool pause(unsigned ms) override {return !stopped && hbl_boot_pause(ms);}
    bool saveStatus(const char *state) {
        const QByteArray text=QByteArray("state=")+state+" phase="+phase+
            " requests="+QByteArray::number(requests)+" writes="+QByteArray::number(writes)+
            " inFlight="+QByteArray::number(inFlight?1:0)+" address="+QByteArray::number(address,16)+
            " value="+QByteArray::number(value,16)+" raw="+QByteArray::number(rawPointer,16)+
            " heap="+QByteArray::number(payloadBase,16)+" block="+QByteArray::number(allocationBytes)+
            " elapsedMs="+QByteArray::number(timer.elapsed())+" reason="+reason+"\n";
        return save("/run/hbl-four-module/boot-loader.status",text);
    }
};
}

void hbl_boot_load_run() {
    unsigned guiPid=0;
    for(unsigned i=0;i<1800;++i) {
        char data[96],extra;
        if(holdRead("/run/hbl-four-module/load.request",data,sizeof(data)) &&
           sscanf(data,"HBL1 %u %c",&guiPid,&extra)==1 && guiPid)break;
        guiPid=0;
        if(!hbl_boot_pause(100))return;
    }
    if(!guiPid) {save("/run/hbl-four-module/boot-loader.status","state=blocked phase=load-request-missing\n");return;}
    // wrapper 已确认 data 挂载；此处不能因空路径而在根分区创建替代状态目录。
    if(!holdDirectorySafe("/run/hbl-four-module")) {
        save("/run/hbl-four-module/boot-loader.status","state=blocked phase=state-directory\n");return;
    }
    const int lock=open(latch,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    const char initial[]="boot installation not complete; automatic replay disabled\n";
    bool recovering=false,durable=false;
    if(lock<0) {
        save("/run/hbl-four-module/boot-loader.status","state=blocked phase=same-boot-incomplete\n");return;
    } else {
        durable=write(lock,initial,sizeof(initial)-1)==ssize_t(sizeof(initial)-1) && fsync(lock)==0;
        if(close(lock))durable=false;
    }
    if(!durable || !syncDirectory("/run/hbl-four-module")) {
        save("/run/hbl-four-module/boot-loader.status","state=blocked phase=latch-durability\n");return;
    }
    RuntimeIO io(guiPid,recovering);
    const bool ok=hbl_load_boot_modules_batch(io);
    if(!ok) {
        io.saveStatus("failed");
        QFile status(QStringLiteral("/run/hbl-four-module/boot-loader.status"));
        if(status.open(QIODevice::ReadOnly))save("/run/hbl-four-module/boot-failure.status",status.readAll());
        return;
    }
    if(!io.saveStatus("modules-verified"))return;
    QFile status(QStringLiteral("/run/hbl-four-module/boot-loader.status"));
    if(!status.open(QIODevice::ReadOnly) || !save("/run/hbl-four-module/boot-success.status",status.readAll()) ||
       unlink(latch) || !syncDirectory("/run/hbl-four-module")) {io.saveStatus("failed-final-record");return;}
    io.saveStatus("ready");
}

bool hbl_boot_is_batch_request(const QByteArray &q) {
    if(q.size()<36 || q.size()>276 || q.left(4)!=QByteArray::fromHex("f4000501"))return false;
    const char *p=q.constData();
    if(word(p+4)!=0x31424248u || !word(p+8) || word(p+12)==0xffffffffu || word(p+28))return false;
    const uint32_t op=word(p+16),n=word(p+20),base=word(p+24);
    if(!n || (op!=1 && op!=2) || (op==1 && (n>20 || base || q.size()!=int(36+12*n))) ||
       (op==2 && (n>60 || (base&3) || uint64_t(base)+n*4>0x100000000ull || q.size()!=int(36+4*n))))return false;
    return checksum(q.left(q.size()-4))==word(p+q.size()-4);
}
