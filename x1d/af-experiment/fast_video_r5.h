/* 开发中：固定 FARM 1.25.0，视频任务内串行切换。当前仅离线链接验证。 */
#ifndef FAST_VIDEO_R5_H
#define FAST_VIDEO_R5_H
typedef unsigned int fv_u32;
struct FastVideoState {
    volatile fv_u32 magic,abi,enabled,session;
    volatile fv_u32 request,ack,target,result,applying,dirty,need_recovery;
    volatile fv_u32 external_epoch,session_epoch,request_epoch;
    volatile fv_u32 observed_width,observed_height,width,height,roi0,roi1,full_rate;
    volatile fv_u32 pipeline_calls,pipeline_result,spi_calls,spi_result,spi_bytes;
    volatile fv_u32 ready_tick,ready_rate,switches,canary;
};
extern struct FastVideoState fast_video_state;
/* 独立诊断字，不改变原120字节视频状态ABI。高位表示尚无本轮资格检查。 */
extern volatile fv_u32 fast_video_begin_status,fast_video_begin_generation;
enum { FV_GATE_BUSY=1, FV_GATE_DISABLED=2, FV_GATE_RECOVERY=4, FV_GATE_AF_STATE=8,
       FV_GATE_INACTIVE=16, FV_GATE_MODE=32, FV_GATE_GENERATION=64,
       FV_GATE_DIMENSIONS=128, FV_GATE_GAIN=256, FV_GATE_ROI=512 };
enum { FV_OK, FV_SUPERSEDED, FV_STOP_FAILED, FV_APPLY_FAILED, FV_PIPELINE_FAILED,
       FV_SENSOR_FAILED, FV_CONFIG };
fv_u32 fast_video_begin(fv_u32 generation,fv_u32 roi0,fv_u32 roi1,fv_u32 rate);
fv_u32 fast_video_request(fv_u32 target);
void fast_video_service(void);
#endif
