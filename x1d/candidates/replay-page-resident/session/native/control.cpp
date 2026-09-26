// 固定 systemctl 命令白名单和 15 秒执行上限；仅 GUI 服务可变更。
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <errno.h>
#include <cstring>
#include <cstdlib>
static volatile sig_atomic_t interrupted=0;
static void cancel(int){interrupted=1;}
static bool eq(const char *a,const char *b){return !std::strcmp(a,b);}
static bool role(const char *p){return eq(p,"victory-gui")||eq(p,"msg2dbus-farm")||eq(p,"configstore")||eq(p,"jpeg-daemon")||eq(p,"storage-daemon");}
static bool allowed(int n,char **a){
    if(n==2 && eq(a[1],"daemon-reload"))return true;
    if(n==3 && eq(a[2],"victory-gui") && (eq(a[1],"start")||eq(a[1],"stop")||eq(a[1],"restart")))return true;
    if(n==4 && eq(a[1],"is-active") && eq(a[2],"--quiet") && role(a[3]))return true;
    return n==5 && eq(a[1],"show") && eq(a[2],"-p") && role(a[4]) &&
        (eq(a[3],"MainPID")||eq(a[3],"FragmentPath")||eq(a[3],"DropInPaths")||eq(a[3],"Environment"));
}
int main(int argc,char **argv){
    if(!allowed(argc,argv))return 59;
    const char *preload=std::getenv("LD_PRELOAD"),*libraries=std::getenv("LD_LIBRARY_PATH");
    if(getuid()!=0 || (preload && *preload) || (libraries && *libraries))return 60;
    signal(SIGTERM,cancel);signal(SIGINT,cancel);signal(SIGHUP,cancel);
    pid_t child=fork();if(child<0)return 61;
    if(child==0){
        if(setsid()<0)_exit(61);
        setenv("PATH","/usr/bin:/bin",1);setenv("LC_ALL","C",1);
        argv[0]=const_cast<char *>("systemctl");execvp(argv[0],argv);_exit(127);
    }
    for(unsigned tick=0;tick<150 && !interrupted;++tick){
        int state=0;pid_t done=waitpid(child,&state,WNOHANG);
        if(done==child)return WIFEXITED(state)?WEXITSTATUS(state):128+WTERMSIG(state);
        if(done<0 && errno!=EINTR)return 61;
        timespec delay={0,100000000};nanosleep(&delay,nullptr);
    }
    kill(-child,SIGTERM);kill(child,SIGTERM);
    timespec grace={0,200000000};nanosleep(&grace,nullptr);
    kill(-child,SIGKILL);kill(child,SIGKILL);
    // SIGKILL 后也不使用阻塞 wait；内核/服务异常不能拖住撤回入口。
    for(unsigned tick=0;tick<10;++tick){
        pid_t done=waitpid(child,nullptr,WNOHANG);
        if(done==child || (done<0 && errno!=EINTR))break;
        timespec reap={0,100000000};nanosleep(&reap,nullptr);
    }
    return interrupted?125:124;
}
