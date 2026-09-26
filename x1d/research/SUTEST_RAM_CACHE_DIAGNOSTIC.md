# 第一代 X1D：经 sutest 查询 Demo 对应的 RAM 缓存

记录日期：2026-09-10。范围是用户指定的第一代 X1D 故障诊断；图像、FullJPEG 与固件修改工作保持暂停。本说明不涉及 X2D 客户端。

## 本次实测结果

**USB 查询已成功，Linux 缓存 `ram_only_mode=0`；不能据此确认当前 Demo 已关闭。**

2026-09-10 02:50:30+08 执行唯一一次已授权查询：控制 OUT 完整发送 512 字节，一次 IN 收到 512 字节，回复头、命令号、操作字、本次关联标记、原厂 CRC、执行结果及严格输出格式均通过；等价文本为 `v i 0\n`。没有迟到 FARM 回复，没有自动重试。主机计时 141 ms，枚举资源、WinUSB 和设备句柄全部关闭。未保存原始回包。

不可变证据见 [本次实机 JSON](validation/hardware/x1d-sutest-ram-cache-20260910-authorized-once.json)。本项目累计 X1D 应用请求三次：第一次 FX3 链路状态 `1`，第二次 FARM RAM 查询接收超时，第三次为此处 sutest 缓存 `0`。没有改变前两次记录，也没有追加第四次请求。

本次证明该 USB 入口能够执行并返回此固定只读属性查询；没有取得缓存新鲜度、实机固件版本、Error 1000 根因或恢复成功证据。完成后停止相机操作。

## 查询对象与结论边界

目标是 `com.hasselblad.farm`、`/farm`、`com.hasselblad.farm.ram_only_mode`。官方 X1D-50c **1.25.0 静态基线**中，这个整数属性由 Linux `msg2dbus` 的 `FarmHandler` 缓存提供；实机固件版本仍未知。

- `FarmHandler` getter `0x58c20` 直接读取对象 `+0x140`，不会发送新的 FARM 查询。
- 构造函数 `0x346b4` 将该缓存初始化为 `0`。更新函数 `0x33d30` 接收值，来自消息 `558/0x22e` 或 `561/0x231` 的分派 `0x39900`。
- GUI 的 `ram_only_mode === Farm.RamModeRamOnly` 对应 Demo 的无存储指示；枚举 `Normal=0`、`RamOnly=1`。缓存为 `1` 可以表述为“Linux 缓存报告 RAM-only”；`0` 可能是初始值，不能据此断言 Demo 已关闭。
- 没有从该属性取得时间戳、同步成功标记或当前 FARM 状态的新鲜度。无论得到哪一个值，都不直接证明 Error 1000 的原因或已恢复。

## 唯一固定命令

```text
exec /usr/bin/busctl --system --auto-start=no --allow-interactive-authorization=no --timeout=2s call com.hasselblad.farm /farm org.freedesktop.DBus.Properties Get ss com.hasselblad.farm ram_only_mode
```

命令为 199 个 ASCII 字节，位于原厂 232 字节命令字段内，并保留 NUL 终止空间。它只发出一个 `Properties.Get`。成功输出只接受 `v i 0\n` 或 `v i 1\n`，以及字段剩余部分全零。

此前考虑过的 `get-property` 形式已撤销、没有发送。相机基线包含 systemd 225 的 `busctl`；[上游 v225 源码](https://raw.githubusercontent.com/systemd/systemd/v225/src/libsystemd/sd-bus/busctl.c) 中 `get_property()` 走 `sd_bus_call_method()`，没有使用 `arg_auto_start` 与 `arg_timeout`。`call()` 则设置消息标志并向 `sd_bus_call()` 传入超时。实际 ARM 二进制相符：

| 固定基线位置 | 核对结果 |
|---|---|
| `0xa724 → 0xbacc` | `call` 分支 |
| `0xbb70 → 0x1a320`，`0x1a348` | 禁用 auto-start 时设置 D-Bus `NO_AUTO_START` 位 |
| `0xbbb0` | 清除允许交互授权的标志 |
| `0xc4dc`、`0xc4e8 → 0x16208` | 从超时变量加载 64 位值并调用 `sd_bus_call` |
| `0xa73c → 0xbcb4`，`0xbd64 → 0x25f8c` | 已撤销的 `get-property` 使用另一调用形式 |

`--timeout=2s` 约束 D-Bus 方法调用，不能声称保证整个进程包含启动、总线握手在内均在两秒内退出。主机接收有独立时限，主机超时也不会取消机内已排队的工作。

## 原厂路径与副作用

固定消息链为 USB host `8` → FX3 控制端点 → SUC → iMX `5` → `msg2dbus` → `sutest-daemon`。三份消息表均确认 `testd_rx_event=10`、`testd_tx_event=9`，消息体为 256 字节。`msg2dbus` 在 `0x2219c` 接受目标 iMX 的消息 10，并在 `0x22550` 选择 `Bus::sutestService()`。

`sutest` 内层结构为 252 字节：命令号在 `+0`，操作字在 `+4`，原厂回传的关联字在 `+8`，32 位容器内 CRC16 在 `+12`，结果在 `+16`，文本从 `+20` 开始。原厂 CRC 覆盖 `+16` 起 236 字节。命令 52 的工厂项（初始化 `0x1bed0`、`0x1bee4`）指向 `0x3c10c`，再构造 `OsSystemCommand`（`0x4b428`）。它调用 `TerminalCmd`，由 `QProcess::start`（`0x59b34`）执行 `/bin/sh -c` 的单个固定字符串；其中 `exec` 将 shell 替换为 `busctl`，没有交互输入。

退出码为零时，`0x59090` 发出成功信号。`OsSystemCommand` 将 stdout 复制至已清零的返回缓冲，最多 232 字节；`SUTest::sendResult`（`0x24610`）回传前三个头字段、计算 CRC。`RawHandler` 在 `0x1d2b4` 生成 ID 9、源 5、目标 8，经既有 SUC 服务与 FX3 控制 IN 返回。只解析到整体偏移 257；忽略原厂消息末尾和 USB 槽中的未定义填充，不保存这些字节。

初始化与通信不是完全被动操作：

- 若 `sutest-daemon` 尚未运行，原厂 D-Bus 激活文件可以启动其 systemd 单元；该单元先执行 `/sbin/modprobe i2c-dev`。此副作用已在候选审阅时报告。
- 已核默认启动路径为 system bus、QObject/执行器初始化、服务和槽注册；没有发现自动选择 `TestMode`。只有收到命令后才构造对应测试对象。
- USB、UART、RTOS 队列、D-Bus 注册及原有日志可能发生。`busctl` 会成为临时系统总线客户端。
- 固定调用禁止启动目标 FARM 服务，不切换 RAM 模式、不清除错误，不调用 setter、拍摄、文件下载或恢复动作。

## 实际复用的仓库工具

按用户要求下载的完整仓库位于 [固定仓库目录](../references/hasselblad-x1d-reverse-engineering-87b39648a962)，revision 为 `87b39648a9625a0b74279b86a44f778e22e9c2c1`，来源为 [公开仓库](https://github.com/YuHaoyua/hasselblad-x1d-reverse-engineering/tree/87b39648a9625a0b74279b86a44f778e22e9c2c1)。原 LICENSE 随仓库保留。

本实现从固定文件中实际加载 `sutest_crc16`、`make_testd_frame`、`make_exec_request` 三个已读纯函数，逐文件验证 SHA-256，通过 AST 只加载函数定义。没有运行仓库的 USB 初始化、无上限 `drain`、任意命令 CLI 或 PullFile 入口。原工具以零初值对命令字段计算 CRC；本请求结果字为四个零，因此与原厂 236 字节覆盖计算一致。

主机传输层复用此前已核对并冻结哈希的 `NativeWinUsb`，使用当前驱动。固定 OUT `0x02`、IN `0x82`，只接受已审阅的 512 字节控制接口。没有更换 USB 配置、驱动、串口或自动重置端点。

## 离线验证与执行边界

- [静态核对](validation/sutest-ram-cache-static.json)：固定二进制哈希、35 个关键指令、三份消息大小表及工厂指针通过。
- [契约与故障模拟](../CodeTests/usb_diagnostic/test_sutest_ram_once.py)：12 项通过，涵盖独立 CRC 算法、长度、路由、关联字、错误结果、输出尾部、超时、短写、共享期限与资源关闭。
- [一次性读取入口](../tools/read_sutest_ram_once.py)：默认无设备访问；执行需显式标志与独占创建的结果文件。命令固定，没有任意参数输入。
- 最多提交一次请求，OUT 超时 2 秒。接收预算共 6 秒，最多两次 IN 调用；只允许先前唯一 FARM 查询的一个迟到回复，其余异常立即停止。不预先清空输入，不自动重试。

前两次历史请求保持原始证据：FX3 链路状态返回 `1`；FARM RAM 查询发送完成后接收超时。本次查询的独立实机证据见顶部，不能回改前两次记录。
