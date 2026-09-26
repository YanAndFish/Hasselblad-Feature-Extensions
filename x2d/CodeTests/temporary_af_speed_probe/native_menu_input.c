/* X2D 4.2.0: dedicated --version host, one persistent input/DBus connection.
 * Main GUI is read-only here. Only the verified owned preview mailbox is written.
 * No focus, capture, RF, credentials, global preload or input-device grab. */
typedef unsigned long U;
extern int open(const char *, int, ...), close(int), poll(void *, U, int);
extern long read(int, void *, U), write(int, const void *, U), pread(int, void *, U, long), pwrite(int, const void *, U, long);
extern int access(const char *, int), snprintf(char *, U, const char *, ...), clock_gettime(int, void *);
extern char *getenv(const char *);
extern int unsetenv(const char *);
extern void _exit(int) __attribute__((noreturn));
extern void *dbus_bus_get_private(int, void *);
extern void dbus_connection_set_exit_on_disconnect(void *, int), dbus_connection_close(void *), dbus_connection_unref(void *);
extern int dbus_connection_get_is_connected(void *);
extern void *dbus_message_new_method_call(const char *, const char *, const char *, const char *);
extern int dbus_message_append_args(void *, int, ...), dbus_message_get_type(void *);
extern void *dbus_connection_send_with_reply_and_block(void *, void *, int, void *);
extern void dbus_message_unref(void *);
extern int dbus_message_iter_init(void *, void *), dbus_message_iter_get_arg_type(void *);
extern void dbus_message_iter_recurse(void *, void *), dbus_message_iter_get_basic(void *, void *);

#define DIR "/tmp/x2d-preview/"
#define RO 0xA0000
#define RW 0xA0002
struct Times { long s, ns; };
struct PollFd { int fd; short events, revents; };
struct Event { long s, us; unsigned short type, code; int value; };
struct Config { U gp, gs, pp, ps, mailbox, visible, mapaddr, map, key, mods, function; };
static struct Config cfg;
static int pagefd=-1, guifd=-1, inputfd=-1, logfd=-1, exitfd=-1;
static void *bus;
static unsigned toggles;
static int shown;
static U pending_at;
static void check_exit_request(void);
static U now_ms(void) { struct Times t; if(clock_gettime(1,&t)) return 0; return (U)t.s*1000+(U)t.ns/1000000; }
static int equal(const char *a,const char *b) { if(!a||!b)return 0; while(*a&&*a==*b){a++;b++;}return *a==*b; }
static int contains(const char *a,const char *b) { for(;*a;a++){const char*x=a,*y=b;while(*x&&*y&&*x==*y){x++;y++;}if(!*y)return 1;}return 0; }
static long textfile(const char *path,char *buf,U cap) {
 int f=open(path,RO); if(f<0)return -1;long n=read(f,buf,cap-1);close(f);
 if(n<0||n==(long)cap-1)return -1;buf[n]=0;return n;
}
static int number(const char *s,U *out) {
 U n=0; if(!*s)return 0; for(;*s;s++){if(*s<'0'||*s>'9'||n>((U)-1-9)/10)return 0;n=n*10+*s-'0';}*out=n;return 1;
}
static int config(void) {
 char b[2048];if(textfile(DIR "native-state",b,sizeof b)<0)return 0;
 U *fields[]={&cfg.gp,&cfg.gs,&cfg.pp,&cfg.ps,&cfg.mailbox,&cfg.visible,&cfg.mapaddr,&cfg.map,&cfg.key,&cfg.mods,&cfg.function};
 const char *keys[]={"gui_pid","gui_start","page_pid","page_start","mailbox","visible_address","map_pointer_address","map_pointer","key_address","modifiers_address","function_address"};
 unsigned seen=0;char *p=b;
 while(*p){char *line=p;while(*p&&*p!='\n')p++;if(*p)*p++=0;char *v=line;while(*v&&*v!='=')v++;if(!*v)return 0;*v++=0;
  unsigned i;for(i=0;i<11;i++)if(equal(line,keys[i])){if(seen&(1u<<i)||!number(v,fields[i]))return 0;seen|=1u<<i;break;}if(i==11)return 0;
 }
 if(seen!=2047||!cfg.gp||cfg.gp>4194304||!cfg.pp||cfg.pp>4194304||cfg.gp==cfg.pp||!cfg.gs||!cfg.ps)return 0;
 for(unsigned i=4;i<11;i++)if(*fields[i]<4096||*fields[i]>=((U)1<<48))return 0;
 return 1;
}
static int identity(U pid,U expected) {
 char path[80],b[2048];snprintf(path,sizeof path,"/proc/%lu/stat",pid);if(textfile(path,b,sizeof b)<0)return 0;
 char *p=b,*last=0;for(;*p;p++)if(*p==')')last=p;if(!last||last[1]!=' ')return 0;p=last+2;
 for(int i=0;i<19;i++){while(*p&&*p!=' ')p++;if(!*p)return 0;p++;}
 char *end=p;while(*end&&*end!=' ')end++;*end=0;U start=0;return number(p,&start)&&start==expected;
}
static int rd(int f,U addr,void *p,U n) { return pread(f,p,n,(long)addr)==(long)n; }
static int guards(void) {
 U pointer=0;unsigned key=0,mods=1;unsigned char fn=255;
 return identity(cfg.gp,cfg.gs)&&identity(cfg.pp,cfg.ps)&&
 rd(guifd,cfg.mapaddr,&pointer,8)&&pointer==cfg.map&&rd(guifd,cfg.key,&key,4)&&key==70&&
 rd(guifd,cfg.mods,&mods,4)&&mods==0&&rd(guifd,cfg.function,&fn,1)&&fn==0;
}
static void logevent(const char *what,long value) {
 char b[192];int n=snprintf(b,sizeof b,"%lu %s %ld\n",now_ms(),what,value);
 if(logfd>=0&&n>0&&n<(int)sizeof b)write(logfd,b,(U)n);
}
static int connect_bus(void) {
 if(bus&&dbus_connection_get_is_connected(bus))return 1;
 if(bus){dbus_connection_close(bus);dbus_connection_unref(bus);bus=0;}
 bus=dbus_bus_get_private(1,0);if(!bus)return 0;dbus_connection_set_exit_on_disconnect(bus,0);return 1;
}
static int get_value(const char *property,int *value) {
 if(!connect_bus())return 0;
 const char *iface="com.hasselblad.camera";
 void *m=dbus_message_new_method_call(iface,"/camera","org.freedesktop.DBus.Properties","Get");if(!m)return 0;
 if(!dbus_message_append_args(m,'s',&iface,'s',&property,0)){dbus_message_unref(m);return 0;}
 void *r=dbus_connection_send_with_reply_and_block(bus,m,300,0);dbus_message_unref(m);if(!r)return 0;
 // Iterators are opaque, aligned storage larger than DBusMessageIter on AArch64.
 U outer[16]={0},inner[16]={0};int ok=0;
 if(dbus_message_get_type(r)==2&&dbus_message_iter_init(r,outer)&&dbus_message_iter_get_arg_type(outer)=='v'){
  dbus_message_iter_recurse(outer,inner);if(dbus_message_iter_get_arg_type(inner)=='i'){dbus_message_iter_get_basic(inner,value);ok=1;}
 }
 dbus_message_unref(r);return ok;
}
static int stop_liveview(void) {
 if(!connect_bus())return 0;
 void*m=dbus_message_new_method_call("com.hasselblad.camera","/camera","com.hasselblad.camera","set_live_view");if(!m)return 0;
 unsigned off=0;if(!dbus_message_append_args(m,'b',&off,0)){dbus_message_unref(m);return 0;}
 void*r=dbus_connection_send_with_reply_and_block(bus,m,1000,0);dbus_message_unref(m);
 if(!r)return 0;int ok=dbus_message_get_type(r)==2;dbus_message_unref(r);return ok;
}
/* Shared state decision is also exercised against the compiled ARM64 function. */
__attribute__((visibility("default"))) int menu_decide(int visible,int lv,int exposure) {
 if(visible)return 2; // hide only; never resume liveview
 if(exposure!=0&&exposure!=512)return 0;
 if(lv==0)return 1;
 if(lv==1)return 3;
 return 0;
}
static int request_visible(int value) {
 if(!guards())return 0;unsigned char b=(unsigned char)value;
 if(pwrite(pagefd,&b,1,(long)cfg.mailbox)!=1)return 0;
 shown=value;pending_at=now_ms();logevent(value?"SHOW_REQUEST":"HIDE_REQUEST",(long)toggles);return 1;
}
static void save_events(void) {
 int f=open(DIR "events",0xA0241,0600);if(f<0)return;
 char b[128];int n=snprintf(b,sizeof b,"visible_request=%d\ntoggles=%u\n",shown,toggles);if(n>0)write(f,b,(U)n);close(f);
}
static void check_exit_request(void) {
 static const char marker[]="X2D_MENU_EXIT_REQUEST";
 static unsigned matched;
 if(exitfd<0)return;
 char b[1024];long n=read(exitfd,b,sizeof b);
 for(long i=0;i<n;i++){
  if(b[i]==marker[matched])matched++;else matched=b[i]==marker[0]?1:0;
  if(matched==sizeof(marker)-1){matched=0;if(shown&&request_visible(0))save_events();}
 }
}
static void front_key(void) {
 U begin=now_ms();int lv=0,exposure=0;
 if(!guards()){logevent("IDENTITY_CHANGED",0);return;}
 if(!shown&&(!get_value("live_view_state",&lv)||!get_value("exposure_status",&exposure))){logevent("QUERY_UNAVAILABLE",0);return;}
 int action=menu_decide(shown,lv,exposure);
 if(action==1||action==2){toggles++;if(!request_visible(action==1))logevent("VISIBILITY_WRITE_FAILED",0);save_events();}
 else if(action==3){int ok=stop_liveview();logevent("PARAMETER_REQUEST",ok);toggles++;save_events();}
 else logevent("FRONT_SKIPPED_TRANSITION",lv);
 logevent("FRONT_HANDLER_MS",(long)(now_ms()-begin));
}
static int host_ok(void) {
 char b[256];long n=textfile("/proc/self/cmdline",b,sizeof b);
 static const char expected[]="/system/bin/camera-test\0--version";
 if(n!=(long)sizeof expected)return 0;for(U i=0;i<sizeof expected;i++)if(b[i]!=expected[i])return 0;return 1;
}
static int open_guarded(int inspect) {
 if(!config()||!identity(cfg.gp,cfg.gs)||!identity(cfg.pp,cfg.ps))return 0;
 char path[80],cmd[512];snprintf(path,sizeof path,"/proc/%lu/cmdline",cfg.gp);
 static const char gui[]="/system/bin/camera-gui\0-platform\0wayland-egl\0--fullscreen";
 long n=textfile(path,cmd,sizeof cmd);if(n!=(long)sizeof gui)return 0;for(U i=0;i<sizeof gui;i++)if(cmd[i]!=gui[i])return 0;
 snprintf(path,sizeof path,"/proc/%lu/mem",cfg.gp);guifd=open(path,RO);if(guifd<0)return 0;
 snprintf(path,sizeof path,"/proc/%lu/mem",cfg.pp);pagefd=open(path,inspect?RO:RW);if(pagefd<0||!guards())return 0;
 unsigned char visible=255;if(!rd(pagefd,cfg.visible,&visible,1)||visible>1)return 0;shown=visible;
 return 1;
}
static int run_loop(void) {
 char name[64];if(textfile("/sys/class/input/event6/device/name",name,sizeof name)<0||!equal(name,"gui_buttons\n")){logevent("INPUT_IDENTITY",0);return 86;}
 inputfd=open("/dev/input/event6",RO|0x800);if(inputfd<0){logevent("INPUT_OPEN",0);return 86;}
 exitfd=open(DIR "page.log",RO);
 if(!guards()||shown){logevent("NOT_HIDDEN",0);return 86;}
 // Establish and exercise the retained connection before reporting readiness.
 // Earlier boot may precede camera-service readiness; only read properties here.
 int ready=0;
 for(int i=0;i<100;i++){
  if(!guards()||access(DIR "stop",0)==0||access("/blackbox/x2d-preview.disabled",0)==0)return 87;
  int lv=-1,exposure=-1;
  if(get_value("live_view_state",&lv)&&get_value("exposure_status",&exposure)){ready=1;break;}
  poll(0,0,100);
 }
 if(!ready){logevent("BUS_NOT_READY",0);return 87;}
 struct PollFd fd={inputfd,1,0};U checked=0;int last_ack=-1;
 logevent("NATIVE_READY",1);
 while(access(DIR "stop",0)!=0&&access("/blackbox/x2d-preview.disabled",0)!=0){
  if(!guards()){logevent("IDENTITY_LOST",0);break;}
  int result=poll(&fd,1,pending_at?2:40);if(result<0){logevent("POLL_FAILED",0);break;}
  if(fd.revents&(8|16|32)){logevent("INPUT_DEVICE_UNAVAILABLE",fd.revents);break;}
  if(result>0&&(fd.revents&1)){
   struct Event events[8];long count=read(inputfd,events,sizeof events);
   if(count<0||count%(long)sizeof(struct Event)){logevent("INPUT_READ_FAILED",0);break;}
   for(long i=0;i<count/(long)sizeof(struct Event);i++)if(events[i].type==1&&events[i].code==33&&events[i].value==1){
    struct Times rt;clock_gettime(0,&rt);
    long queue=(rt.s-events[i].s)*1000+rt.ns/1000000-events[i].us/1000;
    if(queue>=0&&queue<10000)logevent("EVENT_QUEUE_MS",queue);
    front_key();
   }
  }
  unsigned char actual=255;
  if(!rd(pagefd,cfg.visible,&actual,1)||actual>1){logevent("PAGE_READ_FAILED",0);break;}
  if(actual!=last_ack){last_ack=actual;logevent("VISIBLE_ACK",actual);}
  check_exit_request();
  U now=now_ms();
  if(pending_at&&actual==shown){logevent("REQUEST_TO_ACK_MS",(long)(now-pending_at));pending_at=0;}
  else if(pending_at&&now-pending_at>500){logevent("VISIBLE_ACK_TIMEOUT",actual);pending_at=0;}
  if(shown&&now-checked>=80){
   checked=now;int lv=-1;
   if(get_value("live_view_state",&lv)&&(lv==1||lv==2||lv==3)){if(!request_visible(0))break;save_events();logevent("ORIGINAL_LIVEVIEW_RESUMED",lv);}
  }
 }
 if(guards())request_visible(0);
 return access(DIR "stop",0)==0||access("/blackbox/x2d-preview.disabled",0)==0?0:88;
}
__attribute__((constructor)) static void start_native_input(void) {
 const char *mode=getenv("X2D_MENU_INPUT_MODE");int inspect=equal(mode,"inspect");
 if(!inspect&&!equal(mode,"run"))return;
 if(!host_ok())_exit(81);
 if(unsetenv("LD_PRELOAD")||unsetenv("X2D_MENU_INPUT_MODE"))_exit(82);
 logfd=open(inspect?DIR "native-inspect.log":DIR "native.log",0xA00C1,0600);if(logfd<0)_exit(83);
 if(!open_guarded(inspect)){logevent("GUARDS_FAILED",0);_exit(84);}
 int result=0;
 if(inspect){
  for(int i=0;i<3;i++){int lv=-1,ex=-1;U before=now_ms();int a=get_value("live_view_state",&lv),b=get_value("exposure_status",&ex);
   logevent("READ_ONLY_PAIR_MS",(long)(now_ms()-before));logevent("LIVEVIEW",a?lv:-1);logevent("EXPOSURE",b?ex:-1);if(!a||!b)_exit(85);
  }logevent("INSPECT_OK_NO_WRITES",1);
 }else result=run_loop();
 if(bus){dbus_connection_close(bus);dbus_connection_unref(bus);}
 if(inputfd>=0)close(inputfd);if(exitfd>=0)close(exitfd);if(pagefd>=0)close(pagefd);if(guifd>=0)close(guifd);if(logfd>=0)close(logfd);_exit(result);
}
