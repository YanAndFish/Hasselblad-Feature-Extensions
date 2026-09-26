# AF 干净基线完整交付 r5

这是供正常重启后的原厂基线使用的完整 AF 临时安装流程。它组合冻结的 delivery-r3 AF 机器码/合同、ui-interaction-r4 界面和 bus-roundtrip-r3 通信修订，首次服务启动即加载最终组合，不先装旧 bus，也不使用两份 95 增量配置。所有旧冻结交付保持原样。

本任务仅离线构建与验证，0 设备请求。主任务独占实机装载，须先收到用户当前这次重启完成的确认并核对原厂基线。**完整可装流程不等于真实读取/保存已经修好**：r3 bridge 的实际 bool 返回修正已验证，但之前超时的实机断点仍需新匿名计数及真实往返确认。

## 内容与依赖

| 内容 | 本包位置 | 固定来源 |
|---|---|---|
| AF 算法、默认行为、逐字检查、预检/安装/回滚合同 | 本目录主机代码与运行时重定位输出 | delivery-r3，机器码不变 |
| 安装 hold 与资源宿主 | `inputs/libhbl-af-only.so` | 原 AF-only，SHA `99a73073…` |
| 界面 | `inputs/af/libhbl-af-ui.so` | r4，SHA `2ded6099…` |
| 组合 RCC | `inputs/af-only-ui.rcc` | r4，SHA `d9807bfa…` |
| 通信 bridge | `inputs/af/libhbl-af-bus.so` | bus-r3，SHA `3edbc260…` |
| 健康检查器与原厂 Linux 文件校验表 | `inputs/system-check` 等 | 与 delivery-r3 逐字相同 |
| 仅本地 socket 检查 | `inputs/bus-local-check` | bus-r3 同源码，仅临时目录改为本完整包内 |

仍依赖当前 Hasselblad 仓库、已有 Python、Zig、固定 X1D 1.25.0 离线输入及原冻结 AF 验证链，不是脱离仓库的便携安装器。实际 FARM 仍必须通过版本和原字检查；静态基线版本不能代替实机验证。

没有镜头规格分类/适配，没有改变用户认可的 AF 策略或默认值，没有另发配置 apply、参数写入、对焦、拍摄或闪光指令，也不安装回放组件。安装器不会自动打开 AF 页面或发配置 query；装好后用户打开页面所触发的读取仍沿用 r4 行为。两个提前量及默认毫秒/±1 ms 待办没有在本包中补齐或伪造。

## 主任务执行入口

从 `.` 运行。第一条纯离线；后两条由主任务在当时授权和独占现场下执行：

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py report
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py stage
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py install-staged --evidence <上一步实际 stage.json 的绝对路径>
```

`stage` 要求原厂 Linux 服务 active 且 `/tmp/hbl-x1d-combined` 不存在；一次传输、一次解包，逐字节核对本次包。它只传到临时目录，不启动 AF 或更改服务。失败不续传、不重发。

`install-staged` 再核对现场 manifest 与同一 stage 证据，顺序固定：

1. Linux preflight：原厂服务、drop-in、临时目录、文件/健康检查；`bus-local-check` 在包内两个本地 socket 之间验证目标 stat/credentials/收发 ABI，不连 UART/FARM。失败不切服务。
2. UI/hold：建立一次固定健康窗口，只有 `90-hbl-af-only.conf`，首次 GUI 启动即加载 r4 UI 库及 r4 RCC。显式设置 `HBL_AF_UI_R4_ENABLE=0`，让原宿主直接注册原路径下的新 RCC，不访问 r4 增量目录。
3. bus：只有原事务拥有的 90 配置，首次 bus 启动即为新 bus-r3，检查 `backend-r3.status`、flow 文件和 socket。没有第二次 bus 增量重启或旧 r4 `bus.pid` 恢复依赖。
4. 完整 FARM 预检 → 追加式持久日志 → 缓存探针 → 原厂分配 → 本目录重定位构建 → 原 AF 安装 → 完整日志复核 → AF 完成证明 → 释放 hold。

FARM 预检模型保持 7905 请求、31 次 hold 检查、0 写入；段预算 120 秒、hold 至少剩余 180 秒、白名单、逐字检查和请求上限不变。成功 hold 后第一笔 FARM read/version 仍只发送一次、最多等待 20 秒；其他 FARM 请求 2 秒。20 秒是主机预算，不是物理性能或根因结论。

本包对 GUI 和 bus 各执行一次初始 `systemctl restart`，不重启 FARM/相机。串口会按原厂服务启动流程重新打开和建立正常传输链；不声称该过程没有链路副作用。

## 失败分流与恢复

```powershell
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py inspect --evidence <本次 installation.json 的绝对路径>
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py restore-preflight --evidence <同一 installation.json>
python -B x1d/af-experiment/camera-settings-r1/delivery-r5/main.py rollback-held --evidence <本目录 recovery 中完整安装日志的绝对路径>
```

| 离线 inspect 结果/现场阶段 | 处理 |
|---|---|
| `no-linux-service-changes` | preflight 已明确结束，尚未启动 UI/bus；无需恢复服务。保留证据，解决原因后另由主任务安排。 |
| `restore-preflight-linux`，尚未开始 FARM 预检 | UI/bus 阶段结果明确、0 FARM 请求/写入、句柄关闭；`restore-preflight` 先复核同包、阶段与远端无 `ram.started`，只恢复本包服务。服务已是原厂时仅确认基线。 |
| `restore-preflight-linux`，FARM 预检已失败 | 完整 trace 证明 0 写入、句柄关闭、无 RAM 日志，且远端无 RAM 意图标记；同上恢复 Linux。 |
| AF RAM 已完整安装、尚未释放 hold | 仅 `rollback-held`：同一完整日志、现有未释放且未过期健康窗口、完整预检/缓存证明/逐字回滚，再写恢复证明并恢复 Linux。 |
| 已释放 hold 或已过期 | 不重建/续期窗口；主任务结合现场安排用户正常重启清除临时 RAM。 |
| USB/阶段/写入/分配结果未知、日志残尾、外来配置 | 停止保留证据，不重发、不重复缓存动作、不直接移除依赖组件、不自动重启。 |

恢复只处理本完整包的两个 90 配置，先恢复 bus，再恢复 GUI；没有 r4 增量 PID 锁冲突。RAM 一旦出现意图标记，只有完成对应日志逐字回滚的证明才能移除 Linux 消费者。临时目录和证据不自动清空，因此不能在同一残留目录上直接重新 stage。

每个 Linux 阶段有 `.sent/.exit/.log`，主机 `installation.json` 另外记录明确/未知的 `linuxPhases`；FARM 每笔意图和结果落入 `af-trace.jsonl`，RAM 写入另用恢复日志。所有新日志、构建和模型输出位于本目录。设备标识、照片信息及报文正文不记入这些记录。

## 离线检查与后续验收

组合验证检查所有原组件字节、唯一替换集、资源路径/开关、单次服务启动和完整回滚合同。AF 在样本重定位地址 `0x2bacc0` 的候选与旧冻结候选逐字相同，SHA `c2ab77ccfc176cd6cfb5f302d3884f88c90cafd5ca79813dccda7215d2d91224`。真实分配后的地址仍按原验证构建流程绑定。

`CodeTests/validate.py` 覆盖原厂 ARM 分配器模型、完整 AF 安装/回滚、首笔超时/段预算、错误回复、写入歧义、日志残尾、主机阶段唯一发送、包身份及零 FARM 写恢复分流。`CodeTests/test_linux.py` 对实际 shell 运行隔离服务/健康替身，验证 10 个安装/恢复检查。模型不等于真实 USB/Qt/UART 验收。

成功装载后主任务可按新的 `backend-r3-flow.status` 和 r4 `ui-r4.status` 区分 datagram、校验、UART bool、候选 784 回复、UI 投递等层次。计数详细定义沿用 `../bus-roundtrip-r3/README.md`；新完整包不要求先安装该增量包。单独 `ready` 或服务 active 仍不能证明 query/save 成功。

完整 Linux 归档 `inputs/af-only.tar.gz`：87392 字节，SHA-256 `6bbd107079f76619c959574527f692a398732a4fce6f44850a14deff10b739c1`。归档 manifest SHA-256：`bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e`。最终冻结结果以本目录 `validation.json` 和默认离线 `report` 为准。
