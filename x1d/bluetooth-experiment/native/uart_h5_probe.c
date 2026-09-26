#define _DEFAULT_SOURCE
#include "bt_hci.h"
#include <stdio.h>
#include <string.h>

/* 此入口仅含一个 H5 SYNC 包；不完成配置握手、不发 HCI 命令、不重传。 */
struct probe_io {
    void *context;
    int (*send)(void *, const unsigned char *, unsigned);
    int (*receive)(void *, unsigned char *);
};
struct outcome { const char *result; unsigned sent, received; struct bt_reply reply; };
static const unsigned char sync_packet[]={0xc0,0,0x2f,0,0xd0,1,0x7e,0xc0};
static const unsigned char sync_reply[]={0xc0,0,0x2f,0,0xd0,2,0x7d,0xc0};
static struct outcome exchange(struct probe_io *io) {
    struct outcome o={"write_failed",0,0,{0}};
    unsigned char bytes[8];unsigned used=0;
    int n=io->send(io->context,sync_packet,8);
    if(n>0)o.sent=(unsigned)n;
    if(n!=8){o.result="write_incomplete";return o;}
    while(o.received<32){
        unsigned char byte;
        n=io->receive(io->context,&byte);
        if(n<=0){o.result=n<0?"read_failed":(o.received?"incomplete_reply":"no_reply");return o;}
        o.received++;
        if(used==1 && byte==0xc0)continue;
        bytes[used++]=byte;
        if(bytes[0]!=0xc0){o.result="unconfirmed_reply";return o;}
        if(used<8)continue;
        o.result=!memcmp(bytes,sync_reply,8)?"h5_sync_response":
            (!memcmp(bytes,sync_packet,8)?"h5_peer_sync_request":"unconfirmed_reply");
        return o;
    }
    o.result="reply_limit";return o;
}
struct fake {const unsigned char *bytes;unsigned n,pos,calls;int short_write;};
static int fake_send(void *context,const unsigned char *bytes,unsigned n){
    struct fake *f=context;f->calls++;
    if(n!=8||memcmp(bytes,sync_packet,8))return -1;
    return f->short_write?3:8;
}
static int fake_receive(void *context,unsigned char *byte){
    struct fake *f=context;if(f->pos==f->n)return 0;
    *byte=f->bytes[f->pos++];return 1;
}
static int self_test(void){
    for(unsigned n=0;n<=8;n++){
        struct fake f={sync_reply,n,0,0,0};struct probe_io io={&f,fake_send,fake_receive};
        struct outcome o=exchange(&io);
        const char *want=n==8?"h5_sync_response":(n?"incomplete_reply":"no_reply");
        if(strcmp(o.result,want)||f.calls!=1||o.sent!=8||o.received!=n)return 1;
    }
    for(unsigned i=0;i<8;i++){
        unsigned char bad[8];memcpy(bad,sync_reply,8);bad[i]^=1;
        struct fake f={bad,8,0,0,0};struct probe_io io={&f,fake_send,fake_receive};
        struct outcome o=exchange(&io);
        if(strcmp(o.result,"unconfirmed_reply")||f.calls!=1)return 2;
    }
    struct fake f={sync_reply,8,0,0,1};struct probe_io io={&f,fake_send,fake_receive};
    struct outcome o=exchange(&io);
    if(strcmp(o.result,"write_incomplete")||f.calls!=1||o.received)return 3;
    f=(struct fake){sync_packet,8,0,0,0};o=exchange(&io);
    if(strcmp(o.result,"h5_peer_sync_request")||f.calls!=1)return 4;
    puts("uart_h5_self_test=passed;hardware_access=none");return 0;
}

#ifndef _WIN32
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <poll.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <dirent.h>
#include <stdlib.h>
#include <time.h>

static volatile sig_atomic_t stopped;
static void stop_signal(int sig) { (void)sig; stopped=1; }
static long long milliseconds(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    return (long long)ts.tv_sec*1000+ts.tv_nsec/1000000;
}
struct serial { int fd; long long deadline; };
static int serial_send(void *context,const unsigned char *bytes,unsigned n) {
    struct serial *s=context;
    if (stopped) return -1;
    return (int)write(s->fd,bytes,n); /* 不重发，短写也立即退出。 */
}
static int serial_receive(void *context,unsigned char *byte) {
    struct serial *s=context;
    while (!stopped) {
        long long now=milliseconds();
        if (now<0) return -1;
        int left=(int)(s->deadline-now);
        if (left<=0) return 0;
        struct pollfd p={s->fd,POLLIN,0};
        int n=poll(&p,1,left);
        if (n==0) return 0;
        if (n<0) { if (errno==EINTR) continue; return -1; }
        if (p.revents&(POLLERR|POLLHUP|POLLNVAL)) return -1;
        n=(int)read(s->fd,byte,1);
        if (n<0 && (errno==EAGAIN || errno==EINTR)) continue;
        return n==1 ? 1 : -1;
    }
    return -1;
}
static int other_owner(dev_t target) {
    DIR *proc=opendir("/proc"); struct dirent *p,*f; int found=0;
    if (!proc) return -1;
    while (!found && (p=readdir(proc))) {
        char *end; long pid=strtol(p->d_name,&end,10);
        if (*end || pid<=0 || pid==(long)getpid()) continue;
        char folder[96];
        if (snprintf(folder,sizeof(folder),"/proc/%ld/fd",pid)>=(int)sizeof(folder)) {found=-1;break;}
        DIR *fds=opendir(folder);
        if (!fds) { if (errno!=ENOENT && errno!=ESRCH) found=-1; continue; }
        while ((f=readdir(fds))) {
            char path[400]; struct stat st;
            if (f->d_name[0]=='.') continue;
            if (snprintf(path,sizeof(path),"%s/%s",folder,f->d_name)>=(int)sizeof(path)) {found=-1;break;}
            if (!stat(path,&st) && S_ISCHR(st.st_mode) && st.st_rdev==target) {found=1;break;}
        }
        closedir(fds);
    }
    closedir(proc); return found;
}
static int same_termios(const struct termios *a,const struct termios *b) {
    return a->c_iflag==b->c_iflag && a->c_oflag==b->c_oflag && a->c_cflag==b->c_cflag &&
        a->c_lflag==b->c_lflag && !memcmp(a->c_cc,b->c_cc,NCCS) &&
        cfgetispeed(a)==cfgetispeed(b) && cfgetospeed(a)==cfgetospeed(b);
}
static int live(int inspect) {
    struct stat st; struct termios saved,raw,after;
    struct outcome o={"preflight_failed",0,0,{0}};
    int fd=-1,exclusive=0,changed=0,restored=1,closed=1,queue=0,ldisc=-1,queue_clean=1;
    unsigned original_baud=0;
    signal(SIGINT,stop_signal); signal(SIGTERM,stop_signal); signal(SIGALRM,stop_signal);
    alarm(3);
    if (lstat("/dev/ttymxc4",&st) || !S_ISCHR(st.st_mode) || other_owner(st.st_rdev)!=0) goto done;
    fd=open("/dev/ttymxc4",O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);
    if (fd<0) {o.result="open_failed";goto done;}
    struct stat opened;
    if (fstat(fd,&opened) || !S_ISCHR(opened.st_mode) || opened.st_rdev!=st.st_rdev) goto done;
    if (ioctl(fd,TIOCEXCL)) {o.result="exclusive_failed";goto done;}
    exclusive=1;
    if (other_owner(st.st_rdev)!=0 || ioctl(fd,TIOCGETD,&ldisc) || ldisc!=0 || tcgetattr(fd,&saved)) goto done;
    original_baud=(unsigned)cfgetospeed(&saved);
    if (ioctl(fd,TIOCINQ,&queue) || queue!=0 || ioctl(fd,TIOCOUTQ,&queue) || queue!=0) {
        o.result="existing_serial_data";goto done;
    }
    if (inspect) {o.result="serial_inspected";goto done;}
    raw=saved;
    cfmakeraw(&raw);
    raw.c_cflag &= ~(PARENB|CSTOPB|CSIZE|CRTSCTS|HUPCL);
    raw.c_cflag |= CS8|CLOCAL|CREAD;
    raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
    if (cfsetispeed(&raw,B115200) || cfsetospeed(&raw,B115200)) goto done;
    changed=1;restored=0;
    if (tcsetattr(fd,TCSANOW,&raw)) {o.result="configure_failed";goto done;}
    if (tcgetattr(fd,&after) || !same_termios(&raw,&after)) {o.result="configure_mismatch";goto done;}
    /* 发现任何预先活动即停止；不消费或清空原有输入。 */
    struct pollfd p={fd,POLLIN,0};
    if (poll(&p,1,150)!=0 || stopped) {o.result="activity_before_query";goto done;}
    struct serial serial={fd,milliseconds()+1200};
    struct probe_io io={&serial,serial_send,serial_receive};
    o=exchange(&io);
done:
    if (fd>=0) {
        /* 此时队列在查询前已确认为空，只丢弃本轮可能尚未发出的字节。 */
        if (changed && o.sent) {
            if (ioctl(fd,TIOCOUTQ,&queue)) queue_clean=0;
            else if (queue>0 && tcflush(fd,TCOFLUSH)) queue_clean=0;
        }
        if (changed) restored=tcsetattr(fd,TCSANOW,&saved)==0 && tcgetattr(fd,&after)==0 && same_termios(&saved,&after) && queue_clean;
        if (exclusive && ioctl(fd,TIOCNXCL)) restored=0;
        if (close(fd)) closed=0;
    }
    alarm(0);
    /* 不记录原始串口数据、设备地址或名称。 */
    printf("result=%s;tx=%u;rx=%u;restored=%d;closed=%d;original_baud_code=%u",o.result,o.sent,o.received,restored,closed,original_baud);
    if (!strcmp(o.result,"hci_version_reply")) printf(";hci=%u;manufacturer=%u",o.reply.data[0],o.reply.data[4]|((unsigned)o.reply.data[5]<<8));
    puts("");
    return 0; /* 探测失败是有效结果，由主机报告判定；不得自动重发。 */
}
#endif

int main(int argc,char **argv) {
    if (argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
#ifndef _WIN32
    if (argc==2 && !strcmp(argv[1],"--inspect-uart5")) return live(1);
    if (argc==2 && !strcmp(argv[1],"--probe-uart5-h5-sync-once")) return live(0);
#endif
    fputs("explicit_fixed_uart_probe_required\n",stderr);return 2;
}
