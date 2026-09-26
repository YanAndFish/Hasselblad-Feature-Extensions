#include "settings_wire.h"
u32 as_process(const unsigned char *p,unsigned char *out,u32 state,u32 lens){
    if(!as_owned(p))return 0;
    for(u32 i=0;i<AS_BYTES;i++)out[i]=0;
    as_put(out,0x414c4248);as_put(out+4,0x21345246);as_put(out+8,NA_CONFIG_ABI);
    as_put(out+12,as_get(p+12)|0x80000000u);
    as_put(out+16,as_get(p+16));as_put(out+20,as_get(p+20));
    u32 error=0,op=as_get(p+12),generation=0;
    struct NaConfig pending={0},active={0},input;
    if(as_get(p+8)!=NA_CONFIG_ABI || !as_get(p+16) || !as_get(p+20) ||
       (op!=AS_QUERY && op!=AS_APPLY) || as_get(p+251)!=as_hash(p,251))error=AS_FORMAT;
    for(u32 i=AS_APPLY_END;i<251;i++)if(p[i])error=AS_FORMAT;
    if(!error && op==AS_QUERY){for(u32 i=24;i<AS_APPLY_END;i++)if(p[i])error=AS_FORMAT;}
    if(!error)error=na_config_snapshot(&pending,&active,&generation);
    if(!error && op==AS_APPLY){
        as_config_read(&input,p+28);
        if(lens!=18)error=NA_CONFIG_LENS;
        else if(as_get(p+24)!=pending.revision || input.revision!=pending.revision+1)error=AS_CONFLICT;
        else error=na_config_publish(&input);
    }
    u32 snapshot=na_config_snapshot(&pending,&active,&generation);
    if(snapshot){pending=(struct NaConfig){0};active=(struct NaConfig){0};generation=0;if(!error)error=snapshot;}
    as_put(out+24,error);as_put(out+28,generation);as_put(out+32,state);as_put(out+36,lens);
    /* 快扫→精扫、精扫末段的提前触发尚未接通，两个能力位均为 0；保存不等于介入。 */
    as_put(out+40,0);as_config_write(out+AS_PENDING_OFFSET,&pending);as_config_write(out+AS_ACTIVE_OFFSET,&active);
    as_put(out+251,as_hash(out,251));return 1;
}
void as_receive(const unsigned char *p){
    /* 固定分发点提供已解包的 783 消息，body 是 0,255 加 255 字节。
       非本模块消息原样交给原厂 echo handler。 */
    if(p[0]!=0x0f || p[1]!=3 || p[2]!=5 || p[3]!=1 || p[4]!=0 || p[5]!=255 || !as_owned(p+6)){
        ((void (*)(const unsigned char *))0x1e1e1c)(p);return;
    }
    unsigned char reply[260]={0};
    ((void (*)(const unsigned char *,unsigned char *,u32))0x1e0a50)(p,reply,784);
    as_process(p+6,reply+4,*(volatile unsigned char *)0x6bb46c,*(volatile unsigned char *)0x2adc79);
    ((void (*)(unsigned char *))0x1e80d0)(reply);
}
