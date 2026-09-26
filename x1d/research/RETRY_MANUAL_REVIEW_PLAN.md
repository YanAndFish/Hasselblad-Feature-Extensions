# Error 1000 下原厂 Retry：人工恢复审阅方案

2026-09-10。目标是恢复第一代 X1D 的正常工作。本文给出原厂错误页入口、准备流程、实际写入范围与失败边界，**不是已经执行或验证成功的维修流程**。本轮仅分析本地官方 **1.25.0** 镜像，新增相机请求0；此前累计6次读取均已结束、句柄关闭。没有代点按钮、执行升级或清除错误。

## 给操作人的步骤与停点

1. 保持在当前 Error 1000 错误页。无需先进入普通菜单，也无需用 SD 卡上的 CIM 来显示此入口。原包的入口是点击错误页中央感叹号图标累计五次；预期出现 `Firmware …` 文本和 `FW Update Retry` 按钮。只显示按钮的代码仅改变 QML 内存计数，不清除错误，不开始升级。**这一响应尚未在本机验证；若没有出现就停在这里，不能改猜其他按键或接口。**
2. 显示按钮后先停下核对。按钮出现不等于恢复条件通过；`FW Update Retry` 是直接开始实际更新的按钮，没有普通更新页的再次确认。相邻 WiFi 按钮会写设置，不是恢复准备步骤。五次点击也不恢复普通菜单；没有已核实的计数回退按钮。
3. 在决定实际恢复前，确认机身使用可靠、充足的电池供电，并在**开始更新前**断开 USB。这里不再要求重复尝试菜单、取装电池、Save Logs 或拍摄。普通更新页明确提示低电量和 USB 条件；错误页 Retry 没有这层提示，不能依赖按钮自动替人检查。没有从本分支核实到统一的电量百分比或电压阈值，不编造“必须50%”之类数值。
4. 本轮已经证实 Linux 声明版本为 `v1.25.0`，FARM even/odd 与 SPC 三份源载荷逐字节摘要匹配官方同版文件。这只消除了这三份**源文件**的完整性疑点。实际点击前仍应审阅下文列出的其余输入与编程通路缺口，尤其这是全节点重试而非仅修复 FARM/SPC。任何新增机内读取应先形成固定命令与验证方案，另经来源任务核对；本文不安排自动追加读取。
5. 只有用户理解写入范围并决定执行该原厂恢复流程后，才由用户人工点击一次 `FW Update Retry`。这一步会进入系统状态转换、控制器供电切换和 Flash/EEPROM 写入；不能把它当作“看看下一页”。本文及已完成的只读授权不代表代理获准点击或发送 `UpdateNodes`。
6. 开始后等待原厂界面明确给出完成、失败或重启指示。界面清掉1000、转圈、USB消失或显示某个百分比，都不能独立证明全部节点写入成功。运行中不拔电池、不以断电退出、不重复点击，也不启动另一套恢复程序。若停滞或报错，记录当时可见文字与所处阶段；本方案没有经验证的强制中止时限或一键回退操作。

**当前可交付的是上述可审阅方案；实际恢复未执行、未证明成功。** 硬件完好是用户当前判断，不是本轮检查已经证明的结论。无需通过伪造 LinkStatus、清后台错误或修改 GUI 来进入这条原厂错误页分支。

## 点击后实际发生的流程

| 阶段 | 官方1.25代码证据 | 含义与限制 |
|---|---|---|
| 显示入口 | `PopoverError.qml:30,54–57,78–80,188–196`；`showEmergencyButtons` 默认true | 五次图标点击只累加计数；Retry直接调用 `Upgrader.upgradeNodes()` |
| 提交请求 | GUI `0x891fc → 0x53854`，`0x53914 → CUpgrade::updateNodes`；后端 `0x543e0 → 0x1cc3c → 0x3c10c` | GUI拒绝重复的 processing 状态；不是通用文件选择器 |
| 等系统就绪 | `0x3c1f4–0x3c210` 设置 ReadyForUpgrade，检查系统状态3；另有状态回调 `0x3d1b4–0x3d1c0` | 需要系统进入升级状态；请求回复不等于已经写入 |
| 系统升级准备 | `system-manager::prepareUpgradeEnter`，`0x226cc` | 连接完成通知，清当前错误；检查 `fhStatus` 是否为15，不是15则请求设置15并等待 `fhStatusChangeDone` |
| 请求 FARM active | `0x22be4 → putFarmToActive(0x1ca2c)`；`0x1cae4 → 0x2c230` | `PowerClientMonitor` 发送 `DoTransition(0)`；`transitionFinished(bool)` 连接无参 `prepareUpgradeDone`。此连接本身不证明底层转换成功 |
| 节点准备 | 引擎 `0x3be78` 传true给 `PreUpgrade(0x40bec)` | 包含内核模块文件准备、经SUC关闭传感器板供电、定时等待、链路关闭及 FARM 准备关停，再恢复供电。这是设备状态改变，不是纯检查 |
| 原厂编程 | `PreUpgrade::done → Engine::preUpgradeCompletedUpdateNodes(0x36db8)` | 启动 `systemd-cat -t upgrade /usr/bin/program_nodes.sh / / 1`；两个 `/` 指当前系统的工具与源载荷，不从SD重新选择CIM |

系统管理器的具体绑定经 GOT 核对：`0x52a98 → PowerClientMonitor::transitionFinished`，`0x52afc → SystemManager::prepareUpgradeDone`，`0x52b44 → fhStatusChangeDone`，`0x52d40 → putFarmToActive`。`0x2815c` 属性设置器的实际字符串为 `fhStatus`。不把数值15自行命名为某个未核实的物理模式。

## 原厂“失败后继续”是恢复策略的一部分

Retry 向 `PreUpgrade` 传入true，保存在对象 `+0x0c`；它并不要求所有准备检查通过才继续：

- 关闭传感器板供电的 D-Bus 请求失败时，`0x41880–0x41888` 检查该标志，true进入继续分支；随后配置6000ms定时器。这是代码计时，不是实测等待精度。
- FARM 准备关停回调 `0x41e60` 包含失败后继续处理；GPIO93等待最多50次、每次100ms后仍未达到1时，`0x41b7c–0x41b84` 的该标志允许进入后续供电流程。GPIO不存在等其他分支仍可失败，不能概括成任何错误都被忽略。
- 供电回调之后还有 SUC/FARM/SPC 链路状态处理；`0x4156c–0x41574` 在相应失败时允许继续，固定字符串明确为 `One of the links could not be switched off. Continuing anyway.`。
- `0x40d4c` 最终按传入布尔发出done或error，并清此标志。这里的done表示准备流程结束，不是所有硬件健康证明。

`program_nodes.sh` 的第三参数又设为1。即使 FARM 写入返回失败，后续 SPC、FX3、触控、RTC处理与SUC仍可执行；脚本累计非零结果并在末尾返回。不能把“FARM失败”理解成全流程已停止，也不能在进度继续变化时断电。

## 实际写入范围与输入缺口

| 顺序 | 输入/动作 | 已知情况 |
|---|---|---|
| FARM（进度设20） | 当前 `/lib/firmware/hbl/farm/bootimage_even-wedge.bin`、`bootimage_odd-wedge.bin` 写NOR | 两源文件实机摘要匹配；目标NOR内容及实际写入能力未测 |
| SPC（设40） | `power-control/power-control.bin`；经FARM桥接和SUC供电控制编程 | 源文件摘要匹配；桥接、串口、目标Flash能力未测 |
| FX3（设60） | `fx3/fx3_wedge.bin`，由 `program_fx3.sh` 处理 | 此源载荷本轮未做实机摘要核对；原脚本会停服务并控制USB芯片供电/EEPROM总线，连接可能中断 |
| 触控 | `program_touch.sh` 更新触控控制器设置 | 当前脚本、配套输入及执行状态未验证 |
| RTC | 读取RTC，年份小于1970时写系统时间和RTC | 不是固件源文件；重试可能改变时间 |
| SUC（设80） | Wedge使用 `su-control/camera-control.bin` | 本轮未核实机源摘要；先设置autostart，再检查USB，后调用原厂编程脚本 |

上述进度值在动作**之前**设置，不是写入完成百分比或准确故障位置。普通更新的 `UpgradeCheck.qml:234–245` 检查电池状态和USB；脚本的USB阻止条件则是 `checkUsbConnected=true` 且 `usb_vbus_present=true`。没有读取当前开关值，不能保证插USB时一定会阻止所有写入；尤其SUC之前的节点可能已经执行。方案因此要求实际更新开始前拔USB，不安排修改检查开关。

另外仍未验证当前 `victory-gui`、`system-manager`、`upgrade-daemon`、编程脚本和工具的实际字节是否等于所分析的官方版本。Linux版本声明及三份源摘要不能替代整条恢复链完整性核对。离线能还原正常意图，不能用只读检查完整证明目标Flash可擦写。

## 失败后能退回到哪里

显示入口阶段没有Flash写入；停在该页即可保留错误诊断。点击Retry之后，不存在本文已验证的事务式撤销：Linux双分区不保证控制器固件一起回退，当前源载荷保留也不代表目标Flash仍完整。

`program_nodes.sh:133–162` 对SUC有特殊失败处理：特定结果会再次调用编程脚本，随后仍失败可调用 `erase_suc.sh` 并报告SUC状态未知。这是明确的原厂代码分支，不能把全节点Retry描述成无论失败都能自动恢复原状。`program_spc.sh` 本身也有最多三轮尝试；这些内部尝试与用户再次点击是两回事。

末尾的 `/media/data/logs/upgrade/upgrade.log` 来自当前启动journal，并非每步即时落盘；中途断电时可能缺失或陈旧。若恢复失败，先保留当前画面及已知过程，再选择与失败阶段相匹配的有限诊断或原厂维修方案；不能仅从没有日志、USB重枚举、普通菜单短暂出现推断已恢复。

## 来源与验证范围

本轮只读解析并核对输入摘要、Qt资源、ARM调用与分支，未执行任何包内程序。官方1.25固定输入：

- `victory-gui`：`d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`
- `system-manager`：`7bb4e33f13417f7c15dfcbfbb29d552f1c386429bad52da030acde489dc4dba5`
- `upgrade-daemon`：`aa62f9e03208d2306c0890fc9d5d9c522569359922a659060da270da381c8d0c`
- `libappscommon`：`2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263`
- `program_nodes.sh`：`8f889cd348556810bfc55b11a370d3d173be2185fc2d5d808356241fb76a601b`

既有证据：[Retry调用核查](validation/firmware-retry-static.json)、[界面与连接状态](ERROR1000_UI_AND_RECOVERY_INPUTS.md)、[三份源完整性实测](SOURCE_FIRMWARE_INTEGRITY.md)、[恢复入口及整包区别](RECOVERY_ENTRYPOINTS.md)。本说明补充新的准备分支证据，不覆盖或改写历史实测JSON。
