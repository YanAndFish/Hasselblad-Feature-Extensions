/* 临时只读 PCIe RAM 映射验证；无写权限，无发射、复位或入口修改。 */
#define _FILE_OFFSET_BITS 64
#include <stdint.h>
#include <stdio.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <string.h>
#include "pcie_readonly_expected.h"
static void *page(int fd, unsigned address) {
    return mmap(0,4096,PROT_READ,MAP_SHARED,fd,address&~4095u);
}
int main(void) {
    int fd=open("/sys/bus/pci/devices/0000:01:00.0/resource2",O_RDONLY|O_CLOEXEC);
    if(fd<0){perror("resource2-open");return 1;}
    volatile uint8_t *p=page(fd,0x214400);
    if(p==MAP_FAILED){perror("resource2-map");close(fd);return 2;}
    for(unsigned i=0;i<sizeof(expected);++i) {
        if(p[0x400+i]!=expected[i]) {
            printf("mapping-mismatch byte=%u actual=%02x expected=%02x\n",i,p[0x400+i],expected[i]);
            munmap((void*)p,4096);close(fd);return 3;
        }
    }
    printf("code-match\n");
    munmap((void*)p,4096);
    p=page(fd,0x217f00);
    if(p==MAP_FAILED){perror("context-map");close(fd);return 4;}
    uint32_t magic=*(volatile uint32_t*)(p+0xf00),owner=*(volatile uint32_t*)(p+0xf04);
    printf("context=%08x owner=%08x\n",magic,owner);
    munmap((void*)p,4096);
    if(magic!=0x47464632 || owner<0x180000 || owner>0x280000-0x110){close(fd);return 5;}
    p=page(fd,owner+0x100);
    if(p==MAP_FAILED){perror("owner-map");close(fd);return 6;}
    printf("d11=%08x\n",*(volatile uint32_t*)(p+((owner+0x100)&4095)));
    munmap((void*)p,4096);close(fd);return 0;
}
