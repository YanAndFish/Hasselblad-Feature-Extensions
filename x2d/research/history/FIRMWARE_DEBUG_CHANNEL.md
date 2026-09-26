> 历史资料归档：第一代 X2D 100C，固件基线 4.2.0。2026-09-12 迁入专属目录；保留原研究结论及批次边界，仅调整链接。最新地区与机内无线研究见 [当前研究索引](../../README.md)。正文中的根目录相对命令仍从项目根目录执行，旧硬件授权不延伸到当前批次。

# X2D 4.2.0：内部详情获取通道

2026-09-09。本轮目标是把现有客户端推进到能取得固件内部执行信息。用户进一步明确“详情也拿到”。本轮仅做本项目实现与离线验证，新增相机请求为 **0**；此前六项 USB 读取和三轮实机报告保持独立。

## 当前结论

| 层次 | 本轮结果 |
|---|---|
| 解析与详情显示 | **已实现**：10 类已有固件日志格式，保留已审查数值、事件含义、函数、源码行与 ELF 发射地址；已做本机 ADB 协议替身端到端验证。 |
| 获取模块 | **已实现条件性接入**：通过已经运行的本机 ADB server，先匹配两份机内程序哈希，再读取已有 DUSS51 日志。没有相机部署、调试开启或日志开关代码。 |
| 当前相机可连接入口 | **未证实**：固件有 ADB 服务，但前序 USB 枚举没有 ADB；尚未找到满足现有边界的量产 ADB 合法开启与恢复流程。不能把服务存在写成电脑已能连接。 |
| 实机端到端取得详情 | **未验证**。本轮未连接 ADB、未开串口，也未新增普通 USB 请求。 |
| 完整调试器 | 未实现断点、单步、寄存器/内存读取或 MCU 调试。固定日志只能证明到达对应消息点，不能给出全部分支或物理闪光时序。 |

目前的实际缺口是**获得合法可用的机内日志读取通道**。不能靠再加 getter、打开 COM 或把人工日志导入界面叫作“打通”。本轮没有一个已经查清访问条件、连带作用和恢复步骤的量产调试开启动作，因此不提出泛泛授权问题，也不实施未知命令试探。

## 为什么 DUSS 的命令成功不等于拿到了详情

所有地址是官方第一代 X2D 100C **4.2.0** 对应 ELF 的虚拟地址，不是运行时绝对地址。哈希见 [完整 ELF 清单](../../../research/binary-manifest.json) 和 [本轮证据检查](../../../research/firmware-observer-checks.json)。实机曾报告版本号 4.2.0，但尚未实测下面两份机内二进制哈希。

1. `camera-service`：`V1Client::debugCmdCb` 位于 `0x1c8050`，在 `0x1c80d8` 调用 `dcam_dbg_cmd`。构造函数 `0x1c8868` 注册 cmd `0x70`。该类实际处理器为 `debugCmdCb`、`returnOkCb`、`notImplementedCb`，没有发现获取详情的第四个回调。
2. 成功分支 `0x1c8268` 取虚表 `+0x80`，实际虚表项 `0x7a9e30` 指向 `DussEventClient::sendResponseOk` (`0x26d728`)；错误项 `0x7a9e40` 指向 `sendErrorResponse`。这条回调没有取出详细文本并作为数据回复。
3. `libdcam_base.so`：`dcam_dbg_cmd` 位于 `0x14a80`，通常经 `0x14ad4` 的 `looper_message_send_and_wait` 进入机内处理线程。它是能执行命令的分发器，不是只读查询。`librcam.so` 的 `DjiRcam_Debug_Func_Register` (`0xa8e00`) 注册了包含写入、任务队列操作、测试、日志等级等能力的内部命令。
4. 详细文本由 `dcam_dbg_append_ack_info` (`0x179d0`) 写入管理对象 `+0x98`，其格式化调用在 `0x17a7c`。本地 socket 接收分支 `0x18da0..0x18de4` 会把成功文本和这个缓冲区拼接，再经 `_resp_ack` 的 `0x193a8` `sendto` 返回。
5. 这个服务器不是电脑网络服务：初始化 `0x15484..0x15498` 明确使用 `socket(1,2,0)`，即 `AF_UNIX / SOCK_DGRAM`；`0x154c0..0x154e0` 构造 abstract 地址，`0x155b8` 绑定。另一个本地回复地址也由 `_dcam_init_local_socket` (`0x191c8`) 构造。没有把这条机内 datagram 通路直接暴露到现有 Phocus bulk 参数接口的证据。

**串口路由更正。** `/system/etc/dji.json` 中 `system_service/mb_route_table/system/a0,a1` 初始值为 `status=0`，使用 `/dev/ttyGS0`。但 `dji_sys::device_sm_host_connect` (`0x28888`) 会先以 0、再以 1 调用 `sys_route_control_ttygs_channel` (`0x288e4`、`0x288f0`)，后者进入 `duss_event_control_rt_byname` (`0x34360`)。断开路径也有路由关闭。因此初始配置不能证明当前实机路由关闭；仅启用路由也没有解决详细回复返回电脑的问题。未打开 COM，未测试运行态路由。

## 真实日志来源与当前可行的获取组件

在 `librcam.so` 的 `Camx_PreStartExpo`、`Camx_StartExpo`、`Camx_FlashEnable` 中核实了 10 个 `duss_log_print` 调用。消息使用模块 `0x51`；实际消息体包含固件函数和源码行。每个文字模板、函数起址、打印调用、模块号、等级和源码行都由 [trace_firmware_observer.py](../../../tools/trace_firmware_observer.py) 从固定 ELF 复核，目录见 [firmware-observer-events.json](../../../research/firmware-observer-events.json)。

示例：`Camx_StartExpo:1028` 的电子快门消息在 `0xa3ef4` 发射，含最大快门时间参数与曝光时间参数；`Camx_FlashEnable:1226` 在 `0xa64a4` 报告 FSYNC 配置返回错误。这些是内部执行点的数据，**不是**发光时刻或测得的曝光时间。

`libduml_util.so` 的日志出口表在 `0x90158`，共 7 项，包含 console、syslog、Android main/system/crash、本地 `/dev/aplog` 和空回调；没有在这张表发现直接向电脑地址发送详情的出口。Android 写入调用例如 `0x1b8c8`、`0x1b97c`。`dji.json` 给 `dji_rcam` 配置 `android_system_log`、`info` 和 `basic` 格式，给 `dji_camera3` 配置相同通道、`warning` 等级。实际运行等级和日志是否仍在缓冲区不能由静态配置保证。

固件 `/system/bin/cam_log_dump.sh:66` 本来就在读取 system/crash logcat 缓冲区，日志文件目录为 `/blackbox/camera/log`。本轮不启动或修改它；客户端选择读取已经存在的 DUSS51 缓冲区，避免完整日志目录、配置资料和图片。

已实现的电脑路径为：

```text
已合法开放且已授权的相机 ADB
    → 已运行的本机 ADB server (127.0.0.1:5037)
    → 唯一 Eagle2 设备 + shell v2 能力检查
    → 两份程序 SHA-256 校验
    → 固定 logcat 有限读取
    → 固定消息格式解码、过滤
    → 详情界面与脱敏报告
```

ADB smart-socket、host 服务和设备传输切换依据 [AOSP 服务定义](https://android.googlesource.com/platform/system/core/+/refs/tags/android-7.1.2_r1/adb/SERVICES.TXT) 及 [transport-id 客户端实现](https://android.googlesource.com/platform/packages/modules/adb/+/ec7028fb5c2cde5c18522dd08f7c34c5e668fc83/client/adb_client.cpp)。shell v2 区分 stdout、stderr 和退出包，包头使用类型和 32 位长度；退出值为一个字节。见 [协议定义](https://android.googlesource.com/platform/packages/modules/adb/+/43231f1dabbb1d2cf82b605b8d667b1583b87c7e/shell_protocol.h) 与 [守护进程的退出包实现](https://android.googlesource.com/platform/system/core/+/75b3266/adb/daemon/shell_service.cpp)。这些资料支持主机组件实现，不证明当前相机已经开放 ADB。

## 固定操作与副作用

[adb-log.ts](../../../app/adb-log.ts) 只请求本机 `host:devices-l` 和所选 transport 的能力。产品标识取自官方 `/system/build.prop` 的 Eagle2 EC1706 项；一个目标也必须通过文件哈希检查，不能把通用 Eagle2 产品名当成 X2D 的充分身份依据。多个设备、未授权状态、不符的标识或能力都停止，不猜测凭据。

只有后续已获协调的实机批次，才会依次运行下面两个固定命令；**本轮均未执行**：

```text
/system/bin/sha256sum /system/bin/camera-service /system/lib64/librcam.so
/system/bin/logcat -d -t 300 -v brief -b main -b system -b crash 'DUSS51:V' '*:S'
```

文件哈希必须严格匹配官方 4.2.0，才进入日志读取。两份文件和 `sha256sum`、`logcat` 都已在离线固件文件树确认。未使用 `adb root`、`start-server`、设备认证、shell 任意输入、端口转发、debug/log enable、写参数、程序部署或内存转储。日志读取过滤只改变本次 logcat 的显示选择，不修改固件产生日志的等级或开关。

执行仍有副作用：短期创建哈希与 logcat 读取进程，消耗 CPU/文件读取资源；已有 ADB 会话可能保持唤醒。它不停止实时相机进程、不触发曝光或闪光。每条主机通道绝对时限 8 秒，共最多四条通道；原始日志上限 512 KiB，shell 单包上限 64 KiB，最多保留 300 个已核实事件。超时、错误、非零退出、stderr、坏包、大小或编码异常即停止，没有自动重试。`closed` 仅指本轮主机 TCP 连接已关闭；未收到退出包时，不假称机内命令已成功完成。每个已提交命令的完成状态另记录。

数值显示范围是本地防异常规则，不是合法相机设置范围。未知行及未知数值不进入输出，只保留过滤计数。任务名、PID、序列号、路径前缀、照片信息和原始日志不写到报告。输出顺序不是全局执行顺序；多线程记录不提供严格因果关系，缺失日志不证明某条分支未运行。

## 为什么不调用现有“保存日志”或直接改 ADB 配置

`camera-system::LogHandler::saveLogs` (`0xbcb88`) 进入 `collectLogs`、`doCollectLogs`。固件 `collect_logs.sh` 不只读目标日志：会收集配置、设备资料、截图等，打包后调用 `store-log-encrypted` 写入存储，再清理打包临时文件。它不符合本次固定内部消息的范围，且加密包不等于客户端能直接解码的事件流。因此没有调用。

`setup_usb.sh:132..141` 在 production 且 `secure_debug=0` 或该标志缺失的分支选择不含 ADB 的 USB 组合。固件也有 `check_secure_debug` 与 ADB 服务配置；这些存在性证据不是正常用户可操作的解锁入口。本轮未找到可在现有只读会话中合法执行、并已核实持久性及恢复方法的 ADB 开启动作；不能把改属性、改启动标志、刷写或绕过访问检查包装成普通连接。

**继续实机的前置缺口：**需要用户通过合法方式提供已经开放、已经授权电脑的 ADB 调试连接，或另找到正常协议中真正回传上述内部输出的接口。前者的开启流程目前未证实，所以现在没有值得用户批准的确定开启命令。若之后取得合法 ADB 通道，先由来源任务协调当时相机已唤醒，再执行这个固定批次；旧唤醒确认不能沿用。

## 实现、复现与验证

- [消息解析](../../../app/firmware-log.ts)、[受限 ADB 获取](../../../app/adb-log.ts)、[CLI](../../../tools/read-firmware-logs.cjs)。CLI 无参数只显示条件和命令，硬件请求为 0；`--read-existing` 才执行固定流程，不提供 URL、串口或命令输入。
- 界面“固件内部事件”分别标出解析已实现、接入条件和实机未验证。人工回放使用实际格式和人工数值，并明确不是相机执行结果；不会通过回放把实机状态标成已验证。
- `py -3.11 -B tools/trace_firmware_observer.py`：10 个发射点的 60 项核对、12 个通路调用核对、4 个配置文件哈希，结果全部通过；新获取模块未执行任何相机命令。
- `npm test`：29 项全部通过，其中新增 12 项 ADB 替身与消息解析验证，覆盖分包、粘包、哈希门控、拒绝、stderr、非零退出、损坏/过大包、截断、超时、未知内容过滤、空缓冲区与忙状态；测试 server 只监听本机随机回环端口。
- `npm run test:package`：实际打包 EXE 的 9 组界面检查全部通过，使用 `--smoke`，USB 与 ADB 适配器均为空。截图在 [离线接入状态](../../../research/validation/packaged/firmware-unconnected.png)、[人工详情回放](../../../research/validation/packaged/firmware-replay.png)，已经人工检查详情表和接入状态布局，不能作实机证据。

跨机型可复用的是 ADB 主机协议、有限读取编排、过滤框架和报告结构。X1D 的入口、处理器、固件哈希、消息模板及行为必须在独立证据下配置；本轮没有接入 X1D，也没有修改其项目或实验文件。
