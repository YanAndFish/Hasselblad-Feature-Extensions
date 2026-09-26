# 第一代 X1D 故障恢复入口核查

记录日期：2026-09-10（北京时间）。静态对象为官方 X1D-50c **1.25.0**；当前机身版本、引导器与运行状态没有读出。所有结论不套用 X1D II、X2D 或其他机型的设备地址。原输入见 [baseline-manifest.json](baseline-manifest.json) 与 [error-input-manifest.json](error-input-manifest.json)。本阶段没有建立相机会话、探测端口、读取照片/机内日志、执行包内程序、启用接口或刷写。

**目前没有证实一个能在当前错误状态下从电脑强制重装系统的入口。** 已找到原厂整包更新、控制器重试、设置重置，以及引导器和服务的具体代码；还缺 X1D 板级入口如何从外部到达、当前量产机是否允许、需要什么匹配的恢复载荷。这是可达性缺口，不是“没有源码所以不能研究”，也不是断定无法修复。

## 当前故障事实与解释范围

用户报告开机后菜单约能操作 5–6 秒，随后出现错误 1000；反复取装电池无效。错误页下普通按键无效果，关机键有效；最新确认不用取出电池也能正常关机。Save Logs 曾短暂出现“不要取出存储卡”，再次查看卡根目录仍没有新文件。

`ErrorGeneral=1000` 是非可确认的通用系统错误，不指向单一坏件。错误状态隐藏普通主画面，但保存日志触摸入口默认仍保留；不能把 `FilterNone` 误译为“吞掉所有按键”。短暂等待提示也不能证明日志打包或写卡成功。详见 [错误与日志证据](ERROR1000_LOG_EXPORT.md)。没有再次安排取电池、Save Logs 或其他硬件试验。

静态服务中存在从系统启动计算的 10 秒定时器；它与用户从菜单可见时计的 5–6 秒不是同一个起点，不能据数值相近把故障归因于某个定时器。没有当前日志或事件记录，尚不能确定最初失败者、升级实际走到哪一步。

## H6D 线索与 X1D 的共同代码

[2019-07-16 的 H6D 用户记录](https://www.chassimages.com/forum/index.php?topic=90515.5350) 转述客服针对内部生产版退回官方版的建议，涉及卡上 H6D CIM 和服务菜单。它有对照价值，但属于用户转述，不能当作 X1D 的官方维修流程或成功恢复验证；帖子也没有把各菜单动作的底层调用完整列出。

X1D 原包确实存在共用实现证据：同一个 `victory-gui` 内含普通、Wedge、A6D、CFV 四组菜单资源，服务菜单分别列出 `checkForUpdate`、`defaultSettings`、`fwUpdateRetry`；同一个 `TouchWindow.qml` 还包含 `prodinfo.isNewH6DisplayQml()` 分支。`program_nodes.sh` 明确区分 Wedge、Victory、H6D-MS 等板型，并选择不同 FARM、FX3、SUC 文件。因而不能仅因案例是 H6D 就丢弃线索，也不能把“共用框架”扩大成跨机型固件互换或所有版本处理器相同。没有下载 H6D 镜像，也没有做 H6D 1.21 与 X1D 1.25 的逐字节对比。

| X1D 1.25.0 入口 | 实际调用与载荷 | 与当前故障的关系 |
|---|---|---|
| Reset all Settings | `ConfirmDefaultSettings.qml:20 → configstore.resetDefaultSettings(bool)`。GUI `0x850b4 → 0x4a13c` 发送配置服务同名方法；配置端 `0x2d6a0 → 0x23560 → 0x1d564`，可见配置/预置文件处理和删除分支 | 是改变设置的独立流程，没有选择卡上 CIM；不能等同重新安装 Linux。未执行，也未将其列为已证修复手段 |
| Firmware Update Retry | `SettingsGeneric.qml:693 → Upgrader.upgradeNodes()`；错误页另有直接同名调用。`UpdateNodes` 进入引擎，准备完成后运行 `program_nodes.sh`，工具和载荷根均为 `/` | 从当前系统 `/lib/firmware/hbl` 选择控制器文件。该路径没有卡上 CIM 的 UUID/路径选择，所以“卡上没固件”不能排除它重写控制器 |
| Check for Update / Update | `UpgradeCheck.qml:251` 搜索候选，确认后 `:325` 向 `startUpgrade` 传入选中项 UUID；引擎读取并解包 CIM，再走整包脚本 | 与 Retry 独立。整包脚本涉及另一组 Linux 分区和控制器写入；没有证实当前错误状态下能正常完成 |

Retry 的完整调用与脚本参数见 [firmware-retry-static.json](validation/firmware-retry-static.json)。普通 CIM 的校验、双分区行为与限制见 [安装可行性](INSTALLATION_FEASIBILITY.md)。论坛中的合并措辞不能推翻本版 X1D 的实际分流，也不足以证明这条 Retry 会安装卡上整包。

错误 1000 的非可确认弹窗在 UI 状态选择中优先于普通更新页面，隐藏主菜单；错误页保留专门的日志/重试处理器。Retry 引擎入口没有按“1000”直接拒绝，但仍要等系统进入 `StateUpgrade` 并完成准备。升级器 `0x3d1b4–0x3d1c0` 对系统状态 3 作检查，之后才可能继续。可调用、能通过准备、真正开始写入和写完是四件事；不能根据转圈或按钮存在判断当前阶段。普通更新 UI 另外有 USB 连接与电池状态限制。

## 引导器、制造入口与外露 USB

包内 `uboot.bin` 的 SHA-256 为 `bad3ab600873fa78adb7cc06190ff092052ff11b20f012da9c18cf22cddba8d3`。正常 1.25.0 更新脚本不刷这个引导器，因此下列结果仅属于包内版本。

- 默认 `bootcmd` 从 eMMC 的 boot/root 分区启动，带升级试启动选择；`bootdelay=0`、`preboot` 为空。默认命令没有调用 USB 恢复变量。
- `usbboot` 与 `usbupdate` 环境项分别从 USB 存储读取 `loader.hbl` 和 `hblupdate.img`，后者解释载入的脚本。这里的 `fatload usb` 是引导器读取 USB 存储，不能翻译为“电脑连接相机即可推送恢复包”。尚未找到这些专用载荷或进入该流程的 X1D 外部操作依据。
- 固定命令表 `0x1783a1c0–0x1783aa48` 共 78 项，含 `usb`、`usbboot`、`bmode`，没有 `fastboot`、`dfu`、`ums`、`sdp` 表项。这仅限制此表，不证明芯片 ROM 没有下载能力。
- 自动启动在零延时下仍调用 `tstc/getc`（`0x178047e0`、`0x178047f0`）。已追到控制台 stdin/serial 路线，没有绑定到机身某个按键。对应 [U-Boot 上游代码](https://raw.githubusercontent.com/u-boot/u-boot/v2015.07-rc1/common/autoboot.c) 可解释语义，不能据此提供机身组合键。
- `bmode` 处理器可调用启动模式设置与复位；但本包参数表的有效初始化没有闭环。根据 [上游 `cmd_bmode.c`](https://raw.githubusercontent.com/u-boot/u-boot/v2015.07-rc1/arch/arm/imx-common/cmd_bmode.c)，参数是否可用取决于注册的模式表，不能仅因命令名存在承诺 `bmode usb` 可用。
- Wedge Linux DTB 的串行输出指向 `serial@02020000`，i.MX USB 节点 `usb@02184000` 为 `okay`，没有显式 `dr_mode`。DTB 只描述 Linux 使用的硬件节点，不能确认外露插座布线、ROM 启动条件或维修触点位置。

X1D 的 FX3 与主 SoC 是需要分开处理的证据：原厂 `program_fx3.sh` 先停有关服务，用 GPIO 控制 FX3 电源/EEPROM 总线，再经机内 I²C EEPROM 写入其镜像；`program_nodes.sh` 为 Wedge 选择 `fx3_wedge.bin`。`phocus-daemon` 使用 `UsbifProxy` 的链路状态，而不是直接证明 i.MX ROM USB 端点外露。这些支持机内有独立 USB 控制器和独立固件的判断，**仍未证明所有外露 USB 数据线必经 FX3，也未证明可切换直达 i.MX ROM**；缺板级接线或匹配的原厂制造资料。FX3 自身的 USB 启动能力见 [Infineon AN76405](https://www.infineon.com/assets/row/public/documents/24/42/infineon-an76405--ez-usb-fx3-fx3s-boot-options-applicationnotes-en.pdf)，它不等于主 Linux 系统的恢复入口。

[NXP 开发板说明](https://www.nxp.com/document/guide/getting-started-with-i-mx-6quadplus:GS-RD-IMX6QP-SABRE) 与 [NXP mfgtools 示例](https://github.com/nxp-imx/mfgtools/wiki/Example) 解释了片内 ROM 和制造下载的通用能力。对 X1D 还必须分别证实：外部可达链路、板上启动条件、量产机允许状态、匹配板型的 RAM loader 及写入流程。当前四项均未闭环；没有据开发板资料猜按键、接线、熔丝或串口步骤。

Linux `rescue.service` 需要已运行的 Linux/sysinit 和控制台登录环境；它不是错误页可以直接进入的 ROM 恢复模式。包内双分区启动代码也不能保证 FARM、SUC、FX3 等控制器都随 Linux 分区一起回退。

## 端口：静态配置与当时实际可达性

2026-09-09 23:33:55+08 的 Windows 只读 PnP 快照发现 `Hasselblad Digital Camera`、Image 类、状态 OK，公开 VID/PID 为 `2756:0002`，未保存序列号。较早 23:27 的快照无匹配设备；这两次不同的观察不能合并成“始终不枚举”。设备名称未直接标出型号，枚举正常也不证明控制器全部健康。

23:41:22+08 的只读网卡关联检查没有找到归属于该相机的 USB/RNDIS 网卡；对应候选 IP、路由和邻居集合为空。唯一实际 Up 的物理网卡为电脑的 Intel I225-V，不能当作相机网络口。**没有确认相机 IP，所以没有探测 22 或其他端口，不能报告当前端口开或关。** 未扫描局域网，也未套用另一任务的 X2D 地址。

| 固件内证据 | 可得结论 | 不能推出 |
|---|---|---|
| `sshd.socket: ListenStream=22, Accept=yes`；由 `verylate.target` 启用 | 固定镜像配置了 SSH TCP 22；连接还可能触发 per-connection 服务及缺失 host key 的生成 | 当前机身 22 已开放、已有合法登录凭据、单纯建连绝无写入 |
| `phocus-mobile-server.service -p 50001`；程序 `0x20920` 调用 `QTcpServer::listen` | 固定镜像有 TCP 服务及 50001 启动配置 | 当前服务已监听、协议握手无联机副作用或能用它恢复系统 |
| `verylate.timer: OnStartupSec=10`；`usb-modules` 加载 `ci_hdrc_imx` | 镜像含延迟服务启动与 USB 驱动配置 | 外露 USB 当前提供网络、出现菜单 5–6 秒后错误由它导致 |

静态 `bridge.network` 的地址配置与 `usb.network` 的 DHCP 配置不是当前相机地址，未据此猜测连接。没有发现相机 IP 接口时，继续猜端口不能弥补板级可达性缺口。

## 本阶段交付与尚缺的证据

[audit_recovery_entries.py](../tools/audit_recovery_entries.py) 已实际运行通过：15 条调用、78 项固定引导器命令、16 个原包输入哈希与 QML/服务条件，报告为 [recovery-entries-static.json](validation/recovery-entries-static.json)。这些是静态证据核查，不是恢复演练。

当前可以确定三类菜单各自做什么，以及现有网络和引导线索为何尚不能连成电脑恢复路径。要继续定位本机，需要当前日志/错误事件或明确针对第一代 X1D 的原厂维修入口、载荷与板级条件；现有屏幕和卡根观察不能替代它们。此阶段收尾，不再重复无新证据的相机操作。

Full JPEG 与 920K 像素预览仍为独立目标；冻结的 v1/v2 候选和审核证据保持原样，四项审核缺陷待后续独立候选修复。没有把增强候选当作恢复镜像，也没有标记为可安装。
