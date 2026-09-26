#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
static int replacements=0,detached=0;
static void replaceOpened(const char *,int);
#define HBL_HOLD_STATE_DIR "/tmp/hbl-hold-race-20260923"
#define HBL_HOLD_READ_OPEN_HOOK replaceOpened
#include "boot_hold_guard.h"
static void put(const char *path,const char *text) {
 int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);
 if(fd<0 || write(fd,text,strlen(text))!=ssize_t(strlen(text)) || close(fd))_exit(91);
}
static void replaceOpened(const char *path,int fd) {
 if(!replacements || strcmp(path,holdPulsePath))return;
 --replacements;
 char text[128];snprintf(text,sizeof(text),"HPI1 %u %llu %llu\n",unsigned(getpid()),(unsigned long long)(holdReadDeadline()),(unsigned long long)holdNow());
 put(HBL_HOLD_STATE_DIR "/replacement",text);
 if(rename(HBL_HOLD_STATE_DIR "/replacement",path))_exit(92);
 uint32_t mode,uid,links;int64_t size;
 if(!holdFileMetadata(fd,mode,uid,links,size) || links!=0)_exit(93);
 ++detached; // The old reader rejects this exact inode (links != 1).
}
static int checks=0;
static void check(bool ok){++checks;if(!ok){printf("failed=%d\n",checks);_exit(94);}}
int main(){
 if(mkdir(holdStateDirectory,0700))return 90;
 char deadline[80];snprintf(deadline,sizeof(deadline),"HHD1 %llu\n",(unsigned long long)(holdNow()+60000));
 put(holdDeadlinePath,deadline);
 check(holdAtomicPulse(unsigned(getpid()),holdReadDeadline(),holdNow()));
 check(!bootHoldFailure(unsigned(getpid())));
 replacements=1;check(!bootHoldFailure(unsigned(getpid())));check(detached==1);
 replacements=3;check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-pulse-read"));check(detached==4);
 check(holdAtomicPulse(unsigned(getpid()),holdReadDeadline(),0));
 check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-ui-not-ready"));
 check(holdAtomicPulse(unsigned(getpid()),holdReadDeadline(),holdNow()-3000));
 check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-stale-pulse"));
 check(holdAtomicPulse(unsigned(getpid()),holdReadDeadline(),holdNow()));
 check(!strcmp(bootHoldFailure(unsigned(getpid()+1)),"hold-pid-mismatch"));
 check(!link(holdPulsePath,HBL_HOLD_STATE_DIR "/hardlink"));
 check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-pulse-read"));
 check(!unlink(HBL_HOLD_STATE_DIR "/hardlink"));
 check(!chmod(holdPulsePath,0644));check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-pulse-read"));
 check(!chmod(holdPulsePath,0600));
 put(holdReleasePath,"release\n");check(!strcmp(bootHoldFailure(unsigned(getpid())),"hold-released"));
 printf("passed=%d detached-inode-reproduced=%d business-requests=0\n",checks,detached);
 return 0;
}
#ifdef HBL_HOLD_SHARED_TEST
__attribute__((constructor)) static void runHoldTest(){int result=main();fflush(stdout);_exit(result);}
#endif
