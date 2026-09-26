# X1D 正常 USB 诊断链核查

2026-09-10。静态输入为官方 **X1D-50c 1.25.0**；本轮另获用户对第一代 X1D 单次 USB 诊断读取的明确授权。已完成该读取，实机固件版本仍未知。图像增强及 v3 工作保持暂停。

**本轮单次实测成功：2026-09-10 01:15:44+08，完整发送 512 字节，收到 512 字节匹配回复，状态值为 `1`，全部句柄正常关闭。** 这证明此次 FX3 控制请求/回复通路可用，不能诊断错误 1000 或证明相机恢复。详情见[实际硬件记录](validation/hardware/x1d-usb-link-20260910-authorized-once.json)。本次没有运行 Phocus 或进行客户端身份登记、联机模式设置。

已有的错误页保存日志、Retry、SD/ROM 恢复结果分别见 [日志导出](ERROR1000_LOG_EXPORT.md)、[恢复入口](RECOVERY_ENTRYPOINTS.md)及[独立 USB/SD 矩阵](../recovery-review/20260910-usb-sd/USB_SD_MATRIX.md)。本报告只补充正常控制消息，不重复底层启动介质调查。

## 1. 输入与验证

主输入为[官方 X1D 1.25.0 CIM](https://cdn.hasselblad.com/firmware/X1D-50c_Firmware/1.25.0/X1D_v1_25_0.cim)，SHA-256 为 `1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2`。

| 程序 | SHA-256 |
|---|---|
| `phocus-daemon` | `5c17bad12039c649e8b5c8ad1070763d1fc90d40f25d21f8a45bf506041db378` |
| `msg2dbus` | `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1` |
| `libAppsMessaging.so` | `8a6a45428fcaa17e570e0aad217ee7220716501bcaf4cddef106af5137d6f7d1` |
| `libappscommon.so.1.0.0` | `2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263` |
| `fx3_wedge-v0.0-14268-e0ef6ae.bin` | `19236566d65ad6881fda0ee554944374188217fbcb514f0eb8c0cae1416b5a05` |

FX3 输入仅在内存解析原厂 `CY` 分段格式、范围和累加校验；没有修改或执行。新提取的两个 Linux 输入见[补充清单](usb-diagnostic-input-manifest.json)。

[静态脚本](../tools/audit_usb_diagnostic_path.py)已通过 **5 个程序哈希、58 条指令、12 个常量、9 个消息定义、3 份配置描述符**，输出[机器证据](validation/usb-diagnostic-path-static.json)。接机前，[离线契约的 7 项测试](../CodeTests/usb_diagnostic/test_fx3_link_contract.py)和[单次传输控制的 9 项测试](../CodeTests/usb_diagnostic/test_usb_once.py)全部通过，覆盖机型隔离、有效/异常回复、超时不重试和句柄关闭。测试均用人工数据，硬件结果由独立记录证明。

## 2. FX3 本地状态请求

原厂 USB 配置包含两对 bulk 端点。`0x400042f0…0x40004358` 建立控制方向的 DMA：生产 socket `0x402` → CPU，CPU → 消费 socket `0x302`，两者使用回调 `0x40003f68`。这与描述符中的 **OUT `0x02` / IN `0x82`** 对应。SDK 的 socket、DMA 类型和回调定义用于解释数字；哈苏地址和配置来自上述固定二进制。[Infineon API Guide](https://community.infineon.com/gfawx74859/attachments/gfawx74859/twusblowfullhighspeed/399/1/FX3APIGuide.pdf)、[AN75705](https://www.infineon.com/assets/row/public/documents/24/42/infineon-an75705-getting-started-with-ez-usb-fx3-applicationnotes-en.pdf?fileId=8ac78c8c7cdc391c017d073989df5e15)。

| 环节 | 固定版本证据 |
|---|---|
| 控制数据到达 | `0x40003f68` 检查生产事件 `8` 和生产 socket `0x402`，随后 `0x40003f90 → 0x4000517c` 入队。 |
| 收包分流 | `0x400053e0` 处理队列，读取消息头第 3 字节；目标 `9` 进入 FX3 本地处理，其他目标交给 `0x40007870` 消息传输函数。后者的全部板级下游连接尚未闭环。 |
| 本地请求处理 | `0x400054b0` 的循环仅接收目标 `9`；请求 ID `0x0471` 在 `0x400054f8` 分支到 `0x4000553c`。 |
| 返回值 | `0x40005558 → 0x40004ffc`，从本地 USB 活动标志和速度读取结果。返回值只产生 `0`、`1` 或 `3`；速度 getter `0x40010a54` 只是读取缓存字节。 |
| 回复地址与 ID | `0x4000553c…0x40005550` 把请求源节点作为回复目标，回复源为 `9`、ID 为 `0x0472`。 |
| 发回主机 | `0x400055ec → 0x40005230`；目标 `8` 进入 `0x400044a8`，交给控制 IN DMA 缓冲。 |

`libAppsMessaging.so` 的节点表把 `8` 命名为 `usbhost`、`9` 命名为 `fx3`。这些是该正常消息格式的路由地址。消息头为小端 16 位 ID、8 位源节点、8 位目标节点；消息表同时在 FX3 与 Linux 库中核对一致。

本次实测使用以下契约。编码依据来自固定 1.25.0；实际匹配只证明此次请求兼容，不能确认实机整个固件版本。

| 数据 | 语义区 |
|---|---|
| 请求 | `71 04 08 09 00`：ID `0x0471`，正常主机节点 `8` → FX3 节点 `9`，1 字节占位体为零。 |
| 回复 | `72 04 09 08` 后跟 4 字节小端状态。只接受 `0/1/3`，其余拒绝。 |
| 状态解释 | bit 0 为原厂本地 USB 活动标志；bit 1 仅在该标志有效且速度为 SuperSpeed 时置位。它们不是 SUC/FARM 健康结论。 |
| 传输槽长度 | 静态配置有 `64/512/1024` 字节；本次 WinUSB 取得的实际最大包长为 `512`，按此完整发送并接收。请求语义区之后补零。其他两种长度只完成离线验证。 |
| 回复保留范围 | 只保留消息头和状态产生的三个字段；其余传输内容丢弃，不记录原始收包。不能假定原厂回复尾部都为零。 |

长度证据不只来自描述符：`0x400040ac` 按速度设置 `0x40032948` 为 `64/512/1024`；发送函数 `0x400044a8` 在复制和提交控制 IN 缓冲时都取这个长度。描述符分别位于 `0x40017ce0`、`0x40030540`、`0x400304e0`。Full-Speed 描述符的 interface 编号为 `2`，其他两份为 `0`，因此不能硬编码所有连接都使用同一 interface 编号。

**已确认的副作用：**处理该读取时，`0x4000557c → 0x40005290` 会生成 `usbif_trace_event`（ID `0x047a`），源节点 `9`、目标 `iMX=5`，再进入正常消息传输。读取也使用 USB/DMA 队列。所核 getter 没有修改曝光、升级、传感器或联机模式，但这条操作会产生机内消息和诊断记录；不能称作纯被动查看，也不能保证完全不涉及下游控制器。

## 3. Linux Phocus 与诊断消息的边界

在 `msg2dbus` 中，`RawHandler` 对目标 `iMX=5` 的 `hostd_rx_event`（ID `4`）选择 `Bus::phocusService()`：`0x2251c` 比较消息 ID，`0x225cc` 取得服务名，`0x22408` 调用 `RawProxy::rawMessage`。这是实际分派证据，仍不能单凭它补上 FX3 到该进程的全部运行链路。

`phocus-daemon` 的 `RawMessage → 0x47204/0x47208` 进入 `apps_messaging_tunnel::receive_async`，完成包回调 `0x47e74` 交给内层解析器 `0x50e34`。内层包含 16 位计数、8 位种类和后续消息体；种类 `2` 在 `0x484c0` 调用 `ReadParameter`（`0x55964`）。后者按参数 ID `2…73` 分派，部分项直接进入不支持分支；不能把这整个范围当作查询白名单。种类 `9` 当前只发出 `Not implemented (deprecated?)` 警告。

回复回调 `0x461e4` 先调用 `Bus::sucService()`，再调用 `RawProxy::rawMessage` 并等待 D-Bus 返回。服务文件分别配置 SUC `/dev/ttymxc1`、460800；FARM `/dev/ttymxc2`、921600。它们都是相机内部 UART；本报告没有打开任何串口。

普通 Phocus 会话涉及状态变化：`DoAction` 内 `0x66b50` 调用 `SystemManagerProxy::setTetheredMode`，另一路 `0x66b94/0x66b98` 修改并通知 `HasselbladHost` 状态。初始化与 USB 断开处理也涉及 FX3 供电请求及连接清理。因此启动正常客户端、进行身份登记或执行清理动作，不能自动归入上面的单项 FX3 读取。当前没有调用这些路径。

## 4. 错误、升级状态与日志还缺什么

| 目标 | 已核实 | 尚未核实 |
|---|---|---|
| 当前错误报告 | 内部消息 `farm_report_error_event=908`、`suc_report_error_event=909`，各有 3 字节体；已有 SystemManager 的本地通用错误 1000 生成路径。 | 电脑端读取当前/历史错误队列的合法请求、事件订阅入口和返回契约；没有真实错误事件可用于定位故障控制器。 |
| 机身控制器升级状态 | `SucHandler` 的元对象方法 `module_program_GetCbUpgradeStatus` 对应 `0x279c4`，构造请求 `0x0478`，交给公共请求处理并设置 5000 ms 时限；表中回复 `0x0479` 有 1 字节体。 | 对应 SUC 目标 handler 的完整副作用、数值含义、外部 `usbhost` 请求的处理与回复条件。当前不纳入读取白名单，更不是整机升级结果。 |
| 现有诊断日志 | 已有正常日志收集及写卡链；FX3 状态读取本身会产生一条内部 trace。 | 从外露 USB 读取现有 Linux 日志文件的正常入口。内部 trace 发送不是已有日志下载；不能用它绕开失败的写卡路径。 |
| 错误态可达性 | 在已核 FX3 本地 handler 中没有按屏幕错误 1000 拒绝该请求的分支；本轮实际读取得到匹配回复和状态 `1`。 | 当前相机的实际固件版本、SUC/FARM/Linux 后台消息链健康及具体错误报告者；FX3 的成功回复不能证明这些。 |

## 5. 本轮授权、实测与停止边界

来源任务转达用户已将第一代 X1D 开机，并明确要求“你可以让它去试一下通过 USB 去查吗”。本次仅使用这一轮 X1D 授权，没有沿用 X2D 的实测、协议或授权。

01:07:49 的 Windows 被动快照发现一台 `2756:0002 / Hasselblad Digital Camera`，Class `Image`、Status `OK`、ProblemCode `0`，服务为 `WinUSB`；系统驱动 `WinUSB.SYS` 已在运行。已读当前 `oem95.inf`，它明确绑定该 VID/PID，公布的设备接口 GUID 与工具枚举一致。未改动驱动。

[单次读取工具](../tools/read_usb_link_once.py)独占打开这一目标；使用 `WinUsb_Initialize` 取得描述符缓存并初始化主机策略，查询当前 alternate/interface/pipe，核对接口 `0`、alternate `0`、四个 bulk 端点及 `512` 字节最大包长。它核对自动清除 stall、恢复时复位端点和额外零长包均关闭，只设置本次主机 IN/OUT 的 `2000 ms` 超时。初始化的描述符/主机策略行为见 [Microsoft WinUsb_Initialize](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_initialize)，超时及默认策略见[官方策略说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-functions-for-pipe-policy-modification)。这不是纯被动枚举。

实际仅提交 **1 次应用层诊断请求**，完整写出 `512` 字节；读取调用 **1 次**，收到 `512` 字节匹配回复，状态 `1`（本地 USB 活动标志为真，SuperSpeed 标志为假）。没有超时或重试。枚举信息集、WinUSB 和设备句柄均正常释放，主机端整段流程约 `15 ms`；这不是相机内部响应精度测量。记录保留主机结果与已审查状态，未保存设备序列号或原始回复尾部。应用层提交数不统计 Windows USB 栈内部的描述符事务、底层包/NAK 或机内 trace。

本次已结束；结果文件以独占新建方式保留，同一文件不能用于自动重跑。未执行后续 USB 请求。固定原厂代码显示该读取会产生机内诊断事件，但**没有读取该事件实际投递、落盘情况**。

这次读取已经验证“控制请求能进 FX3 并得到回复”，其结果不足以选择刷写目标或恢复步骤。错误根因仍需原厂错误事件/日志，或完成上表中升级状态目标 handler 的核查。当前没有可推荐给故障机执行的写入、重启、节点重试或整机恢复方案。接下来按来源指令独立核查 SSH/Wi-Fi 入口；不把 USB 成功当作已有网络连接。

本轮有上述 **1 次应用层相机请求**，没有网络探测、照片/机内日志读取、串口、驱动修改、拍摄、固件操作或相机设置修改。没有修改冻结的 v1/v2/v3、共享 X2D 客户端、独立恢复核查目录、Git 历史或远端。静态审计 JSON 中的请求 `0` 只表示那个离线脚本自身未访问相机，实际请求单独记录在硬件 JSON 中。
