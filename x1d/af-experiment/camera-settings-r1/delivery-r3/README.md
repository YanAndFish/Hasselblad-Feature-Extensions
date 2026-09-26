# AF 独立交付 r3

本目录是 AF 模块的独立装载交付。设备操作由主任务独占执行；本任务完成了离线构建与模型验证，设备请求为 0。不要与正在运行的 UI、回放、组合包或旧 AF 安装叠装。

## 固定内容与前置条件

- Linux 包为此前主任务现场报告 UI、Qt 资源、AF bus-r2 和健康检查通过的同一份字节：`inputs/af-only.tar.gz`，SHA-256 `f325db70de366f52ae3b58b98f8e9fd3e496f353dbab64c6ca4712a49064cc6a`，78825 字节。包、6 份原验证资料及来源清单已复制到本目录；安装不调用 combined-runtime 的构建或会话入口。
- AF 机器码、机内 QML、bus-r2 和原厂逐字校验均保持原实现。基线来自本仓库 X1D 1.25.0 研究输入，FARM SHA-256 `317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca`；实际设备必须通过版本、原字、回调、heap 和空白区域预检，不能仅凭文档版本放行。
- 使用当前仓库根目录、Python、已有离线固件依赖和 Zig 工具链。AF 原始来源链仍由冻结验证器逐项检查；这些是显式仓库依赖，并非可脱离仓库运行的便携包。
- `stage` 需要原厂 Linux 服务 active，且 `/tmp/hbl-x1d-combined` 不存在。UI 阶段还检查原厂服务与 drop-in、无其他临时模块、健康状态和原厂可安装状态，然后建立本次健康窗口。
- 完整 FARM 预检仍为正常模型下 7905 次请求、31 次 hold 检查、0 次 RAM 写入。段预算 120 秒、hold 至少剩余 180 秒、逐字校验及最大请求数限制保持原样。

## 独立入口

在 `.` 运行。默认 `report` 完全离线：

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r3/main.py report
python -B x1d/af-experiment/camera-settings-r1/delivery-r3/main.py stage
python -B x1d/af-experiment/camera-settings-r1/delivery-r3/main.py install-staged --evidence <上一步输出的stage.json绝对路径>
```

后两条是明确的设备动作入口。安装顺序为 Linux preflight → UI/hold → bus-r2 → 完整 FARM 预检 → RAM 持久日志 → 缓存探针 → 原厂分配 → 在本目录重定位构建 → AF 安装 → 完整日志复核 → 释放 hold。日志和运行生成物只写本目录。没有继续失败会话或跳过地址的入口。

## r3 的传输改动

每次成功的 Linux hold 查询之后，仅首笔 FARM `read` 或 `version` 的一次回复等待预算改为最多 20 秒，并取当前段剩余预算的较小值。其余 FARM 请求仍为 2 秒。请求只发送一次；错误路由、短包、超时和写入歧义立即停止，不重发、不清管道、不重置 USB。

`af-trace.jsonl` 在预检前建立，与允许 RAM 写入的事务日志分开。每笔操作在调用传输前追加并落盘意图，之后追加结果，记录实际地址、阶段、主机单调时钟、请求预算、收发字节数、Win32 错误和句柄关闭状态。它不记录报文正文或设备标识。链尾意图或不完整行代表结果未知，不能被当作成功。

20 秒是主机请求预算，不是设备响应的实测上界，也不是已查明的故障修复。WinUSB 超时与主机排队计时有边界，主机取消也不能证明设备操作被取消。参见 [Microsoft 管道策略说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-functions-for-pipe-policy-modification) 和 [ReadPipe 返回错误说明](https://learn.microsoft.com/en-us/windows/win32/api/winusb/nf-winusb-winusb_readpipe)。

## 失败和恢复

首先运行离线检查，保留整个会话目录及对应 recovery 日志：

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r3/main.py inspect --evidence <本次installation.json绝对路径>
```

| 证据状态 | 可执行路径与限制 |
|---|---|
| FARM preflight 失败，完整 trace 确认 0 写、句柄已关闭、没有 RAM 日志 | `restore-preflight --evidence <installation.json>`；先检查同一包、目录所有权和远端 `ram.started` 不存在，再执行本包 Linux 恢复。 |
| AF RAM 已完整装好、释放 hold 之前发生问题 | `rollback-held --evidence <本目录recovery中的完整安装日志.json>`；先检查当前既有未释放健康窗口，再完整预检、缓存证明、AF 回滚及逐字复核，最后写恢复证明并恢复 Linux。 |
| 正常安装已释放 hold，或 hold 已过期 | 本入口不会重建或续期窗口；由主任务结合当前设备状态安排用户重启，清除临时 RAM 安装。不得直接套用 `rollback-held`。 |
| 任意未完成写入、缓存动作、分配、阶段结果未知或证据损坏 | 停止，保留全部记录，按实际阶段交给主任务审阅；不重试、不释放堆块、不直接恢复 Linux、不自动重启。 |

恢复只移除本包拥有的 drop-in 并恢复原厂服务；临时目录、证据及已保留堆块不会被自动清空。回滚失败也必须停止，不能用新会话重复同一步骤。Linux 阶段存在 `.sent` 而无 `.exit` 时，不重发该阶段；主任务先确认该进程结果与当前设备状态。

## 验证与未完成项

`validation.json` 绑定所有 r3 执行源、输入快照、测试输出和原 AF 验证入口；`CodeTests/validate.py` 可重新执行离线核验。15 项检查覆盖首笔延迟、普通超时、段预算、错误回复、hold 失败、trace 落盘失败/残尾、具体预检地址、完整 AF 安装/回滚、写入歧义、Linux 传输、阶段去重、预检恢复分流及不同现场包拒绝。ARM 原厂分配器实际在模拟器执行，USB、调度、缓存和时钟仍为替身。

r3 尚未实机重测。此前 bus/UI 的现场通过属于旧的同字节 Linux 包证据；不等于 r3 传输改动已通过实机验收。新预测动作和两个提前补偿仍未接通实际执行，不能标记完成。
