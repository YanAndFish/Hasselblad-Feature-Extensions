/* 固定 X1D 1.25.0 FARM，GFP3 两点观察候选；未装入相机。
 * 参数在原厂换算完成后保存；启动点另记录原始时间和状态。
 * 无拍摄、SPI、任务消息、计时器配置或引闪入口。
 */
#include <stdint.h>

#define MAGIC UINT32_C(0x33504647)
#define CONFIG UINT32_C(0x006c1690)
#define REGISTERS UINT32_C(0x006db2e8)

struct stamp { uint32_t low, high, control, valid; };
struct capture {
    uint32_t magic, armed, sequence, event;
    struct stamp before;
    uint32_t status, shadow[5];
    uint32_t start_frames, mode_flags, start_registers[2];
    struct stamp after;
    uint32_t encoded_valid, encoded_frames, encoded_registers[2];
    uint32_t exposure_low, exposure_high, encoded_calls;
};
_Static_assert(sizeof(struct capture) == 116, "GFP3 layout");

static uint32_t read32(uint32_t address)
{
    return *(volatile const uint32_t *)(uintptr_t)address;
}

static int ready(volatile struct capture *out)
{
    return out && !((uintptr_t)out & 3) && out->magic == MAGIC &&
           out->armed == 1 && !(out->sequence & 1);
}

__attribute__((noinline)) static void capture_time(volatile struct stamp *out)
{
    const uint32_t base = UINT32_C(0xf8f00200);
    out->low = out->high = out->valid = 0;
    uint32_t control = read32(base + 8);
    out->control = control;
    if (!(control & 1)) return;
    for (unsigned attempt = 0; attempt != 4; ++attempt) {
        uint32_t high = read32(base + 4);
        uint32_t low = read32(base);
        if (high == read32(base + 4)) {
            if (control == read32(base + 8)) {
                out->low = low;
                out->high = high;
                out->valid = 1;
            }
            return;
        }
    }
}

/* 包装已核对原厂调用者、配置及缓冲指针；此处不调用原厂函数。
 * 两点之间仍由原厂正常应用参数。输入时长及寄存器编码不是感光测量。
 */
__attribute__((used, visibility("default")))
void farm_capture_encoding(volatile struct capture *out, uint32_t low, uint32_t high)
{
    if (!ready(out)) return;
    out->encoded_valid = 0;
    out->encoded_frames = read32(CONFIG + 0x98);
    out->encoded_registers[0] = read32(REGISTERS);
    out->encoded_registers[1] = read32(REGISTERS + 4);
    out->exposure_low = low;
    out->exposure_high = high;
    /* 多次准备只保留最后一次，并用计数明确暴露配对歧义。 */
    if (out->encoded_calls != UINT32_MAX) ++out->encoded_calls;
    __asm__ volatile("dmb sy" ::: "memory");
    out->encoded_valid = 1;
}

__attribute__((used, visibility("default")))
void farm_capture_start(volatile struct capture *out)
{
    if (!ready(out)) return;
    uint32_t sequence = out->sequence;
    out->armed = 0;
    out->sequence = sequence + 1;
    __asm__ volatile("dmb sy" ::: "memory");
    out->event = 1;
    capture_time(&out->before);
    out->status = read32(UINT32_C(0x42000014));
    for (unsigned index = 0; index != 5; ++index)
        out->shadow[index] = read32(UINT32_C(0x002b1990) + index * 4);
    out->start_frames = read32(CONFIG + 0x98);
    out->mode_flags = read32(CONFIG + 0x7c);
    out->start_registers[0] = read32(REGISTERS);
    out->start_registers[1] = read32(REGISTERS + 4);
    capture_time(&out->after);
    __asm__ volatile("dmb sy" ::: "memory");
    out->sequence = sequence + 2;
}
