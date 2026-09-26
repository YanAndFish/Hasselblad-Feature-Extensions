// 仅用于执行实际 Bus 方法；Qt、时钟、socket 和文件系统替身不访问设备。
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <deque>
#include <string>
#include <vector>
#include <mutex>
#include <thread>
using pthread_mutex_t=std::mutex;
#define PTHREAD_MUTEX_INITIALIZER {}
static int pthread_mutex_lock(pthread_mutex_t *m){m->lock();return 0;}
static int pthread_mutex_unlock(pthread_mutex_t *m){m->unlock();return 0;}
extern "C" {
#include "settings_wire.h"
}
using qint64=long long;
static qint64 now=0;
struct QThread { static QThread *currentThread(){static QThread t;return &t;} };
struct QEvent {
    enum Type {User=1000};Type t;explicit QEvent(Type v):t(v){}virtual ~QEvent()=default;
    Type type(){return t;}static int registerEventType(){return 1001;}
};
static unsigned forwardedEvents=0;
struct QObject {
    explicit QObject(QObject * =nullptr){} virtual ~QObject()=default;
    virtual bool event(QEvent *){++forwardedEvents;return false;}
    QThread *thread(){return QThread::currentThread();}
    std::vector<QObject *> children(){return {};}
    template<class... T> static void connect(T... ){}
};
static std::mutex postedMutex;
static std::deque<std::pair<QObject *,QEvent *>> posted;
struct QCoreApplication {
    static void postEvent(QObject *o,QEvent *e){std::lock_guard<std::mutex> lock(postedMutex);posted.push_back({o,e});}
};
static void drainEvents(){
    for(;;){std::pair<QObject *,QEvent *> p;
        {std::lock_guard<std::mutex> lock(postedMutex);if(posted.empty())return;p=posted.front();posted.pop_front();}
        p.first->event(p.second);delete p.second;
    }
}
template<class T> struct QPointer {
    T *p;QPointer(T *v):p(v){} T *operator->()const{return p;} operator T *()const{return p;}
};
struct QElapsedTimer { qint64 startAt=0;void start(){startAt=now;}qint64 elapsed(){return now-startAt;} };
struct QByteArray {
    std::string v;QByteArray(int n,char c):v(n,c){} int size()const{return int(v.size());}
    char &operator[](int n){return v[n];}char *data(){return &v[0];}const char *constData()const{return v.data();}
};
struct QSocketNotifier:QObject { enum {Read=0};QSocketNotifier(int,int,QObject *){}void activated(int){} };
struct QTimer:QObject { explicit QTimer(QObject *p):QObject(p){}void setInterval(int){}void timeout(){}void start(){} };
namespace Qt { enum {DirectConnection=1}; }
static bool invoked=true,accepted=true,delivered=true;
static unsigned invocations=0;
static std::vector<unsigned char> sent,returned;
struct BoolArg{const char *type;bool *p;};struct ByteArg{const char *type;QByteArray *p;};
#define Q_RETURN_ARG(T,p) BoolArg{#T,&p}
#define Q_ARG(T,p) ByteArg{#T,&p}
struct QMetaObject {
    static bool invokeMethod(QObject *io,const char *name,int type,BoolArg ret,ByteArg arg){
        assert(io && !std::strcmp(name,"SendMessage") && type==Qt::DirectConnection);
        assert(!std::strcmp(ret.type,"bool") && !std::strcmp(arg.type,"QByteArray"));
        assert(!*ret.p);++invocations;
        sent.assign(arg.p->constData(),arg.p->constData()+arg.p->size());
        if(invoked)*ret.p=accepted;return invoked;
    }
};
struct Datagram {int result;std::vector<unsigned char> bytes;};
static std::deque<Datagram> incoming;
#define AS_DIRECTORY "/test"
#define AS_BACKEND "/test/backend"
#define AS_UI "/test/ui"
static int as_bind(const char *){return 7;}
static int as_recv(int,unsigned char *p,const char *peer,unsigned *reason){
    *reason=0;
    assert(!std::strcmp(peer,AS_UI));
    if(incoming.empty()){errno=EAGAIN;return -1;}
    auto d=incoming.front();incoming.pop_front();
    if(d.result==1){assert(d.bytes.size()==255);std::memcpy(p,d.bytes.data(),255);}return d.result;
}
static bool as_send(int,const char *peer,const unsigned char *p){
    assert(!std::strcmp(peer,AS_UI));returned.assign(p,p+255);return delivered;
}
static bool as_directory(){return false;}
static int as_stat(const char *,uint32_t &,uint32_t &){assert(false);return -1;}
static int geteuid(){return 0;}
static int fakeOpen(const char *,int,int){assert(false);return -1;}
static int fakeWrite(int,const char *,size_t){assert(false);return -1;}
static int fakeClose(int){return 0;}
static int fakeUnlink(const char *){return 0;}
#define open fakeOpen
#define write fakeWrite
#define close fakeClose
#define unlink fakeUnlink
#define O_WRONLY 0
#define O_CREAT 0
#define O_TRUNC 0
#define O_CLOEXEC 0
#define O_NOFOLLOW 0
#define O_NONBLOCK 0
#define S_ISREG(x) ((x)!=0)
static void health(const char *,int=0){}
#include "transport_counts.h"
static TransportCounts transport;
static void transportSnapshot(){transport.changed();}
