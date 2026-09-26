# AF 配置通信修订 r3

本包修复原桥接忽略 `SendMessage` 实际 bool 返回的问题，并补齐分段匿名计数、目标机本地 socket 检查及受控安装/恢复入口。离线验证通过，**读取超时的实机根因尚未唯一确定，真实配置读取/保存尚未验收**；不能把本包称为已完成 AF 往返修复。

按主任务最新安排，现场优先测试回放，可能先正常重启。本任务 0 设备请求，没有装载本包。它是要求既有 AF r3 + GUI r4 的条件式增量，不是重启后干净机身的完整 AF 安装包。镜头规格分类/适配委托已撤回，本版没有相关改动。

## 已验证与未验证

已知现场证据由主任务提供：r4 页面 5 次查询、86 次本地编辑，0 回复、0 socket/envelope 拒绝、0 本地发送错误；仅凭这些信息不能区分 bridge、UART 或 FARM 回程。读取 FARM dispatcher 的最后消息缓存会受到诊断读取本身影响，已取消该观察方案，没有新增该 RAM 白名单。

固定 X1D 1.25.0 `msg2dbus` SHA-256 为 `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1`。原厂 `SendMessage` 在 `0x1de1c` 检查 owner 状态；未就绪返回 false。Qt `invokeMethod` 的返回只表示调用能否完成，不能代替 slot 返回。新版使用 `Q_RETURN_ARG(bool,accepted)`，将调用失败、UART 拒绝和入队接受分开记录；入队接受仍不等于已到达 FARM。

`../query-diagnostics-r1/original-chain-tests.json` 的 3 项原厂 ARM 检查已通过，覆盖实际已安装 payload、原厂 dispatcher、封包、发送至 RTOS 队列边界、UART bool 与消息长度。它不覆盖实机 UART。FARM 固定 SHA-256 为 `317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca`。

本版另有：

- 真实 Bus 源码方法的 7 组收发场景：准确封包、单个在途请求、UART/调用拒绝、非法输入拒绝、回复身份/校验和匹配、超时和 UI 发送失败；Qt/socket/文件系统使用替身。
- 实际新 ARM 库的 6 项发现与转发 ABI 回归，覆盖无信号启动、参数/errno、失败、销毁和重复连接。
- 6 个隔离安装场景，覆盖正常安装/恢复、前置失败不切服务、新服务失败恢复、外来 drop-in 和 GUI PID 变化时拒绝恢复。
- 6 项主机入口检查，覆盖归档、可执行权限、传包逐字节一致、命令 231 字节上限、一次发送、失败/未知不重发、未关闭阶段拒绝。

`bus-local-check` 在机内独立 `/tmp/hbl-af-bus-r3/local-check` 目录建立两个本地 socket，双向比较 255 字节测试数据，然后关闭并清理自己的目录。它使用实际目标 ARM/glibc 接口，不创建 MessageIO、不打开 UART、不访问 AF 端点。尚未在目标机执行；`apply` 会先执行此检查，失败时不停止通信服务。

## 安装与恢复边界

入口默认 `report` 为离线。后续 `stage`、`apply`、`restore` 仅由主任务独占执行，且服从当时现场顺序。本任务没有替主任务执行这些动作。

```powershell
python -B x1d/af-experiment/camera-settings-r1/bus-roundtrip-r3/main.py report
python -B x1d/af-experiment/camera-settings-r1/bus-roundtrip-r3/main.py stage
python -B x1d/af-experiment/camera-settings-r1/bus-roundtrip-r3/main.py apply --evidence <本包实际 stage.json 的绝对路径>
python -B x1d/af-experiment/camera-settings-r1/bus-roundtrip-r3/main.py restore --evidence <同一 stage.json 的绝对路径>
```

前置检查绑定旧 AF-only 包 manifest SHA `79da1a75552717936fbad737d8d4532c489907a7e02197e4acd0605f43c63b05`、r4 GUI manifest SHA `67da9db221c3e47598c204393d9d0a628d427d497da7763d618a5f724c75f9ca`、原 drop-in、运行库、socket 和 GUI 健康状态。GUI gate 沿用已审查 `--require-ui-stage`，接受合格 Active 或 Standby；不因此放宽 FARM 写入条件。

只新增 `msg2dbus-farm.service.d/95-hbl-af-bus-r3.conf`，覆盖该服务的 `LD_PRELOAD`。先停止 bus、确认原 PID 已退出，才删除经权限/类型校验的旧 backend socket/状态文件；随后启动新 bus 并核对 GUI PID 不变。原 AF RAM、r4 UI 库、RCC、GUI 服务及旧 90 配置均不由本包修改。没有 AF 查询/保存命令、AF 清 RAM、系统 hold 或相机重启命令。

原厂服务重新启动会打开 `/dev/ttymxc2`，原 `SerialPortWorker::openPort` 会清理串口缓冲，`initializeMsgtranspStack` 会重建正常传输链；因此这是有短暂链路中断的服务切换。脚本没有重启 FARM 的命令，但 **AF RAM 保持情况仍应由主任务用既有已审查白名单做切换前后只读核对**，不能以脚本未写 RAM 替代现场证据。

失败恢复只撤销本新增 95 配置并启动原固定 bus 库，保留原 90 配置。若遇外来配置、GUI owner 变化或不确定阶段，则停止并记录；不重发安装。已自动恢复后也不重复恢复。

**恢复责任限制：** 这是 bus-only 恢复，不是整个 AF 组合栈的回滚。旧 r4 GUI 恢复脚本固定了当时 bus PID；正常 bus 切换/恢复后的 PID 变化会使其拒绝执行。不要改写旧 `bus.pid` 证据来绕过检查，也不要直接套用旧 r4 恢复入口。完整组合栈恢复由主任务按当时现场另外审查；用户正常重启会清掉本次临时组件。现场已转向回放测试时，本包保持离线交付。

## 匿名计数解释

`/tmp/hbl-af-settings/backend-r3.status` 记录绑定阶段；`backend-r3-flow.status` 记录计数，不含会话、sequence、原始报文、配置、镜头信息或设备标识。

| 字段 | 含义 |
|---|---|
| `events / datagrams` | notifier 回调 / 本地接收的 datagram |
| `socket / socketreason` | 本地端点校验拒绝 / 最近一次拒绝类别 |
| `owner / envelope / config / busy` | 线程/对象、消息信封、内容或在途占用拒绝 |
| `queries / applies` | 通过校验、尝试交给原厂的两类请求 |
| `invoke / uartreject / uartaccept` | 调用失败 / 原厂返回 false / 原厂入队接受 |
| `farm` | 从原厂 ReceiveMessage 信号观察到 ID 784、长度 2–320 的候选回复；不是所有 FARM 流量 |
| `replyreject / unsolicited / matched` | 回复拒绝 / 无在途请求 / 完整匹配 |
| `delivered / uifail / expired` | 发给 UI 的本地发送成功 / 发送失败 / 在途超时 |

`socketreason`：1 长度，2 截断，3 地址族，4 对端地址长度，5 对端路径，6 缺少合法 credentials，7 UID。只保留类别，不输出实际 UID 或路径。两秒等待上限保持原值；无自动重发或自动配置请求。真实读取/保存应在主任务安排的后续现场往返中验收，单独 `ready` 不够。

## 固定产物

- `linux-build/libhbl-af-bus.so`：22756 字节，SHA-256 `3edbc26070feaec2a2d8971d6ab4b5c47493cb778b4b17e65daeb325151ce81b`。
- `linux-build/bus-local-check`：6380 字节，SHA-256 `7c810cf7529b9a846f26c4843a9941b607dc1c188748142fc4e09d1aebfc6daa`。
- `build/package/af-bus-r3.tar.gz`：16621 字节，SHA-256 `0517cd00643d80163d97fa27d55228c9b5b516f4613e89ba43e5472e6676d358`。
- 归档 manifest SHA-256：`325cb19c634385443e6825d590f90173bb5959345355ce740d0d0c8b76edbdc7`。

AF 算法、当前认可的默认策略、提前量默认值与 ±1 ms 交互均不在本修订里改变或补齐；没有伪造原厂毫秒值，也没有把保存按钮绕过真实读回校验强行启用。
