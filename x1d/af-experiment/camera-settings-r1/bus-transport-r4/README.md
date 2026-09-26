# AF 通信断点诊断 r4

现场 r5 已安装，但用户的 15 次配置读取全部超时。bus3 记录 15 次原厂 writer 入队接受、0 个通过其前置筛选的 784 回复。本版仅补足后续发送和回程计数，**尚未确定实机根因，也未证明查询或保存修复**。

固定来源为 X1D 1.25.0：`msg2dbus` SHA-256 `988bf67864d09e6183b86b65a2e0ad5b60b18df84c2a06076da96ebff84d6eb1`，`libAppsMessaging.so` SHA-256 `8a6a45428fcaa17e570e0aad217ee7220716501bcaf4cddef106af5137d6f7d1`。原厂 `SendMessage` 在 `0x1de1c` 调用 `0x1dd50` 入队；异步 writer 在 `0x1df84` 才调用 `MSGTRANP_send_prepacked`。后者 `0x4adf63e8` 另检查队列和链路状态，可返回 -1 或 -2；writer 在 `0x1e158` 检测错误。本版原参数调用该真实函数一次并保留返回值、errno，不增加重发。

原厂接收 callback `0x1c600 → 0x1c4f8 → 0x54f60` 发出 `ReceiveMessage`，使用本版已拦截的原 Qt activate 签名。本版把计数置于 ID/长度/owner 筛选前，原 Qt 分发继续执行一次。计数不记录报文内容、会话、配置、镜头或照片信息。普通链路活动计数不能当作某次私有请求已实际送达。

## 独立安装与恢复

用户已明确把本轮 AF 实机执行权交给本任务；主任务和回放任务停止访问设备。仍不自动发送 AF query/apply，不触发拍摄、对焦或闪光。

仅支持当前已装 `delivery-r5`，原 manifest SHA-256 必须为 `bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e`。完整校验原包、90 配置及 GUI owner；安装新增 `95-hbl-af-bus-r4.conf`，只切换 msg2dbus-farm。GUI PID 必须不变；AF RAM、GUI 库、RCC、搜索策略均无写入入口。原 r5、bus3 源码、包与验证报告保持冻结。

服务启动会重新打开原串口并初始化原厂传输链，存在短暂链路中断；没有重启 FARM 或相机的命令。脚本不写 AF RAM，不代表已经通过实机 AF 效果验收。

```powershell
python -B x1d/af-experiment/camera-settings-r1/bus-transport-r4/main.py report
python -B x1d/af-experiment/camera-settings-r1/bus-transport-r4/main.py stage
python -B x1d/af-experiment/camera-settings-r1/bus-transport-r4/main.py apply --evidence <本版实际 stage.json 的绝对路径>
python -B x1d/af-experiment/camera-settings-r1/bus-transport-r4/observe.py
python -B x1d/af-experiment/camera-settings-r1/bus-transport-r4/main.py restore --evidence <同一 stage.json 的绝对路径>
```

首次安装先执行私有目录中的本地 socket 自检，失败不切服务。修改服务后发生确定失败，脚本尝试撤销自己的 95 配置并恢复原 bus3，结果留在 `failure-restore.log` 与结果标记中。结果未知、存在外来配置或 GUI owner 变化时停止，不重发安装。已自动恢复不再重复恢复。该入口只恢复 bus；正常卸载应先完成本版恢复，不能直接套用旧组合栈的恢复脚本。

## 匿名计数

`backend-r4-flow.status` 保留 bus3 的收发校验计数。新增 `backend-r4-transport.status` 由 owner 线程至多每 250 ms 更新，回调只更新 ARM32 原子计数。

| 字段 | 边界 |
| --- | --- |
| calls | 所有实际进入原厂 prepacked 包装函数的调用 |
| private / returned | 私有请求进入 / 真实函数返回；有差值可能仍在调用中 |
| ok / notready / invalid / other | 私有请求返回 0 / -1 / -2 / 其他；0 仅表示内部提交 |
| queue | 原厂 writer queueData 信号；包括普通流量 |
| serialtx / serialrx | 原厂 SerialPortWorker writeData / dataAvailable 信号；仅链路活动 |
| receive / rxowner | 筛选前 ReceiveMessage / 匹配当前 owner |
| rx784 / rx784size / rx784owner | ID 784 / 其中长度 259 / 其中当前 owner |
| rx784queued | 通过既有前置筛选并安排交给 Bus.reply |
| rxargument / rxwide / uartparse | 接收参数缺失 / 长度超界 / 原厂 parseError 信号 |

装载后先取零查询基线，再请用户仅手动读取一次，比较新增计数。若 `private` 未增加，断在 writer 调度至 transport 入口；若 notready/invalid 增加，断在原厂 transport 独立检查；若返回 0 且没有 784，继续定位链路与 FARM；若 784 已出现，则由长度、owner、queued 与 flow 定位回程筛选。不得把其中任一中间阶段标记为真实 query/save 成功。

## 离线验证范围

真实 Bus 与计数方法共 9 组场景；实际 ARM 库及固定原厂 transport 共 11 项 ABI/返回分支测试；6 项安装/恢复场景、6 项实际 common.sh 就绪谓词场景、6 项归档/主机入口场景。Qt、文件系统、服务、USB 和 RTOS 外部边界使用替身。实际设备装载和往返结果另行记录，不改写冻结验证报告。
