/* 保留已装正式发送逻辑；新增白名单只读快照，不启动或准备发射。 */
#define hbl_formal_dispatch hbl_existing_dispatch
#include "formal_flash.c"
#undef hbl_formal_dispatch
__attribute__((used)) unsigned hbl_formal_dispatch(uintptr_t pi,unsigned selector) {
    static const uint16_t offsets[]={0x538,0x540,0x542,0x544,0x546,0x54a,0x55a,0x55c,0x492};
    if(selector==12050) return 0x5052;
    if(selector>=12064 && selector<12064+sizeof(offsets)/sizeof(offsets[0])) {
        uintptr_t regs=*(volatile uint32_t *)(pi+0x100);
        return *(volatile uint16_t *)(regs+offsets[selector-12064]);
    }
    return hbl_existing_dispatch(pi,selector);
}
