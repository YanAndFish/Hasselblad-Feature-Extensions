# Error 1000：界面解除、连接状态与恢复输入

2026-09-10。静态部分沿用官方 X1D-50c **1.25.0** 的固定缓存，没有执行缓存固件。随后按用户具体授权及来源任务核对，03:26:02+08执行了一次固定源文件摘要查询，累计硬件请求五次并已停止；根文件系统声明v1.25.0，三源文件匹配同版官方摘要，其他程序/控制器实际版本未核实。用户希望优先调查固件/系统问题，暂时恢复菜单交互，再由其人工恢复固件；这不是已证明具体固件损坏，也不授权自动升级。

## 当前结论

没有找到能通过已核正常接口临时隐藏不可确认的 Error 1000、同时恢复普通菜单且保留后台失败状态的办法。原厂错误页可以显示应急按钮，但这不解除错误，不恢复普通菜单。点击其中的 Retry 会实际进入更新流程，不能当作打开一个无副作用的恢复页面。

`UpdateNodes` 使用当前 Linux 中的控制器源固件。更新中断不能单独证明源文件已经丢失；完整源文件也不能证明目标控制器的编程通路可用。已完成FARM even/odd与SPC三份源文件的实机摘要校验，均匹配官方1.25；结果见[完整性校验报告](SOURCE_FIRMWARE_INTEGRITY.md)。上次升级失败步骤、其他重试输入和目标控制器Flash仍未核实。

## LinkStatus 的精确含义

`system-manager` 构造代码将三个 `LinkStatus` 对象绑定如下：

| 对象偏移 | 构造调用 | 服务与路径来源 | 日志名称 |
|---|---|---|---|
| `+0x88` | `0x23458 → 0x2abec` | `Bus::sucService / sucPath` | SUC |
| `+0xac` | `0x23488 → 0x2abec` | `Bus::farmService / farmPath` | FARM |
| `+0xd0` | `0x234b8 → 0x2abec` | `Bus::pwrctrlService / pwrctrlPath` | SPC |

构造器 `0x2ac6c` 将各对象 `+0x18` 的状态初始化为 1。`onPropertiesChanged`（`0x2aca8`）读取属性表的 `status`，在 `0x2b21c` 转为整数，变化时于 `0x2b25c` 保存并最终发出 `statusChanged`。实际固件版本另由 `firmwareVersion` 表的 `firmware_version` 字段更新到对象 `+0x1c`，并非把版本字符串比较结果直接填入这个整数。

`libappscommon` 的 `Bus::statusString`（`0x4ad54618`）给出了明确映射：

| 状态 | 原厂字符串 | `0x2a6cc` 检查结果 |
|---|---|---|
| 0 | Connected | true |
| 1 | Version unknown | false |
| 2 | Version mismatch | true |
| 3 | Disconnected | false |
| 4 | Manually switched off | false |

`0x2a6cc` 使用 `(status & ~2) == 0`，接受 0 或 2。因此第四次读取的 FARM/SPC=false **不能直接解释为版本不匹配**；已定义状态中它可能对应 1、3、4，也可能还停在没有更新过的默认 1。未知整数也会被拒绝。

`msg2dbus` 的 `LinkstatusHandler::onInterfaceStatusChanged(bool)`（`0x51d7c`）在接口恢复时将状态设为 1，并开始原厂版本请求；接口失去时设为 3，手动关闭状态 4另行保留。状态 getter `0x511ac` 在底层接口不可用时返回 3。它们区分了接口和版本信息，但第四次保存的布尔字段不足以反推其中哪一项。不能称为板损坏，也不能称为已经排除通信问题。

`allLinksUp`（`0x1fdd8`）只合并上述检查；`checkBootDone`（`0x20130`）和独立的实际/预期版本比较（`0x1ffbc`）另有流程。`failBootEnter` 的三行实际/预期版本仍只是可选后续证据，本轮未读取。

## 确认错误与只改界面的区别

| 做法 | 已核作用 | 能否用于本次菜单解锁 |
|---|---|---|
| `ErrorControl.ack()` / `CError::Ack(int)` | GUI 先检查可确认性；后端再核对当前 UID 与 canAck | 不能确认不可确认的 1000 |
| 写 `currentError` / `ErrorControl.code` | 所查 Qt 元属性为只读，没有写分发 | 没有正常写属性方案 |
| `clearCurrentError` / `setCurrentError` | C++ 内部函数，改变后端当前错误 | 不属于独立界面隐藏接口，也不是暴露的 MOC 方法 |
| 只把错误遮罩设为不可见 | 主界面和焦点仍受 error 状态控制 | 未实现，不能证明恢复交互 |
| 强制进入升级准备 | 改系统状态并涉及升级协调，内部会清当前错误 | 不能拿来模拟“仅打开菜单” |
| 修改 QML/进程或屏蔽错误上报 | 需要改变运行中 GUI 或后端行为 | 没有已核实的可逆实施路径，本轮未实施 |

后端 `CError::Ack` 在 `0x4ad714d8` 比较传入 UID；在 `0x4ad71544` 将 canAck 转为布尔，false 于 `0x4ad71560` 返回，只有 true 才调用空表形式的 `setCurrentError`。参数是当前错误 UID，不是简单传入错误码 1000。`CError` 元对象只列报告/通知和 `Report`、`Ack`；`currentError` 属性标志 `0x95001`，分发仅支持读取。内部 clear/set 的符号存在不等于可经 D-Bus 调用。

GUI `ErrorProxy` 元对象的 `code`、`isAckable` 等属性也只读。`ack` 分发 `0x8d2a0 → 0x78a94`，开头检查对象可确认标志，false 直接返回。错误1000的强制遮罩不是普通可确认 `ErrorPopup`。

`TouchWindow.qml:146–157` 中不可确认错误优先于 updating/update_finished；`:1668–1687` 的 error 状态隐藏 `main_screen`，加载 `PopoverError`，保持活动与焦点。普通画面其他分支也检查 `ErrorControl.code`，因此只移除一个可见标志不足以建立菜单可用性。

`SystemManager::prepareUpgradeEnter` 的 Qt 方法索引35，经 `0x38110 → 0x384e4 → 0x226cc`；其中 `0x22af0` 调用 `clearCurrentError`。这是原厂实际升级准备流程中的后端改变，有助于解释升级UI如何可能取代错误页；不是可单独拿来清除失败并回到普通菜单的恢复承诺。仍须通过系统升级准备条件，不能绕过检查。

## 原厂错误页的更窄入口

固定镜像 `PopoverError.qml` 中，感叹号图标的 `MouseArea` 只执行 `showFWUpdateRetryCounter++`（78–80行）。计数初始0；达到5次时显示：

- `Firmware ` 加 `System.versionID` 的版本文本（54–57行）。
- `FW Update Retry` 按钮和 WiFi 按钮（188–213行）。

**仅点击图标五次在这段代码中只改变当前 QML 对象的内存计数。** 它没有调用 Ack、清错、配置写入或升级；错误和后台失败继续保留。它不恢复普通菜单，也不提供通用固件文件选择页。这里没有计数回退按钮；只有该对象重新创建时回到0，没有核实当前故障下无需重启即可立即隐藏这些按钮的方法。实际机身版本及该入口响应尚未验证。

错误页 Retry 的196行直接调用 `Upgrader.upgradeNodes()`，没有普通设置菜单那层确认。WiFi 按钮208–209行写 `WIFI_power`，也不属于上述只显示按钮的动作。本报告不安排点击任何更新或WiFi按钮。

普通 `SettingsGeneric.qml:599–603` 的 `checkForUpdate` 才会加载 `UpgradeCheck.qml`；该页搜索状态调用 `Upgrader.startSearch()`（251行），确认候选后调用 `startUpgrade(uuid)`（325行）。它有USB连接（242–245行）及电池状态（234–239行）限制。解除遮罩不等于这些条件或存储候选来源已满足。

## 机内源文件与实际编程通路

已核 `program_nodes.sh` 不删除选中的源载荷，也不执行 Linux 根分区重装。节点写入目标与 `/lib/firmware/hbl` 源文件是两处；不能从中断推导源文件必然丢失。Linux 整包安装属于独立的 `hbl-upgrade` 流程。

`program_farm.sh`（SHA-256 `2d3cf8bf120969961738d24af6c18aefeb3181d908146a78eb2d898b674ce4fb`）：先取得 even/odd 文件大小，要求各小于8MiB；随后设置FARM复位、重新加载NOR驱动并要求mtd3/mtd4各报告`08000000`，经`flashcp`写入。它不以正常FARM应用链路为true作为此脚本入口条件。脚本自身会改变GPIO/驱动与Flash，不能运行它来进行只读“可用性测试”。

`program_spc.sh`（SHA-256 `3f642df18f400a47fb325774591d58c292a0a2d455b5da0ddcd02c8538da8eb6`）：停止`msg2dbus-farm`，控制FARM进桥接模式，最多50次每次1秒等待GPIO93；再通过SUC切换传感器供电，经串口的原厂工具写SPC。主循环最多3轮，`RESTART_FARM_AFTER`默认0。因此SPC恢复依赖FARM桥接、SUC控制、串口与目标写入条件；源文件完整不能替代这些条件。SPC在`program_nodes.sh`注释中明确为 Sensor Power Control。

这些是固定1.25代码的条件，不是当前相机已通过的状态。未停止服务、操作GPIO/串口、探测节点或运行program。

## 上次失败步骤的证据缺口

`program_nodes.sh` 仅在主流程末尾执行 `journalctl -b -o short-precise > /media/data/logs/upgrade/upgrade.log`。若运行中途断电，该文件可能未生成，或仍保留较早一次结果。不能把它直接称作“上次中断的日志”。当前启动journal也未必含前次启动的更新信息。

有限筛选 Start/End 节点更新、FARM桥接失败等固定消息可提供线索，但没有结束行不能证明精确中断点；还需核对记录所属运行和时间。尚未读取这个文件，没有安排整包日志导出。当前优先核对源输入，未提出新的升级日志硬件命令。

## 已获核对并执行的唯一读取

以下218字节常量最初作为提案提交，随后来源任务明确核对通过，完成8项离线模拟后仅执行一次。它取得根文件系统声明版本与三份固定源文件摘要：

```text
/bin/grep -E '^VERSION="v[0-9.]{3,11}"$' /etc/os-release;cd /lib/firmware/hbl&&/usr/bin/sha256sum farm/bootimage_even-wedge.bin farm/bootimage_odd-wedge.bin power-control/power-control.bin|/bin/grep -oE '^[0-9a-f]{64}'
```

命令218 ASCII字节。`/usr/bin/sha256sum` 在原包alternatives指向已核BusyBox1.23.2的`/bin/busybox.nosuid`。主机只接受严格一条 `VERSION="vA.B.C"`（三段各1–3数字）及随后恰好三行64位小写十六进制，顺序为FARM even、FARM odd、SPC；总输出不超过219字节，须有完整换行、NUL及全零尾部。少一行则整组摘要位置未知，不猜哪个文件缺失；空、格式不符或截断均为未知，不保存其他stdout/stderr。

复用已核的单OUT、6秒共享接收期限、最多两次IN和异常即停；没有修改旧USB封装。相机侧仍有原厂sutest初始化/可能的服务激活及固定shell进程副作用，新增读取仅涉及声明版本文件与三个固定源载荷。没有机内硬截止；主机超时不取消摘要进程。原包三份源载荷合计7,957,343字节，实机文件大小与符号链接目标未预先核实，这个限制经来源任务明确接受。实测一次OUT512、一次IN512，主机469ms，匹配有效回复且全部句柄关闭；没有上传、替换或写回任何相机文件。

官方1.25固定源文件对照：

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `bootimage_even-wedge-v1.25.0-13075-c9bb91d.bin` | 3954444 | `e0575442e0831f0ba6cd65a5beedfc64bff2c992182220b7832a27e49928cac0` |
| `bootimage_odd-wedge-v1.25.0-13075-c9bb91d.bin` | 3954444 | `2c1ff341653f6548c04c0cfb10db7e864887135f259e278066de49ae1c7967be` |
| `power-control-v1.25.0-14703-9b140c9.bin` | 48455 | `dc0a77dd46f7e07a5640fb9407e077b8f544871d007f9c3fa4233ea5fc8e7616` |

原包 `/etc/os-release` 的 `VERSION` 是 `v1.25.0`，`VERSION_ID` 是构建号42；`/etc/version` 是构建时间戳，不可当作固件版本。即使实机声明1.25且三份摘要匹配，也只能确认这些源载荷字节匹配；不能证明全部Linux程序、运行中组件或控制器Flash匹配。若声明其他版本，必须取同版官方输入再核对，不能以不等于1.25摘要判损坏。

## 来源与边界

固定系统管理器SHA-256 `7bb4e33f13417f7c15dfcbfbb29d552f1c386429bad52da030acde489dc4dba5`；libappscommon `2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263`；msg2dbus `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1`。GUI/QML与脚本均来自[固定基线清单](baseline-manifest.json)及同一官方CIM。

前次实测与历史性限制见 [USB有限日志诊断](ERROR1000_USB_DIAGNOSIS.md)；原厂更新分流见[恢复入口](RECOVERY_ENTRYPOINTS.md)。用户人工恢复的目标保留，但本轮没有执行Retry、UpdateNodes、清后台错误、伪造连接状态、写设置、重启或试拍。
