# Error 1000：USB 有限日志诊断

2026-09-10。本次只做获授权的有限诊断读取，没有执行恢复、Retry、UpdateNodes、设置修改或试拍。用户补充“不能拍照”为用户观察。

## 实测结果与解释

03:06:21+08 的唯一一次读取成功返回以下三条匹配历史记录，顺序保持原样：

| 顺序 | 类型 | 已取得字段 |
|---|---|---|
| 1 | 连接检查历史 | SUC=true，FARM=false，SPC=false |
| 2 | 连接检查历史 | SUC=true，FARM=false，SPC=false |
| 3 | 错误报告历史 | code=1000，category=5，severity=1 |

**已经取得启动过程中 FARM 与 SPC 尚未通过连接检查的历史线索；具体根因仍未确定。** 这些是本次启动中 system-manager 最近 200 条 journal 记录的最后三条匹配，不含时间戳，不能当作当前实时链路状态，也不能跨行断言唯一因果。尚不能区分通信、供电、初始化或固件问题，不能据此判定控制器硬件损坏。

一次 OUT 完整发送 512 字节，一次 IN 收到 512 字节，路由、命令52、操作字、本次关联标记、CRC、结果字段及输出白名单全部通过。主机计时156ms，无迟到FARM回复、无重试；枚举资源、WinUSB和设备句柄均关闭。不可变证据为 [实机JSON](validation/hardware/x1d-sutest-error-log-20260910-authorized-once.json)。

截至本次，X1D应用请求累计四次：FX3链路状态1；FARM RAM接收超时；sutest读取Linux RAM缓存0；本次有限日志字段。第三次缓存0仍无新鲜度保证，不证明Demo已关闭，也不作为1000病因。

## 与官方1.25.0静态证据的联系

实机固件版本未知。以下地址仅绑定官方X1D-50c **1.25.0**，不能冒充当前相机逐字节匹配。

- `Errors::ErrorGeneral=1000`，为非可确认通用错误。升级失败1001、FARM状态异常1005、介质缺失6005等另有编号，不能把1000直接翻译为SD卡坏或固件坏。
- `SystemManager::allLinksUp`（`0x1fdd8`）分别检查三对象，布尔结果由`0x2a6cc`的内部状态判定产生。日志字面量为`All links are not yet up:`，依次输出SUC/FARM/SPC；这是软件连接检查结果，不是电气测量。
- `checkBootDone`（`0x20130`）等待该连接检查；通过后还检查当前错误，普通流程遇到1000至5999的非可确认错误可发送`systemFault`。
- 普通`failEnter`在`0x1f668`选择1000、`0x1f670`选择类别5、`0x1f660`选择严重度1，再调用`CError::reportLocal`。本次数字与该分支一致，但不能仅凭相同参数排除其他报告者。类别/严重度的独立枚举名称没有在本次核定，不臆造名称。
- `onErrorReportReceived`（`0x1e84c`）的日志在`0x1e904/0x1e91c/0x1e934`输出错误码、类别和严重度，后面另含源文件、函数、行号。本次只提取前三个数字，不返回后面字符串。
- `failBootEnter`（`0x27470`）还会记录SUC、FARM、power-control实际与expected固件版本。版本不一致是可继续核对的候选；**本次未读这些版本，不能宣称已发现不匹配。**
- `/error`上的`currentError`仅保留错误码、UID和能否确认；不包含完整报告来源。因此没有再发一次只重复显示错误码的属性请求。

输入哈希：system-manager `7bb4e33f13417f7c15dfcbfbb29d552f1c386429bad52da030acde489dc4dba5`；libappscommon `2d834be366ba5a78cf370e679f28a5bb171b8dc5944fe2f69e81c2a170ddc263`。此前通用错误传播说明见 [错误与日志导出](ERROR1000_LOG_EXPORT.md)。

## 固定读取与验证边界

```text
/bin/journalctl -b -n 200 --no-pager -o cat _COMM=system-manager|/bin/grep -oE 'onErrorReportReceived [0-9 ]+|SUC: (true|false) FARM: (true|false) SPC: (true|false)'|/usr/bin/tail -n 3
```

这是已审阅的184字节唯一常量。未调用整份日志导出，不生成日志包、不写卡、不访问照片或账户文件。仅返回筛选后的数字/布尔字段，不保存原始journal、其他stdout或stderr。主机共享接收期限6秒，最多两次IN、单次OUT、异常即停；没有机内进程硬截止，主机超时不取消机内工作。

原厂镜像的`/bin/journalctl`为systemd225，SHA-256 `051d233648de4268a70e7c64a1aaae68779cf44e730f8b85b8ae4e6791bbf928`。`/bin/grep`和`/usr/bin/tail`的alternatives指向BusyBox1.23.2的`/bin/busybox.nosuid`，SHA-256 `f919c5f6252dabfe41f828e0a4a9239dca374aaa47b6844b6175d30fbdb2ad2c`。参数行为对照[systemd225手册](https://raw.githubusercontent.com/systemd/systemd/v225/man/journalctl.xml)、[同版BusyBox grep](https://raw.githubusercontent.com/mirror/busybox/1_23_2/findutils/grep.c)及[tail](https://raw.githubusercontent.com/mirror/busybox/1_23_2/coreutils/tail.c)。

[8项离线模拟](../CodeTests/usb_diagnostic/test_sutest_error_log_once.py)全部通过，包括严格字段、行数、长度、NUL/换行终止、空输出和截断未知、CRC/关联失败、超时停止及句柄关闭。初始化和CRC/封装复用[上一轮已审阅路径](SUTEST_RAM_CACHE_DIAGNOSTIC.md)，冻结原文件哈希，未改变旧实测记录。

管道退出码只能代表tail。因此`sutestResult=0`不证明journalctl和grep完整成功；有合法记录可以保留为历史证据，不能称为完整日志。空输出、格式不符或截断都视为未知，不当作没有故障。

## 不识别SD卡时的固件恢复可行性

刚打通的USB通路是在**已经运行的Linux**里执行固定命令，提供了进一步评估发起原厂机内流程的通信基础，尚未验证恢复成功或安全写入。

1. **UpdateNodes / Firmware Update Retry**：使用当前系统`/lib/firmware/hbl`中的载荷重编程控制器，因此不依赖SD上的CIM。这可能对应用户回忆的“从机内取固件”，但它不等于从ROM恢复整套Linux；故障状态下是否能通过`StateUpgrade`准备并写完仍未知。
2. **CIM整包安装**：需要整包载荷、完整校验、安装与回退流程；不能把sutest命令执行成功等同已具备这套恢复条件。本次未上传或安装任何包。
3. **SoC/FX3 BootROM**：属于其他启动阶段和不同控制器；当前正常Linux/FX3接口不证明ROM入口可达。既有板级缺口见[恢复入口](RECOVERY_ENTRYPOINTS.md)和[USB/SD矩阵](../recovery-review/20260910-usb-sd/USB_SD_MATRIX.md)，未重新开展泛启动搜索。

本次诊断读取完成后停止相机操作。剩余缺口是故障时相关控制器的具体初始化/版本/通信原因，以及对应原厂恢复流程在当前状态下的可行性；不能以重刷替代诊断。
