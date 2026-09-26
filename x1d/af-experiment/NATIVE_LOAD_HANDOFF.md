# AF 与引闪联合装载：交给主任务的执行说明

2026-09-12。本轮用户已授权把 AF 和引闪一起装载，并明确：AF 源码修改由“研究哈苏 X1D”负责，主任务 root 复核并亲自串行操作相机。**本 AF 任务不接收 USB、不连接设备。** 不重复询问安装授权；自动对焦、拍摄、试闪仍未授权。

## 当前候选与设备状态

AF 候选、119 项检查及相关源码须以 [汇总](build/native-capture-r1/loader-validation.json) 当前哈希为准。候选主体 14944 字节，申请 16 KiB，有效余量 1440 字节。保留原厂精扫、全部判向/预判代码；首次仅观察原厂标量，new-direction、speed override 和 prediction actuation 均关闭。真实帧关联、采样提供器、时间/制动标定及算法元数据并发发布仍未完成，不能宣称增强 AF 已生效。

本启动引闪已由主任务实际安装成功，AF 已核对固定记录与完整不可变快照，并更新来源合同。当前合同 `aab59f89f16d2d3f8f972be640f72934e69fc020e45497d5077d2fb55d3faeb4`，只更新五个来源字段，HFS1 布局、代码、8 处入口及 AF 写入范围不变。旧启动记录保留为历史，不再是当前合同来源。

## 本启动的固定成功证据

成功记录为 `../wireless-flash/build/formal-flash-package/installation-20260912T125921Z.json`，恢复记录为 `../wireless-flash/build/formal-capture-recovery-20260912T125921Z.json`，会话为同一 package 目录的 `session-20260912T125921Z.json`。不可变快照 `../wireless-flash/build/formal-flash-package/stable-success-20260912T125921Z/` 的 7 项 SHA-256 全部通过，完整包 148364 字节、SHA-256 `d7e06ad983915f77c1ffe87893457703f5b8ec6d6e706ff028590536f71feef9`，包内 15 项逐一核对。

成功阶段 `installed-default-off-locked-for-joint-af`，`installed/linuxInstalled/farmArmed=true`。`installationGateReleased=false`、`installationHoldRetained=true` 是联合 AF 安装期间刻意保留的协调状态。会话全部回复匹配、句柄关闭，无拍摄/试闪；最后实测健康 `system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1`。本任务读取证据，没有自行访问设备。

主任务通报本轮未重启，末次 `verify(1)` 已读回 HFS1 代码、8 处入口及 idle 记录、原厂 CB/ARG 与 64 字节零 scratch，缓存临界段结束、SGI 无在途，所有设备客户端退出。该通报和固定文件不能替代安装入口稍后的实时状态检查。

hold 约北京时间 20:59 建立，最多 20 分钟不可延长；时间流逝不会自动授权新窗口。AF 首次及各安全边界仍要求 `--require-held-min-ms 180000` 通过，逾期或健康不合格即停，不自动续期。主任务保持本批次不对焦、不拍摄、不试闪，亲自执行下述入口。

## 执行入口与参数

全部命令从 `.` 执行。默认 `report` 完全离线；不要把 `install` 或 `detach` 当成只读查询。

```powershell
# 离线来源和准备状态；没有 USB
python -X utf8 -B .\x1d\af-experiment\CodeTests\validate_native_install.py
python -X utf8 -B .\x1d\af-experiment\native_loader.py report
python -X utf8 -B .\x1d\af-experiment\native_detach.py report

# 仅由主任务在上述已对齐证据及当前串行窗口成立后执行一次
python -X utf8 -B .\x1d\af-experiment\native_loader.py install
```

安装不接受手填堆地址或预测启用参数。程序生成非零代次，固定只读预检通过后在 AF `recovery/` 创建 `native-observe-<本机时间>.json`、对应事件链和锁文件；输出 `prepared` 时给出此次记录文件名。原厂空闲任务申请独立堆块并返回地址，程序核对块头后在该地址重定位、构建、写入和回读；不得把离线 `0x800000` 或 `0x2bacc0` 手填为实机地址。

离线主体 SHA-256 `57c15f40e3d38ae14a6e898b04198fbc1fc7df64791edaf7451ba71ce5a069d4`；`0x2bacc0` 重定位样本 SHA-256 `489e282bd7b64851d769a5182c45e5e5f4d155f87fa77ed2dfe9f8cb2269cb38`。真实返回地址不同可导致不同主体哈希；必须绑定本轮完整 manifest 和相同源码来源，不用离线样本哈希强行代替。

## 共享资源的串行条件

AF 与引闪共同使用 `[0x2b2800,0x2b2840)` scratch、回调/参数 `0x2a5074/0x2a5078`，以及 SGI15。AF 临时入口是 `0x19b960`（AF idle gate）和 `0x1e2224`（限定 F4 ACK 通知）。主体独立申请，不覆盖引闪；960 字节引导位于 `[0x2b3400,0x2b37c0)`，与当前历史 HFS1 段间隔 228 字节。

整个安装/撤销事务只运行一个设备客户端。不得并行运行另一装载器、缓存探针、FARM 诊断、AF 记录读取或 keepalive 进程。主任务统一控制电源协调生命周期；中途不切换待机、不重启服务/相机、不重新启动引闪进程。释放窗口前检查 AF 进程退出、全部句柄关闭、持久事件链完整，`inFlight` 和 `cacheInFlight` 均为空，以及原厂回调和临时入口恢复。

AF 内部在每次改回调前后、触发 SGI 后反复检查 pending/active 与对应 ACK；限定循环最多 64 次，无自动重试。HFS1 代码、入口、magic/enabled/idle 及曝光代次变化导致停止。安装成功保留本次 scratch 缓存辅助内容，但原厂回调恢复；下一客户端应使用当前快照，不假定 scratch 必为零。

[批次准备证据](build/native-capture-r1/joint-install-preparation.json) 中完整模型安装为 20619 次总请求（其中 hold 60 次）/4429 次 FARM 写请求，撤销为 12391 次总请求（其中 hold 50 次）/425 次 FARM 写请求；请求上限均为 24000。这是固定 CPU/报文/缓存模型计数，不是实机耗时承诺。运行时编译工具及本轮日志目录须可用，不应在程序还保持 gate 时终止构建或开始另一事务。

## 固定 hold 查询与分段边界

当前固定命令是 `/tmp/hbl-wireless-flash/formal-system-check --require-held-min-ms 180000`。成功回复仅接受退出码 0 和精确 `system=2 suc=0 farm=0 pwr=0 ui-power=0 hold=1\n`，同时核对报文类型、随机 token、CRC 及正文零填充；只发一次、只读一次，不丢弃旧回复后重试。checker ELF SHA-256 为 `8a0225ea00b74c549575f8d7599ecf106135bacf081bad230fa00fc9b16ce6dc`；源码和本地构建绑定见 [NativeHold.json](CodeTests/Fixtures/NativeHold.json)。这不是目标机文件身份或本启动安装成功的替代证据。

第一次检查在任何 FARM 请求之前，因此主任务须先交出已经恢复原厂 CB/ARG、无在途请求的独占接口。后续检查前，AF 完成缓存 ACK，确认 SGI15 pending/active 为零，恢复原厂 CB/ARG，再关闭 FARM 句柄后单独运行 Linux 查询。保持 gate 本身可以跨检查边界；尚在等待临时任务唤醒、缓存请求未完成或原厂回调未恢复时禁止查询。

原厂 6834 个字每 256 字一块；主体每 1024 字节一块。另在缓存探针之前、引导/分配阶段之前、分配完成后、主体取指探针完成后、每处原厂入口写入并同步缓存后及释放 gate 前检查。撤销使用同样的首检、只读分块、取得 gate 和逐入口恢复边界。完整主体缓存同步和 Thumb 取指回执属于一个不可插入 Linux 查询的临界段。

每次 checker 的三个快照均要求设备 hold 至少剩余 180000 ms。主机从本次检查开始计 120000 ms 段预算，包含 Linux 查询耗时；查询最多等待 20000 ms。每次 FARM 派发前，包括打开并准备接口后，重新检查段预算。已到期禁止再次查询来续接，需停止并审查。单事务最多 96 次 hold 查询，计入 24000 次总请求预算；设备原有 1200000 ms 截止时间不变。

这些限制提供名义时间余量，不能证明任意操作系统调度、句柄开关或日志持久化阻塞都有硬上界，也不能保证一个阶段必定完成。检查失败、关闭失败、回复不明或段超时后不再发后续 FARM 请求，不自动释放 gate、清理、重试或延长 hold。若已分配、上传部分主体或只改部分入口，保留阶段和事件链交由主任务协调离线分析。正常退出后仍由主任务确认共享资源/句柄/日志状态，再结束 hold。

## 成功判定与撤销入口

成功安装终态为 `installed_observation_until_restart`，持久记录应包含 `installed:true`、`ownedCodeExecuted:true`、`predictionActuation:false`、`speedOverrides:false`、`nativeFinePreserved:true`、`flashCodePreserved:true`、`allHandlesClosed:true`，事件链完整且没有在途操作。核对本轮真实分配响应、主体 manifest、12 处入口、引闪代码和原厂回调。代码/缓存读回与取指回执不代表实际合焦或预判效果。

完整成功安装且仍为初始观察模式时，可以使用以下入口恢复原厂 AF 调用点；其中记录路径必须替换为**本轮程序实际输出**，不是预先生成的文件名：

```powershell
python -X utf8 -B .\x1d\af-experiment\native_detach.py report --journal <本轮完整成功观察安装记录绝对路径>
# 仅主任务在审查本轮记录和重新取得串行空闲窗口后执行
python -X utf8 -B .\x1d\af-experiment\native_detach.py detach --journal <同一本轮记录绝对路径>
```

撤销终态 `original_af_restored_memory_retained`、`removed:true`、`heapFreed:false`：恢复 12 处原厂 AF 入口、两个临时入口、原厂回调及撤销前 scratch；驻留代码和堆块保留，不重启、不 free、不重复分配。只支持完整成功且未改配置的观察安装；不支持同轮重新安装。

若安装在中途失败、未知写入结果、回执缺失或日志损坏，**没有通用自动回退或继续安装入口**。保留日志、代码和堆块，停止后续设备请求，由主任务把失败阶段与事件链交回 AF 任务做离线核对，再形成特定恢复方案。不得拿 `native_detach.py` 处理不完整安装，不通过自动重启清掉引闪，也不要直接重跑 `install`。此次已修正装载日志里过时的“按需手动重启”提示，使其与当前回退边界一致。
