/* 只核验原厂驱动通道与本模块 marker。没有可选参数，也没有发射入口。 */
#include "rf_netlink_wire.h"
#include <sys/socket.h>
#include <linux/netlink.h>
#include <net/if.h>
#include <poll.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <time.h>

static long long now_ms(void) {
    struct timespec ts; if (clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    return (long long)ts.tv_sec*1000+ts.tv_nsec/1000000;
}
static int response(int fd,uint32_t seq,uint32_t port,uint16_t family,int operation,uint32_t *value) {
    uint8_t bytes[4096]; long long deadline=now_ms()+1200;
    while (now_ms()<deadline) {
        struct pollfd p={fd,POLLIN,0}; struct sockaddr_nl from;
        struct iovec iov={bytes,sizeof(bytes)}; struct msghdr mh;
        ssize_t n; size_t off=0;
        int wait=(int)(deadline-now_ms());
        if (wait<=0) break;
        if (poll(&p,1,wait)<=0) { if (errno==EINTR) continue; return -10; }
        memset(&mh,0,sizeof(mh)); memset(&from,0,sizeof(from));
        mh.msg_name=&from; mh.msg_namelen=sizeof(from); mh.msg_iov=&iov; mh.msg_iovlen=1;
        n=recvmsg(fd,&mh,0);
        if (n<0) { if (errno==EINTR || errno==EAGAIN) continue; return -11; }
        if ((mh.msg_flags&MSG_TRUNC) || from.nl_pid || from.nl_family!=AF_NETLINK) return -12;
        while (off<(size_t)n) {
            size_t len; int result; int32_t err=0;
            if ((size_t)n-off<16) return -13;
            len=rf_le32(bytes+off);
            if (len<16 || len>(size_t)n-off || rf_align4(len)>(size_t)n-off) return -14;
            result=rf_nl_one_reply(bytes+off,len,seq,port,family,operation,value,&err);
            if (result==RF_NL_DATA) return 0;
            if (result<0) { printf("reply-error=%d driver=%d\n",result,(int)err); return -15; }
            off+=rf_align4(len);
        }
    }
    return -16;
}
int main(void) {
    struct sockaddr_nl local,remote; socklen_t localSize=sizeof(local);
    uint8_t request[128]; uint32_t family=0,marker=0,port,index; size_t size;
    int fd=socket(AF_NETLINK,SOCK_RAW|SOCK_CLOEXEC,NETLINK_GENERIC),rc=0;
    if (fd<0) return 10;
    memset(&local,0,sizeof(local)); local.nl_family=AF_NETLINK;
    memset(&remote,0,sizeof(remote)); remote.nl_family=AF_NETLINK;
    if (bind(fd,(struct sockaddr *)&local,sizeof(local)) || getsockname(fd,(struct sockaddr *)&local,&localSize)) { rc=11; goto end; }
    port=local.nl_pid; index=if_nametoindex("wlp1s0");
    if (!index) { rc=12; goto end; }
    size=rf_nl_family_request(request,sizeof(request),1,port);
    if (!size || sendto(fd,request,size,0,(struct sockaddr *)&remote,sizeof(remote))!=(ssize_t)size) { rc=13; goto end; }
    rc=response(fd,1,port,16,RF_NL_FAMILY,&family); if (rc) goto end;
    size=rf_nl_register_request(request,sizeof(request),(uint16_t)family,2,port,index,0);
    if (!size || sendto(fd,request,size,0,(struct sockaddr *)&remote,sizeof(remote))!=(ssize_t)size) { rc=14; goto end; }
    rc=response(fd,2,port,(uint16_t)family,RF_NL_REGISTER,&marker); if (rc) goto end;
    printf("normal-driver-marker=0x%04x\n",(unsigned)marker);
    if (marker!=0x584e) rc=15;
end:
    close(fd); if (rc) printf("probe-failed=%d\n",rc);
    return rc ? 1 : 0;
}
