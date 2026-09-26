# AF 两阶段试探完整交付 r6

本版为固定 X1D 1.25.0 FARM 基线上的临时 AF 完整包。新增每轮一次的低速起步，按原厂接受的有效采样数量转入高速段；保留 r5 的滚动判向、远端优先、原厂状态迁移以及 bus-reply-r5 的跨线程 `postEvent` 回复修复。没有改变 ROI、判向算法、原厂后续判向门限或提前量实现。

当前仅完成离线构建与验证，设备请求为 0。安装流程可用不代表实机效果已验证。本包需要原厂 Linux/AF 干净基线，**不能覆盖当前已经安装的独立 UI**。主任务已报告当前存在 `/tmp/hbl-ui-resident` 和 `90-hbl-ui-resident.conf`；以后安装 r6 须由主任务协调新的正常重启并核对基线，或另行获得明确共存需求后建立合同。本版不实施共存适配，也不删除其他模块。

## 界面与行为

| 设置 | 取值及默认值 |
|---|---|
| 低速起步 | 关闭（默认）、1000、2000、3000、4000、5000 |
| 有效采样数 | 1–500，默认 3；每次增减 1 |
| 高速段 | 跟随原厂（默认）、5000、7000、9000、11000、13000、15000、17000、20000 |
| 快速扫描与原厂精扫 | 保留原有档位和默认值 |

旧“判向试探”改名“高速段”。设置列表可上下滑动，返回、读取和保存仍固定在屏幕上。参数保存后在下一轮 AF 开始时整体锁存；不会自动选择低速档或自动保存。新判向开关仍默认关闭。

开启低速起步后，初始试探命令使用独立低速幅值，原有远端优先仍生效。从初始命令之后累计原厂 `nc_accepted` 入口确认接受的采样；它不是显示视频帧数、IRQ 次数或物理曝光数。原厂数组计数重置时，低速段已经累计的数量不回零。

每次原厂完整判向函数返回时，若已经成功发出 FAST，低速阶段立即结束，不等待设定数量。若仍处于试探状态，且累计数量达到设置值，则只发送一次高速段命令。切换保留当前运动符号；高速段选“跟随原厂”时恢复本轮初始原厂试探命令幅值。端点折返、重复处理同一批采样、FAST 失败后回到试探状态，均不会重新开始低速段。只有下一轮 AF 重置才重新启用。

这些速度是 signed16 命令幅值，不是实测镜头运动速度。两项提前量继续沿用原版“保存但未接通”的限制；本版未宣称完成毫秒补偿。

## 固定实现与验证范围

- FARM 基线 SHA-256：`317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca`。实际装载仍须版本及原字校验，不能以静态分析代替现场检查。
- ABI4 配置为 13 个 32 位字；UI、Bus、FARM 同步升级。请求尾部从 80 字节起要求零填充；回复中的 pending/active 配置分别在 44/96 字节。旧 ABI 不被当作新配置接受。
- 在原 14 个入口外仅增加 `0x19d5c0` 的判向函数返回入口，原指令 `0xe24bd008`。它与原有 peak 入口共享已检查缓存行；首次安装的预检请求数、缓存范围保护和只读闪光区域不扩大。
- 低速累计数量和周期编号保存在同一原子字，按周期检查并通过 CAS 完成一次切换；有效周期编号超过 22 位时禁用低速起步，避免编号复用。
- 新 ARM 候选为 18208 字节，仍只使用一次原厂 32768 字节分配。实际安装地址重新构建后，来源、入口、分配归属及逐字结果继续绑定安装日志。

`CodeTests/validate.py` 汇总实际 ARM 参数/判向/两阶段执行、完整分配安装与逐字回滚、主机失败分流和组合差异验证。`CodeTests/test_linux.py` 使用实际 shell 与隔离服务替身；`bus/CodeTests/test_roundtrip.py` 执行真实 Bus 方法、跨线程事件投递和 ARM interposer。`CodeTests/test_qml.py` 在 Qt 6.11.2 主机环境验证三个尺寸、两个入口及原厂父级拖动过滤下的点击与纵向滑动；它不等于相机 Qt 5.5.1 的现场验收。

最终检查结果及所有冻结来源以 `validation.json` 为准。Linux 归档 `inputs/af-only.tar.gz` 为 90530 字节，SHA-256：`13aeec312bda478d7c64d6ae40c19c0f46f2c67d990308b30b0a81a15e54cf18`。

## 主任务入口与恢复

在 `.` 执行。`report` 完全离线；设备动作必须由主任务串行安排：

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py report
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py stage
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py install-staged --evidence <本次 stage.json 的绝对路径>
```

流程保留 r5：一次传包并校验 → 原厂 Linux preflight → 一次 GUI/hold 启动 → 一次 Bus 启动 → 完整 FARM 原字检查 → 持久日志 → 缓存探针 → 原厂分配 → 重定位构建 → 15 个入口安装及核验 → 释放 hold。没有自动对焦、拍摄、配置 apply、回放安装或相机重启。Bus 重新启动会执行原厂链路初始化，不能称为无连接副作用。

成功 hold 后首笔 FARM 读取仅发送一次、最多等待 20 秒；之后为 2 秒，失败不自动重试。预检模型为 7905 请求、31 次 hold 检查、0 RAM 写入。段预算、健康窗口、写入白名单、闪光只读保护及恢复分流保持原版。

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py inspect --evidence <本次 installation.json>
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py restore-preflight --evidence <同一 installation.json>
python -B x1d/af-experiment/camera-settings-r1/delivery-r6/main.py rollback-held --evidence <本目录 recovery 中完整安装日志>
```

`inspect` 离线判断恢复分流。明确证明 0 RAM 写入、句柄关闭且无 RAM 意图时，`restore-preflight` 只恢复本包 Linux 服务。完整 RAM 安装且现有 hold 仍有效、未释放时，才能使用 `rollback-held` 逐字恢复 15 个入口与 bootstrap；保留已分配堆块，不释放。hold 已释放或过期，不重新建立窗口。USB/分配/写入结果未知、日志残尾或外来配置时停止并保留证据，不重发、不清理依赖、不自动重启。

完整安装后的匿名诊断沿用 `/tmp/hbl-af-settings/backend-r5.status`、`backend-r5-flow.status`、`backend-r5-transport.status` 与 `ui-r4.status` 的实际目录定义；路径以 `native` 相关头文件及 `bus/settings_socket.h` 为准。`ready` 或服务 active 不等于参数读取、保存成功。

用户观察“螺丝起步画面越来越糊、尚未识别方向、到端点再折返并最终合焦”另列为后续研究，不作为本版交付依赖。用户已撤回“判反”表述，新判向开关状态未知；显示模糊变化不能直接证明原生 CV 单调下降。本版不能宣称解决该现象。
