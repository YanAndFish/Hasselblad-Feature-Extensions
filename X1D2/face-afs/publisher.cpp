/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
// Bounded detector publisher. No camera commands, AF, shutter or service API.
#include "preview_resize.h"
#include "vendor/libfacedetection/facedetectcnn.h"
extern "C" {
#include "target_exchange.h"
#include "target_select.h"
#include "menu_control.h"
}
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static int clock_failed;
static void stop_requested(int) { stopping=1; }
static uint64_t now_ns()
{
    timespec t{};
    if(clock_gettime(CLOCK_MONOTONIC,&t)) { clock_failed=1;stopping=1;return 0; }
    return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;
}
static void pause_briefly()
{
    timespec t{0,10000000};nanosleep(&t,nullptr);
}

struct Mapping {
    int fd=-1;void *data=MAP_FAILED;size_t size=0;
    bool open_file(const char *path,size_t bytes)
    {
        fd=open(path,O_RDWR|O_NOFOLLOW);
        if(fd<0) return false;
        struct stat st{};
        if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() ||
           st.st_size!=(off_t)bytes || flock(fd,LOCK_EX|LOCK_NB)) return false;
        size=bytes;data=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
        return data!=MAP_FAILED;
    }
    ~Mapping() { if(data!=MAP_FAILED) munmap(data,size);if(fd>=0) close(fd); }
};

struct MenuControl {
    const char *intent=nullptr,*ack=nullptr;
    uint32_t revision=0;
    unsigned choice=EAF_MENU_AUTO,tick=0;
    bool valid=false;
    uint64_t next_heartbeat=0;
    uint32_t acknowledged_revision=0;
    unsigned acknowledged_choice=EAF_MENU_AUTO;
    bool acknowledged_valid=false;
    bool refresh(enum EafMode &mode,uint32_t &generation,EafTargetExchange *target)
    {
        if(!intent) return true;
        char record[EAF_MENU_BYTES+1];
        int fd=open(intent,O_RDONLY|O_NOFOLLOW);
        struct stat st{};
        bool owned=fd>=0 && !fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_uid==geteuid();
        ssize_t n=owned?read(fd,record,sizeof record):-1;
        if(fd>=0) close(fd);
        uint32_t incoming=0;unsigned selected=0;
        bool ok=n>=0 && eaf_menu_parse(record,(size_t)n,&incoming,&selected) &&
            incoming>=revision && (incoming!=revision || !valid || selected==choice);
        if(ok && (incoming!=revision || !valid || selected!=choice)) {
            revision=incoming;choice=selected;valid=true;
            mode=choice==EAF_MENU_FACE?EAF_FACE:EAF_ORDINARY;
            return eaf_target_publish(target,mode,++generation,nullptr);
        }
        if(!ok && (valid || mode!=EAF_ORDINARY)) {
            valid=false;choice=EAF_MENU_AUTO;mode=EAF_ORDINARY;
            return eaf_target_publish(target,mode,++generation,nullptr);
        }
        return true;
    }
    bool acknowledge(const EafTargetExchange *target,bool alive=true)
    {
        if(!ack) return true;
        uint64_t now=now_ns();
        if(alive && now<next_heartbeat && revision==acknowledged_revision &&
           choice==acknowledged_choice && valid==acknowledged_valid) return true;
        std::string temporary=std::string(ack)+".new";
        int fd=open(temporary.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
        if(fd<0) return false;
        EafRequestObservation observation{};
        bool observed=alive && eaf_observation_read(target,&observation) && observation.dispatch_count;
        uint64_t decision=((uint64_t)observation.decision_hi<<32)|observation.decision_lo;
        observed=observed && decision && now>=decision;
        char text[512];
        int n=std::snprintf(text,sizeof text,
            "{\"magic\":\"EAF_MENU_1\",\"revision\":%u,\"mode\":%u,\"tick\":%u,\"alive\":%s,"
            "\"request\":{\"valid\":%s,\"count\":%u,\"point\":%u,\"size\":%u,\"age_ms\":%.3f}}\n",
            revision,valid?choice:EAF_MENU_AUTO,++tick,alive?"true":"false",
            observed?"true":"false",observation.dispatch_count,observation.point,observation.size,
            observed?(now-decision)/1e6:0.);
        bool ok=n>0 && n<(int)sizeof text && write(fd,text,(size_t)n)==n;
        if(close(fd)) ok=false;
        if(ok && rename(temporary.c_str(),ack)==0) {
            next_heartbeat=now+100000000u;acknowledged_revision=revision;
            acknowledged_choice=choice;acknowledged_valid=valid;return true;
        }
        unlink(temporary.c_str());return false;
    }
};

int main(int argc,char **argv)
{
    if(argc!=7 && argc!=9) {
        std::fprintf(stderr,"Usage: %s FRAME.bin TARGET.bin face|eye SECONDS(1..30) "
            "unconfirmed|full-preview-confirmed image-left|image-right [MODE.txt ACK.json]\n",argv[0]);
        return 2;
    }
    std::string frame_path=argv[1],target_path=argv[2];
    auto slash=frame_path.rfind('/');
    if(slash==std::string::npos || target_path!=frame_path.substr(0,slash)+"/target.bin" ||
       frame_path.substr(slash)!="/frame.bin") return 2;
#if defined(__arm__) && defined(__linux__)
    std::string directory=frame_path.substr(0,slash);
    if(directory.size()!=25 || directory.compare(0,13,"/tmp/eye-afs-")) return 2;
    for(size_t i=13;i<directory.size();++i)
        if(!std::strchr("0123456789abcdef",directory[i])) return 2;
#endif
    MenuControl menu;
    bool service=!std::strcmp(argv[3],"menu-service");
    EafMode mode;
    if(!std::strcmp(argv[3],"face")) mode=EAF_FACE;
    else if(!std::strcmp(argv[3],"eye")) mode=EAF_EYE;
    else if((!std::strcmp(argv[3],"menu") || service) && argc==9) {
        mode=EAF_ORDINARY;menu.intent=argv[7];menu.ack=argv[8];
        if(std::string(menu.intent)!=frame_path.substr(0,slash)+"/mode.txt" ||
           std::string(menu.ack)!=frame_path.substr(0,slash)+"/mode-ack.json") return 2;
    }
    else return 2;
    if(argc==9 && !menu.intent) return 2;
    char *end=nullptr;errno=0;long seconds=std::strtol(argv[4],&end,10);
    if(errno || !*argv[4] || *end || (service ? seconds!=0 : (seconds<1 || seconds>(menu.intent?600:30)))) return 2;
    bool geometry=false;
    if(!std::strcmp(argv[5],"full-preview-confirmed")) geometry=true;
    else if(std::strcmp(argv[5],"unconfirmed")) return 2;
    unsigned eye=0;
    if(!std::strcmp(argv[6],"image-right")) eye=1;
    else if(std::strcmp(argv[6],"image-left")) return 2;
    Mapping frame_file,target_file;
    if(!frame_file.open_file(argv[1],sizeof(EafPreviewPacket)) ||
       !target_file.open_file(argv[2],sizeof(EafTargetExchange))) {
        std::perror("owned exchange file or exclusive writer lock");return 2;
    }
    auto *frame=static_cast<EafPreviewPacket *>(frame_file.data);
    auto *target=static_cast<EafTargetExchange *>(target_file.data);
    uint32_t initial_state=__atomic_load_n(&frame->state,__ATOMIC_ACQUIRE);
    if(frame->magic!=EAF_FRAME_MAGIC || initial_state>EAF_ERROR ||
       (!service && initial_state!=EAF_IDLE)) return 2;
    bool discard_inherited_frame=service && initial_state!=EAF_IDLE;
    uint32_t generation=1;
    if(!eaf_target_publish(target,mode,generation,nullptr)) return 2;
    std::signal(SIGTERM,stop_requested);std::signal(SIGINT,stop_requested);
    uint64_t begin=now_ns(),deadline=begin+(uint64_t)seconds*1000000000u;
    if(!begin) { eaf_target_publish(target,EAF_ORDINARY,++generation,nullptr);return 2; }
    std::vector<unsigned char> bgr(160*120*3);
    alignas(128) unsigned char detections[FACEDETECTION_RESULT_BUFFER_SIZE];
    EafRawFace faces[FACEDETECTION_RESULT_MAX_FACES];
    unsigned frames=0,invalid=0;
    int status=0;
    while(!stopping && (service || now_ns()<deadline) && (service || frames<(unsigned)seconds*10)) {
        if(!menu.refresh(mode,generation,target) || !menu.acknowledge(target)) { status=3;break; }
        if(menu.intent && mode==EAF_ORDINARY) {
            // AF-S and MF do no inference and request no new sensor frames.
            for(unsigned i=0;i<5 && !stopping && (service || now_ns()<deadline);++i) pause_briefly();
            continue;
        }
        if(discard_inherited_frame) {
            // A GUI/service restart may inherit one outstanding callback.
            // Drain it only after the tap releases ownership; never reset a
            // writer or turn the previous process's frame into fresh input.
            uint32_t inherited=__atomic_load_n(&frame->state,__ATOMIC_ACQUIRE);
            if(inherited==EAF_REQUEST || inherited==EAF_WRITING) { pause_briefly();continue; }
            if(inherited>EAF_ERROR) { status=3;break; }
            if(inherited==EAF_READY || inherited==EAF_ERROR)
                __atomic_store_n(&frame->state,EAF_IDLE,__ATOMIC_RELEASE);
            discard_inherited_frame=false;
        }
        uint32_t requested_generation=generation;
        uint64_t requested=now_ns();
        uint32_t idle=EAF_IDLE;
        if(!__atomic_compare_exchange_n(&frame->state,&idle,EAF_REQUEST,0,
                                       __ATOMIC_RELEASE,__ATOMIC_RELAXED)) { status=3;break; }
        bool timed_out=false;
        uint32_t state;
        do {
            if(!menu.refresh(mode,generation,target) || !menu.acknowledge(target)) { status=3;break; }
            state=__atomic_load_n(&frame->state,__ATOMIC_ACQUIRE);
            if(state==EAF_READY || state==EAF_ERROR) break;
            if(state!=EAF_REQUEST && state!=EAF_WRITING) { status=3;break; }
            if(!timed_out && now_ns()-requested>250000000u) {
                // Keep waiting for this same outstanding request, never resend.
                if(!eaf_target_publish(target,mode,service?generation:++generation,nullptr)) { status=3;break; }
                timed_out=true;
            }
            pause_briefly();
        } while(!stopping && (service || now_ns()<deadline));
        if(status || stopping || (!service && now_ns()>=deadline)) break;
        ++frames;
        uint64_t received=frame->callback_monotonic_ns,copy_end=frame->copy_end_monotonic_ns;
        uint64_t before=now_ns();
        // The tap timestamps only after acquiring this REQUEST. A packet
        // from an earlier request is not new input, even if under 250 ms old.
        bool earlier_callback=received<requested;
        int height=0;
        bool intent_changed=menu.intent && (mode!=EAF_FACE || generation!=requested_generation);
        bool valid=!intent_changed && state==EAF_READY && frame->width==1024 && frame->height==768 &&
            frame->stride==4096 && received && !earlier_callback &&
            copy_end>=received && before>=copy_end &&
            before-received<=250000000u && eaf_preview_to_bgr(frame,160,height,bgr) && height==120;
        uint64_t preprocessed=now_ns();
        // READY/ERROR owns no factory frame. Release only after copying pixels
        // into the small private BGR buffer; inference never runs in the tap.
        __atomic_store_n(&frame->state,EAF_IDLE,__ATOMIC_RELEASE);
        if(!valid) {
            ++invalid;
            if(!service && !earlier_callback && !intent_changed) geometry=false;
            // A resident worker discards transient AF/zoom frames without
            // destroying the calibrated full-view transform. The camera
            // consumer checks native photo/no-crop state and freezes only
            // before a real ImageLiveview -> AF transition.
            if(!eaf_target_publish(target,mode,service?generation:++generation,nullptr)) { status=3;break; }
            std::printf("{\"frame\":%u,\"rejected\":\"%s\",\"request_ns\":%llu,"
                "\"callback_ns\":%llu,\"pixels_seen_ns\":%llu}\n",frames,
                intent_changed?"menu_intent_changed":earlier_callback?"pre_request_callback":"invalid_preview",
                (unsigned long long)requested,(unsigned long long)received,(unsigned long long)before);
            std::fflush(stdout);
        } else {
            int *result=facedetect_cnn(detections,bgr.data(),160,120,480);
            uint64_t completed=now_ns();
            if(!menu.refresh(mode,generation,target) || !menu.acknowledge(target)) { status=3;break; }
            if(!result || *result<0 || *result>FACEDETECTION_RESULT_MAX_FACES) { status=3;break; }
            for(int i=0;i<*result;++i) {
                const short *r=reinterpret_cast<const short *>(detections+4)+FACEDETECTION_RESULT_STRIDE_SHORTS*i;
                faces[i]={r[0],r[1],r[2],r[3],r[4],{}};
                for(unsigned k=0;k<10;++k) faces[i].landmarks[k]=r[5+k];
            }
            EafTargetSnapshot selected=eaf_select_target(faces,(uint32_t)*result,received,generation,geometry,eye);
            bool fresh=completed>=received && completed-received<=250000000u;
            if(stopping || !fresh || (!service && completed>=deadline) ||
               (menu.intent && (mode!=EAF_FACE || generation!=requested_generation))) {
                if(!eaf_target_publish(target,mode,service?generation:++generation,nullptr)) { status=3;break; }
            } else if(!eaf_target_publish(target,mode,generation,&selected)) { status=3;break; }
            uint64_t publication_returned=now_ns();
            std::printf("{\"frame\":%u,\"raw_faces\":%d,\"qualified_faces\":%u,"
                "\"eye_usable\":%u,\"geometry_approved\":%u,\"face_point\":%u,\"eye_point\":%u,"
                "\"preprocess_ms\":%.3f,\"inference_ms\":%.3f,\"age_ms\":%.3f,\"fresh\":%s,"
                "\"request_ns\":%llu,\"callback_ns\":%llu,\"copy_end_ns\":%llu,"
                "\"pixels_seen_ns\":%llu,\"preprocess_done_ns\":%llu,"
                "\"inference_done_ns\":%llu,\"publication_return_ns\":%llu}\n",
                frames,*result,selected.face_count,selected.eye_usable,selected.geometry_confirmed,
                selected.face_point,selected.eye_point,(preprocessed-before)/1e6,
                (completed-preprocessed)/1e6,(completed-received)/1e6,fresh?"true":"false",
                (unsigned long long)requested,(unsigned long long)received,(unsigned long long)copy_end,
                (unsigned long long)before,(unsigned long long)preprocessed,
                (unsigned long long)completed,(unsigned long long)publication_returned);
            std::fflush(stdout);
        }
        // Cap requests at 10 Hz even on the faster host or on invalid input.
        while(!stopping && (service || now_ns()<deadline) && now_ns()-requested<100000000u) pause_briefly();
    }
    bool cleared=eaf_target_publish(target,EAF_ORDINARY,++generation,nullptr);
    if(!menu.acknowledge(target,false)) status=3;
    if(!cleared) status=3;
    else if(clock_failed) status=2;
    rusage usage{};bool usage_ok=getrusage(RUSAGE_SELF,&usage)==0;
#ifdef __APPLE__
    long rss=usage.ru_maxrss/1024;
#else
    long rss=usage.ru_maxrss;
#endif
    std::printf("{\"stopped\":true,\"frames\":%u,\"invalid_frames\":%u,\"status\":%d,"
                "\"peak_rss_kib\":",frames,invalid,status);
    if(usage_ok) std::printf("%ld",rss);else std::printf("null");
    std::printf(",\"target_cleared\":%s,\"af_requests\":0}\n",cleared?"true":"false");
    return status;
}
