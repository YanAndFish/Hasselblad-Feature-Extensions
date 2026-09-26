/* X1D 1.25.0 FARM 的一次性 SENSORIF 观察组件；尚未装入相机。
 * 仅供原厂 0x21410c 写控制寄存器返回后的普通任务上下文调用。
 * 这记录控制提交后的状态，不表示传感器开始积分。
 * 本文件没有安装器、指令替换、串口、拍摄或引闪入口。
 */
#include <stdint.h>

#define PROBE_MAGIC UINT32_C(0x32504647)
#define TIMER_BASE UINT32_C(0xf8f00200)
#define SENSOR_STATUS UINT32_C(0x42000014)
#define SENSOR_SHADOW UINT32_C(0x002b1990)
#define SENSOR_CONFIG UINT32_C(0x006c1690)
#define SENSOR_REGISTERS UINT32_C(0x006db2e8)

struct probe_time {
    uint32_t low, high, control, valid;
};

struct farm_sensor_probe {
    uint32_t magic, armed, sequence, event_kind;
    struct probe_time before;
    uint32_t sensor_status;
    uint32_t shadow_words[5];
    uint32_t exposure_frames, mode_flags, sensor_register_words[2];
    struct probe_time after;
};

_Static_assert(sizeof(struct farm_sensor_probe) == 88, "GFP2 record layout");

static uint32_t read32(uint32_t address)
{
    return *(volatile const uint32_t *)(uintptr_t)address;
}

/* 高/低/高核对跨字回卷；只读，最多四次，不开启或重设计时器。
 * 原始计数的实际频率和运行状态须另行核实，不能直接输出微秒。
 */
__attribute__((noinline)) static void read_time(volatile struct probe_time *value)
{
    value->low = value->high = value->valid = 0;
    uint32_t control = read32(TIMER_BASE + 8);
    value->control = control;
    if (!(control & 1))
        return;
    for (unsigned retry = 0; retry != 4; ++retry) {
        uint32_t high = read32(TIMER_BASE + 4);
        uint32_t low = read32(TIMER_BASE);
        uint32_t high_again = read32(TIMER_BASE + 4);
        if (high == high_again) {
            uint32_t control_after = read32(TIMER_BASE + 8);
            if (control_after == control) {
                value->low = low;
                value->high = high;
                value->valid = 1;
            }
            return;
        }
    }
}

/* 调用者须提供本补丁独占、可写且已初始化的记录区，并保证 PL 正在运行。
 * armed==1 只消费一次；默认零不读取硬件。宿主以偶数且前后相同的
 * sequence 接受完整记录。安装位置、原指令恢复及缓存同步由装载器负责。
 */
__attribute__((used, visibility("default")))
uint32_t farm_sensor_probe_after_start(volatile struct farm_sensor_probe *out)
{
    if (!out || ((uintptr_t)out & 3) || out->magic != PROBE_MAGIC ||
        out->armed != 1 || (out->sequence & 1))
        return 0;

    uint32_t sequence = out->sequence;
    out->armed = 0;
    out->sequence = sequence + 1;
    __asm__ volatile("dmb sy" ::: "memory");
    out->event_kind = 1; /* SENSORIF 控制写入已返回，非积分事件。 */
    read_time(&out->before);
    out->sensor_status = read32(SENSOR_STATUS);
    for (unsigned i = 0; i != 5; ++i)
        out->shadow_words[i] = read32(SENSOR_SHADOW + 4 * i);
    /* 原厂配置及寄存器软件缓冲，均不是新 SPI 请求。
     * 本挂接位置早于 0x1c437c 启动的原 SVR 更新定时器。
     * 保存原始位；不把 SVR 或行编码直接称为感光时刻。
     */
    out->exposure_frames = read32(SENSOR_CONFIG + 0x98);
    out->mode_flags = read32(SENSOR_CONFIG + 0x7c);
    out->sensor_register_words[0] = read32(SENSOR_REGISTERS);
    out->sensor_register_words[1] = read32(SENSOR_REGISTERS + 4);
    read_time(&out->after);
    __asm__ volatile("dmb sy" ::: "memory");
    out->sequence = sequence + 2;
    return 1;
}
