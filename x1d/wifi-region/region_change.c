/* X1D 1.25.0 only. Production data never printed. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SIZE 8192
#define REGION 48
#define CHECK 252
static uint32_t get32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void put32(unsigned char *p,uint32_t v) {
    for(int i=0;i<4;i++) p[i]=(unsigned char)(v>>(8*i));
}
static uint32_t checksum(const unsigned char *p) {
    uint32_t v=0xdeadbeef;
    for(int i=0;i<CHECK;i+=4) v^=get32(p+i);
    return v;
}
static int plan(const unsigned char *old,unsigned char *next) {
    if(get32(old+REGION)!=2 || checksum(old)!=get32(old+CHECK)) return 0;
    memcpy(next,old,SIZE); put32(next+REGION,0); put32(next+CHECK,checksum(next));
    for(int i=0;i<SIZE;i++)
        if(!((i>=REGION && i<REGION+4)||(i>=CHECK && i<CHECK+4)) && old[i]!=next[i]) return 0;
    return checksum(next)==get32(next+CHECK);
}
#ifdef MODEL_TEST
int main(void) {
    unsigned char a[SIZE],b[SIZE];
    for(unsigned seed=0;seed<256;seed++) {
        for(int i=0;i<SIZE;i++) a[i]=(unsigned char)(i*37+seed);
        put32(a+REGION,2);put32(a+CHECK,checksum(a));
        if(!plan(a,b)||get32(b+REGION)!=0) return 1;
        for(int i=0;i<SIZE;i++) if(i!=REGION && i!=CHECK && a[i]!=b[i]) return 2;
        a[0]^=1;if(plan(a,b)) return 3;a[0]^=1;
        put32(a+REGION,1);put32(a+CHECK,checksum(a));if(plan(a,b)) return 4;
    }
    puts("plan-tests-passed-valid-corrupt-wrong-region-preserve-other-bytes");return 0;
}
#else
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <signal.h>
#include <errno.h>
#define EEPROM "/sys/bus/i2c/devices/2-0057/eeprom"
#define BACKUP_DIR "/media/data/hbl-wifi-region-r1"
static int read_all(int fd,unsigned char *p) {
    int n=0;
    while(n<SIZE) {ssize_t k=pread(fd,p+n,SIZE-n,n);if(k<=0)return 0;n+=(int)k;}
    return 1;
}
static int durable_backup(const unsigned char *p) {
    if(mkdir(BACKUP_DIR,0700))return 0;
    int dir=open(BACKUP_DIR,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(dir<0)return 0;
    int fd=open(BACKUP_DIR "/original.bin",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    if(fd<0){close(dir);return 0;}
    int n=0;while(n<SIZE){ssize_t k=write(fd,p+n,SIZE-n);if(k<=0)break;n+=(int)k;}
    int ok=n==SIZE && fsync(fd)==0;close(fd);if(fsync(dir))ok=0;close(dir);
    int parent=open("/media/data",O_RDONLY|O_DIRECTORY);if(parent<0)return 0;
    if(fsync(parent))ok=0;close(parent);
    unsigned char verify[SIZE];fd=open(BACKUP_DIR "/original.bin",O_RDONLY|O_NOFOLLOW);
    if(fd<0)return 0;ok=ok && read_all(fd,verify) && !memcmp(p,verify,SIZE);close(fd);return ok;
}
static int field(int fd,const unsigned char *data,int at) {
    return pwrite(fd,data+at,4,at)==4;
}
int main(int argc,char **argv) {
    int apply=argc==2 && !strcmp(argv[1],"--apply");
    if(argc!=2 || (!apply && strcmp(argv[1],"--inspect")))return 2;
    unsigned char old[SIZE],again[SIZE],next[SIZE];
    int fd=open(EEPROM,O_RDONLY|O_NOFOLLOW);
    if(fd<0 || !read_all(fd,old)||!read_all(fd,again)||memcmp(old,again,SIZE)){puts("read-failed-no-write");return 3;}
    close(fd);
    if(!plan(old,next)){puts("precondition-failed-no-write");return 4;}
    if(!apply){puts("region-2-valid-stable-plan-0-two-fields-only");return 0;}
    if(!durable_backup(old)){puts("backup-failed-no-eeprom-write");return 5;}
    fd=open(EEPROM,O_RDWR|O_NOFOLLOW);
    if(fd<0 || !read_all(fd,again)||memcmp(old,again,SIZE)){puts("prewrite-failed-no-eeprom-write");return 6;}
    signal(SIGHUP,SIG_IGN);signal(SIGINT,SIG_IGN);signal(SIGTERM,SIG_IGN);
    int written=field(fd,next,REGION) && field(fd,next,CHECK);
    if(written && read_all(fd,again) && !memcmp(next,again,SIZE)) {
        close(fd);puts("region-0-written-entire-eeprom-verified-backup-retained-restart-required");return 0;
    }
    /* Restore only the two possibly touched fields, never the entire device. */
    int restored=field(fd,old,REGION);restored=field(fd,old,CHECK)&&restored;
    restored=read_all(fd,again)&&!memcmp(old,again,SIZE)&&restored;
    close(fd);
    puts(restored?"write-failed-original-restored-verified":"write-failed-restore-unconfirmed-do-not-restart");
    return restored?7:8;
}
#endif
