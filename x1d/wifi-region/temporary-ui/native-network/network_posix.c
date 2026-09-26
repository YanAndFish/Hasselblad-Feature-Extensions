#define _GNU_SOURCE
#include "network_core.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define RUNTIME "/run/hbl-hotspot-ui"
#define CALLBACK RUNTIME "/dhcp-native"
static volatile sig_atomic_t cancelled;
static void interrupt(int signal_number){(void)signal_number;cancelled=1;}
static const char *const names[HBL_FILE_COUNT]={0,"band","infra","ap","up","started","wpa.conf","wpa.pid","wpa.start","bound","dns","client.sock"};
static char *const safe_environment[]={"PATH=/usr/sbin:/usr/bin:/sbin:/bin","LANG=C","LC_ALL=C",0};
typedef struct Runtime {
 int dir,radio_dir,callback,operation_lock,lease_lock,radio_lock;
 struct stat operation_identity,lease_identity,radio_identity;
 pid_t spawned;
 char spawned_start[32];
} Runtime;

static int secure(const struct stat *s,int directory){return s->st_uid==0&&!(s->st_mode&0022)&&(directory?S_ISDIR(s->st_mode):S_ISREG(s->st_mode))&&(directory||s->st_nlink==1);}
static uint64_t milliseconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;}
static void pause_ms(unsigned ms){struct timespec t={(time_t)(ms/1000),(long)(ms%1000)*1000000};while(nanosleep(&t,&t)&&errno==EINTR){}}
static int sleep_ms(void *unused,unsigned ms){(void)unused;if(cancelled)return 1;pause_ms(ms);return cancelled?1:0;}
static int read_fd(int fd,char *out,size_t cap,int binary){
 size_t used=0;if(cap<2)return -1;
 for(;;){ssize_t n=read(fd,out+used,cap-1-used);if(n<0){if(errno==EINTR)continue;return -1;}if(!n)break;used+=(size_t)n;
  if(used==cap-1){char extra;ssize_t more;do{more=read(fd,&extra,1);}while(more<0&&errno==EINTR);if(more)return -1;break;}}
 if(!binary&&memchr(out,0,used))return -1;out[used]=0;return (int)used;
}
static int read_at(int dir,const char *name,char *out,size_t cap,int binary,int guarded){
 int fd=openat(dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
 struct stat info;if(fstat(fd,&info)||(guarded&&!secure(&info,0))){close(fd);errno=EPERM;return -1;}
 int n=read_fd(fd,out,cap,binary);int error=errno;close(fd);errno=error;return n;
}
static int read_state(void *v,enum HblFile f,char *out,size_t cap){
 Runtime *r=v;if(f<0||f>=HBL_FILE_COUNT)return 1;
 if(f==HBL_DRIVER){
  int fd=open("/run/hbl-four-module/radio-mode",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);struct stat info;
  if(fd<0)return 1;if(fstat(fd,&info)||!secure(&info,1)){close(fd);return 1;}
  int n=read_at(fd,"driver",out,cap,0,1);close(fd);return n<0?1:0;
 }
 return read_at(r->dir,names[f],out,cap,0,1)<0?1:0;
}
static int presence(void *v,enum HblFile f){
 Runtime *r=v;struct stat info;if(f<=HBL_DRIVER||f>=HBL_FILE_COUNT)return -1;
 if(fstatat(r->dir,names[f],&info,AT_SYMLINK_NOFOLLOW))return errno==ENOENT?0:-1;
 return secure(&info,0)?1:-1;
}
static int write_all(int fd,const char *s,size_t n){while(n){ssize_t done=write(fd,s,n);if(done<0){if(errno==EINTR)continue;return 1;}if(!done)return 1;s+=done;n-=(size_t)done;}return 0;}
static int write_state(void *v,enum HblFile f,const char *value){
 Runtime *r=v;char tmp[64];struct stat info;
 if(cancelled||f<=HBL_DRIVER||f>=HBL_FILE_COUNT||f==HBL_CLIENT_SOCKET||!value||strlen(value)>8192)return 1;
 if(!fstatat(r->dir,names[f],&info,AT_SYMLINK_NOFOLLOW)){if(!secure(&info,0))return 1;}else if(errno!=ENOENT)return 1;
 snprintf(tmp,sizeof(tmp),".native-%ld-%d",(long)getpid(),(int)f);
 int fd=openat(r->dir,tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return 1;
 int bad=write_all(fd,value,strlen(value));if(close(fd))bad=1;
 if(!bad&&renameat(r->dir,tmp,r->dir,names[f]))bad=1;
 if(bad)unlinkat(r->dir,tmp,0);return bad;
}
static int remove_state(void *v,enum HblFile f){Runtime *r=v;if(f<=HBL_DRIVER||f>=HBL_FILE_COUNT)return 1;return unlinkat(r->dir,names[f],0)&&errno!=ENOENT?1:0;}
static int lock_at(int dir,const char *name,struct stat *identity){
 if(mkdirat(dir,name,0700))return 1;
 if(fstatat(dir,name,identity,AT_SYMLINK_NOFOLLOW)||!secure(identity,1)||(identity->st_mode&0777)!=0700){unlinkat(dir,name,AT_REMOVEDIR);return 1;}
 return 0;
}
static int unlock_at(int dir,const char *name,const struct stat *identity){
 struct stat now;if(fstatat(dir,name,&now,AT_SYMLINK_NOFOLLOW)||now.st_dev!=identity->st_dev||now.st_ino!=identity->st_ino||!secure(&now,1))return 1;
 return unlinkat(dir,name,AT_REMOVEDIR)?1:0;
}
static int lease_lock(void *v,int acquire){
 Runtime *r=v;if(acquire){if(r->lease_lock)return 0;if(lock_at(r->dir,"lease-native.lock",&r->lease_identity))return 1;r->lease_lock=1;return 0;}
 if(!r->lease_lock)return 0;int rc=unlock_at(r->dir,"lease-native.lock",&r->lease_identity);if(!rc)r->lease_lock=0;return rc;
}
static int finish(void *v){
 Runtime *r=v;int rc=lease_lock(r,0);
 if(r->operation_lock){if(unlock_at(r->dir,"network-native.lock",&r->operation_identity))rc=1;else r->operation_lock=0;}
 if(r->radio_lock){if(unlock_at(r->radio_dir,"lock",&r->radio_identity))rc=1;else r->radio_lock=0;}
 if(r->dir>=0){close(r->dir);r->dir=-1;}
 if(r->radio_dir>=0){close(r->radio_dir);r->radio_dir=-1;}return rc;
}
static int begin(void *v,int kind){
 Runtime *r=v;struct stat info;if(geteuid()!=0)return HBL_UNSAFE;
 r->callback=kind==HBL_CALLBACK;r->dir=open(RUNTIME,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(r->dir<0)return HBL_RUNTIME;
 if(fstat(r->dir,&info)||!secure(&info,1)){finish(r);return HBL_UNSAFE;}
 if(kind==HBL_RADIO_GUARDED){
  r->radio_dir=open("/run/hbl-four-module/radio-mode",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  if(r->radio_dir<0||fstat(r->radio_dir,&info)||!secure(&info,1)||(info.st_mode&0777)!=0700){finish(r);return HBL_UNSAFE;}
  if(lock_at(r->radio_dir,"lock",&r->radio_identity)){finish(r);return HBL_LOCKED;}r->radio_lock=1;
 }
 if(r->callback){if(lease_lock(r,1)){finish(r);return HBL_LOCKED;}}
 else {if(lock_at(r->dir,"network-native.lock",&r->operation_identity)){finish(r);return HBL_LOCKED;}r->operation_lock=1;}
 return 0;
}
static int log_file(Runtime *r,const char *name){
 struct stat info;int fd=openat(r->dir,name,O_WRONLY|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;if(fstat(fd,&info)||!secure(&info,0)||ftruncate(fd,0)){close(fd);return -1;}return fd;
}
static void child_exec(char *const argv[],int output,int error_fd,int own_group){
 if(own_group)setpgid(0,0);
 signal(SIGINT,SIG_DFL);signal(SIGTERM,SIG_DFL);signal(SIGHUP,SIG_DFL);
 int null=open("/dev/null",O_RDWR);if(null<0)_exit(126);
 if(dup2(null,STDIN_FILENO)<0||dup2(output>=0?output:null,STDOUT_FILENO)<0||dup2(output>=0?output:null,STDERR_FILENO)<0)_exit(126);
 if(null>2)close(null);if(output>2)close(output);
 execve(argv[0],argv,safe_environment);
 if(error_fd>=0){int failure=errno;(void)write(error_fd,&failure,sizeof(failure));}
 _exit(127);
}
static void reap_failed(pid_t pid,int group){
 if(pid<=1)return;kill(group?-pid:pid,SIGTERM);
 /* Keep a completed child as a zombie until its group has been terminated.
  * This reserves its PID/PGID while orphaned callbacks are cleaned up. */
 for(int n=0;n<50;n++){
  siginfo_t info={0};if(waitid(P_PID,(id_t)pid,&info,WEXITED|WNOHANG|WNOWAIT)&&errno==ECHILD)return;
  if(!group&&info.si_pid==pid)break;pause_ms(10);
 }
 kill(group?-pid:pid,SIGKILL);while(waitpid(pid,0,0)<0&&errno==EINTR){}
}
static int run(Runtime *r,char *const argv[],char *out,size_t cap,int log,unsigned timeout){
 if(cancelled)return 125;int pipes[2]={-1,-1};size_t used=0;if(out){if(cap<2||pipe2(pipes,O_CLOEXEC))return 125;out[0]=0;}
 pid_t pid=fork();if(pid<0){if(out){close(pipes[0]);close(pipes[1]);}return 125;}
 const int group=!r->callback;
 if(!pid){if(out)close(pipes[0]);child_exec(argv,out?pipes[1]:log,-1,group);}
 if(group)setpgid(pid,pid);
 if(out){close(pipes[1]);fcntl(pipes[0],F_SETFL,O_NONBLOCK);}
 uint64_t end=milliseconds()+timeout;int exit_code=125,done=0,bad=0;
 while(!done){
  if(out){for(;;){char buffer[512];ssize_t n=read(pipes[0],buffer,sizeof(buffer));if(n<=0){if(n<0&&errno!=EAGAIN&&errno!=EINTR)bad=1;break;}if(used+(size_t)n>=cap){bad=1;break;}memcpy(out+used,buffer,(size_t)n);used+=(size_t)n;out[used]=0;}}
  siginfo_t info={0};int waited=waitid(P_PID,(id_t)pid,&info,WEXITED|WNOHANG|WNOWAIT);
  if(!waited&&info.si_pid==pid){done=1;exit_code=info.si_code==CLD_EXITED?info.si_status:125;}
  else if(waited<0&&errno!=EINTR){bad=1;break;}
  if(cancelled||milliseconds()>=end)bad=1;if(bad)break;if(!done)pause_ms(10);
 }
 if(out){if(done&&!bad){for(;;){ssize_t n=read(pipes[0],out+used,cap-1-used);if(n<=0)break;used+=(size_t)n;if(used==cap-1){char extra;if(read(pipes[0],&extra,1)>0)bad=1;break;}}out[used]=0;}close(pipes[0]);}
 if(bad||(!strcmp(argv[0],"/sbin/udhcpc")&&group))reap_failed(pid,group);
 else if(done)while(waitpid(pid,0,0)<0&&errno==EINTR){}
 if(bad||!done)return 125;return exit_code;
}
static int process(pid_t pid,char *state,char start[32],int check_args){
 char path[64],data[2048];snprintf(path,sizeof(path),"/proc/%ld",(long)pid);
 int dir=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(dir<0)return errno==ENOENT?0:-1;
 struct stat info;if(fstat(dir,&info)||info.st_uid!=0){close(dir);return -1;}
 int n=read_at(dir,"stat",data,sizeof(data),0,0);
 if(n<0||!hbl_proc_stat(data,(int)pid,state,start,32)){close(dir);return -1;}
 if(*state!='Z'&&check_args){n=read_at(dir,"cmdline",data,sizeof(data),1,0);if(n<0||!hbl_wpa_argv(data,(size_t)n)){close(dir);return -1;}}
 close(dir);return 1;
}
static int owned_pid(Runtime *r,pid_t *pid,char stamp[32]){
 char text[64];int n=presence(r,HBL_WPA_PID);if(n<0)return -1;
 if(!n){if(r->spawned>1){*pid=r->spawned;strcpy(stamp,r->spawned_start);return 1;}return 0;}
 int value;if(read_state(r,HBL_WPA_PID,text,sizeof(text))||!hbl_pid(text,&value))return -1;*pid=(pid_t)value;
 n=presence(r,HBL_WPA_STAMP);if(n<0)return -1;stamp[0]=0;
 if(n){if(read_state(r,HBL_WPA_STAMP,stamp,32)||!stamp[0])return -1;for(const char *p=stamp;*p;p++)if(*p<'0'||*p>'9')return -1;}
 return 1;
}
static int probe_wpa(void *unused,int pid,int arguments,char *state,char start[32]){(void)unused;waitpid((pid_t)pid,0,WNOHANG);return process((pid_t)pid,state,start,arguments);}
static int terminate_wpa(void *unused,int pid){(void)unused;return kill((pid_t)pid,SIGTERM)&&errno!=ESRCH?1:0;}
static void pause_wpa(void *unused,unsigned ms){(void)unused;pause_ms(ms);}
static int stop_wpa(Runtime *r){
 pid_t pid=0;char expected[32];int found=owned_pid(r,&pid,expected);if(found<=0)return found?1:0;
 /* Old kernel has no pidfd. The shared, mock-tested policy verifies argv and
  * starttime twice and never escalates an adopted daemon to SIGKILL. */
 HblWpaProcess io={r,probe_wpa,terminate_wpa,pause_wpa};return hbl_stop_wpa(&io,(int)pid,expected);
}
static int start_wpa(Runtime *r){
 int log=log_file(r,"wpa.log"),ack[2];if(log<0)return 1;if(pipe2(ack,O_CLOEXEC)){close(log);return 1;}
 char *const args[]={"/usr/sbin/wpa_supplicant","-D","nl80211","-i","wlp1s0","-c",RUNTIME "/wpa.conf",0};
 pid_t pid=fork();if(pid<0){close(log);close(ack[0]);close(ack[1]);return 1;}
 if(!pid){close(ack[0]);child_exec(args,log,ack[1],1);}
 setpgid(pid,pid);r->spawned=pid;r->spawned_start[0]=0;close(log);close(ack[1]);
 struct pollfd p={ack[0],POLLIN|POLLHUP,0};int ready;do{ready=poll(&p,1,5000);}while(ready<0&&errno==EINTR&&!cancelled);
 int error=0;ssize_t count=ready>0?read(ack[0],&error,sizeof(error)):-1;close(ack[0]);
 if(count!=0||cancelled){reap_failed(pid,1);r->spawned=0;return 1;}
 char state;if(process(pid,&state,r->spawned_start,1)!=1||state=='Z'){reap_failed(pid,1);r->spawned=0;return 1;}
 char text[32];snprintf(text,sizeof(text),"%ld\n",(long)pid);
 if(write_state(r,HBL_WPA_STAMP,r->spawned_start)||write_state(r,HBL_WPA_PID,text))return 1;
 return 0;
}
static int wpa_ready(Runtime *r){
 pid_t pid;char expected[32],actual[32],state;int owned=owned_pid(r,&pid,expected);if(owned!=1)return -1;
 int live=process(pid,&state,actual,1);if(live!=1||state=='Z'||(expected[0]&&strcmp(expected,actual)))return -1;
 int dir=openat(r->dir,"ctrl",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(dir<0)return errno==ENOENT?1:-1;
 struct stat info;if(fstat(dir,&info)||!secure(&info,1)){close(dir);return -1;}
 int rc=fstatat(dir,"wlp1s0",&info,AT_SYMLINK_NOFOLLOW);close(dir);
 if(rc)return errno==ENOENT?1:-1;return S_ISSOCK(info.st_mode)&&info.st_uid==0?0:-1;
}
static int dhcp(Runtime *r){
 int fd=openat(r->dir,"dhcp-native",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return 1;
 struct stat info;char magic[4];int good=!fstat(fd,&info)&&secure(&info,0)&&read(fd,magic,4)==4&&!memcmp(magic,"\177ELF",4)&&!fchmod(fd,0700);close(fd);if(!good)return 1;
 int log=log_file(r,"dhcp.log");if(log<0)return 1;
 char *const args[]={"/sbin/udhcpc","-f","-n","-q","-t","3","-T","2","-i","wlp1s0","-s",CALLBACK,0};
 int rc=run(r,args,0,0,log,25000);close(log);return rc;
}
static int execute(void *v,enum HblCommand c,const char *a,const char *b,char *out,size_t cap){
 Runtime *r=v;char *args[20]={0};unsigned timeout=5000;
 switch(c){
 case HBL_NM_ACTIVE:case HBL_AP_ACTIVE:args[0]="/bin/systemctl";args[1]="is-active";args[2]="--quiet";args[3]=c==HBL_NM_ACTIVE?"network-manager":"hostapd";break;
 case HBL_WIFI_POWER:args[0]="/usr/bin/dbus-send";args[1]="--system";args[2]="--print-reply";args[3]="--reply-timeout=2000";args[4]="--dest=com.hasselblad.config";args[5]="/config";args[6]="org.freedesktop.DBus.Properties.Get";args[7]="string:com.hasselblad.config";args[8]="string:WIFI_power";break;
 case HBL_IPV4_STATE:args[0]="/sbin/ip";args[1]="-4";args[2]="addr";args[3]="show";args[4]="dev";args[5]="wlp1s0";break;
 case HBL_FLUSH:args[0]="/sbin/ip";args[1]="addr";args[2]="flush";args[3]="dev";args[4]="wlp1s0";break;
 case HBL_IFCONFIG:if(!hbl_ipv4(a,0)||!hbl_ipv4(b,0))return 1;args[0]="/sbin/ifconfig";args[1]="wlp1s0";args[2]=(char*)a;args[3]="netmask";args[4]=(char*)b;args[5]="up";break;
 case HBL_ROUTE:if(!hbl_ipv4(a,0))return 1;args[0]="/sbin/route";args[1]="add";args[2]="default";args[3]="gw";args[4]=(char*)a;args[5]="dev";args[6]="wlp1s0";break;
 case HBL_WPA_START:return start_wpa(r);
 case HBL_WPA_STOP:return stop_wpa(r);
 case HBL_WPA_READY:return wpa_ready(r);
 case HBL_DHCP:return dhcp(r);
 default:
  args[0]="/usr/bin/wl";
  switch(c){
  case HBL_READ_BAND:args[1]="band";break;case HBL_READ_INFRA:args[1]="infra";break;case HBL_READ_AP:args[1]="ap";break;case HBL_READ_UP:args[1]="isup";break;
  case HBL_DOWN:args[1]="down";break;case HBL_UP_RADIO:args[1]="up";break;
  case HBL_SET_BAND:if(!a||(strcmp(a,"auto")&&strcmp(a,"a")&&strcmp(a,"b")))return 1;args[1]="band";args[2]=(char*)a;break;
  case HBL_SET_AP:case HBL_SET_INFRA:if(!a||(strcmp(a,"0")&&strcmp(a,"1")))return 1;args[1]=c==HBL_SET_AP?"ap":"infra";args[2]=(char*)a;break;
  case HBL_SCAN_ENABLE:args[1]="scansuppress";args[2]="0";break;
  default:return 1;
  }break;
 }
 return run(r,args,out,cap,-1,timeout);
}
int main(int argc,char **argv){
 Runtime r={0};r.dir=r.radio_dir=-1;
 HblNetworkIO io={&r,begin,lease_lock,finish,read_state,write_state,presence,remove_state,execute,sleep_ms};
 struct sigaction action={0};action.sa_handler=interrupt;sigemptyset(&action.sa_mask);
 sigaction(SIGTERM,&action,0);sigaction(SIGINT,&action,0);sigaction(SIGHUP,&action,0);umask(077);
#ifdef HBL_DHCP_MAIN
 const char *event=hbl_dhcp_event(argc,argv);if(!event)return HBL_ARGUMENT;
 if(geteuid()!=0)return HBL_UNSAFE;
 HblLease lease={getenv("interface"),getenv("ip"),getenv("subnet"),getenv("router"),getenv("dns")};
 return hbl_dhcp_run(&io,event,&lease);
#else
 const char *op=hbl_network_operation(argc,argv);return op?hbl_network_run(&io,op):HBL_ARGUMENT;
#endif
}
