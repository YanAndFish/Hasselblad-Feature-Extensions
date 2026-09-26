# 曝光通知到无线发射的中断路径

研究日期：2026-09-10。静态来源为官方 X1D 1.25.0；下文不把发行包中的板级配置直接等同于本次实机启动配置。本轮没有发出相机请求、试闪或拍摄，没有安装中断补丁。

**历史研究记录。** 下文“当前”的 GUI 加子进程架构属于当时版本，后来已改为独立常驻接收与直接驱动提交，且该临时安装目前已失效。用户最新要求已转为 FPGA 硬件链路核对，不再继续抓取四条软件通知；当前结果见 [FPGA_EXPOSURE_PATH.md](FPGA_EXPOSURE_PATH.md)，机身状态见 [README.md](README.md)。

## 结论

目前没有证据证明曝光控制信号直接连接到 BCM4356 的可用触发中断。原厂消息接收程序经串口接收 FARM 消息，再转成 Qt / D-Bus 通知；当前引闪模块在 GUI 收到通知后启动一次快速发射程序。

无线驱动的正常控制命令包含互斥锁及等待响应，不能把这条完整调用直接放进硬中断处理函数。已有证据支持继续研究更短的软件路径：在常驻消息程序收到完整、已解析的曝光消息时通知专用执行端，并预先保持正常驱动接口可用，从而省去 D-Bus、GUI 调度及每次启动程序的开销。该路径尚未实现或实测，不能给出节省多少毫秒的结论。

## 输入绑定

以下文件从官方根文件系统包读取到内存；未执行原厂脚本或加载新内核模块。

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `boot/imx6q-hbl-wedge.dtb` | 40949 | `bcd548efc1c01eb93bb8c8829beb371e2991f42dc7fcdf8bae29fa66d7bc7aca` |
| `lib/systemd/system/msg2dbus-farm.service` | 302 | `ce55146a5cd0a344d3ed2de1c6361d1992eb221f951d2bd418d057cff18fe8c0` |
| `usr/bin/msg2dbus` | 439340 | `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1` |
| `brcmfmac.ko`，内核模块目录内的原厂文件 | 224944 | `e4fc81cc5d28286807033bfa0ea0d2caf878be744c2c06f0fa37ae39d60e37ab` |

`boot/devicetree-zImage-imx6q-hbl-wedge.dtb` 与上表 DTB 字节完全相同。无线模块的版本元数据说明它由 Linux v4.2.6 回移到原厂 3.14.28 内核；上游代码仅用来解释机制，实际函数位置和调用以该模块反汇编为准。

## 已验证的静态事实

### 板级配置

- 根节点为 i.MX6 Quad Hasselblad Wedge Board。PCIe 控制器启用，包含供电与复位 GPIO；这些 GPIO 不能当作曝光输入或发射触发线。
- FPGA 节点位于 WEIM 总线。此次查看的配置没有声明曝光到无线芯片的专用中断连接；这项缺失不能证明电路板上绝无其他连线。
- 名称为 `farm-alert` 的节点使用 `gpio-leds`，子节点默认状态为 `on`。它不是配置中已声明的曝光中断入口，不能按名称直接接作触发源。

### 曝光消息进入 Linux

- `msg2dbus-farm.service` 指定 `/dev/ttymxc2`、波特率 921600、FIFO 调度及优先级 1；这些是发行包配置值，未在本轮测量串口时延或核验实时调度状态。
- `MessageIO_UART::msgtransp_directCallback` 位于 `0x1c600`，在 `0x1c72c` 调用 `0x1c4f8`；后者在 `0x1c54c` 调用 `MessageIO_Interface::ReceiveMessage(QByteArray)`，信号入口为 `0x54f60`。
- 已有曝光消息解析位置保持不变：`0x39784` 判断消息命令 `0x30`，再进入 `0x32464` 发出曝光开始通知。当前 GUI 模块显式订阅对应的 FarmProxy 信号。
- 因而，“在 Linux 较早收到同一条消息时处理”与“曝光硬件直接中断无线芯片”是不同的实现范围。前者仍包含 FARM 消息生成、串口传输及接收解析。

### 正常无线控制接口不能直接用于硬中断

以下地址为 `brcmfmac.ko` 的 `.text` 节相对位置：

- `brcmf_fil_cmd_data_get` 在 `0xa9b8`，其 `0xa9ec` 处重定位目标是 `mutex_lock`；对应 set 和整数接口也包含锁。
- `brcmf_msgbuf_query_dcmd` 在 `0x165ac`：先预留并提交控制环请求，随后等待响应；`0x166f8` 的重定位目标为 `schedule_timeout`，`0x1670c` 为 `prepare_to_wait_event`。
- `brcmf_msgbuf_set_dcmd` 在 `0x1681c`，使用相同查询处理链。不能以“只写一条命令”为由认定不会等待。
- 模块包含 `brcmf_pcie_quick_check_isr_v1/v2` 与 `brcmf_pcie_isr_thread_v1/v2`，并引用 `request_threaded_irq`。现有 PCIe 中断机制的存在不代表已经有曝光事件到发射入口的连接。

Linux 对中断上下文中的可睡眠调用有限制；这与本模块中实际识别出的锁及等待调用相吻合。依据：[Linux 中断上下文调用说明](https://www.kernel.org/pub/linux/kernel/people/rusty/kernel-locking/c557.html)、[上游控制接口锁定代码](https://raw.githubusercontent.com/torvalds/linux/v4.2/drivers/net/wireless/brcm80211/brcmfmac/fwil.c)、[上游控制环提交与等待代码](https://raw.githubusercontent.com/torvalds/linux/v4.2/drivers/net/wireless/brcm80211/brcmfmac/msgbuf.c)。

## 待验证方向

1. 保留设置时准备、单次提交和取消规则，在完整曝光消息接收点接入可辨认的事件。不得把任意串口字节、中断次数或同名 GPIO 当作曝光。
2. 验证预先打开的正常驱动接口能否替代每次启动 `wl`，并让独立执行端处理可能等待的命令。不能让无线响应等待阻塞原厂消息处理循环。
3. 如继续研究无线固件的专用事件或硬件连线，须另行证明事件来源、触发资格、清除和退出行为。当前尚无可安装实现，也无物理延迟测量。

相机正在试用的准备版仍采用 GUI 通知加一次快速发射程序，本研究没有改变它。
