# X1D replay-next 会话装载交接

2026-09-12。用户要求“做到能直接装载的程度，装载由其他会话执行”。本目录已提供可执行的临时会话包；本任务没有连接相机或执行装载。对象仅为第一代 **X1D-50c / 官方 1.25.0**。

## 接收文件

- [session.tar.gz](artifacts/session-package/session.tar.gz)：663,204 字节，SHA-256 `4ff2a1981ecf52546b0f743ea6eb6622a8aceac8db968c03262496a44c439a78`。
- [package.json](artifacts/session-package/package.json)：各文件摘要、来源报告绑定及未完成的实机验证。
- [transfer_session.py](tools/transfer_session.py)：供执行会话注入已有授权 `Session` 的传输接口；没有设备发现、USB 打开或连接代码。
- [完整包验证](artifacts/package-tests/validation.json)：实际生成的 5,030 条上传命令在宿主工作副本完成解码、解包及 14 个成员校验；没有运行 ARM 程序。

`packageReadyForDelegatedLoad=true` 表示交接文件和执行流程已具备；`targetValidated=false` 表示相机上的装载、功能、性能与恢复尚未验证。早期 [装载前准备](LOAD_PREPARATION.md)中的 `loadReady=false` 属于该阶段离线审计，不能当作本包缺少安装实现，也不能被本包状态改写成实机通过。

包内为 5 份 shell 脚本、`replay-check`、`replay-ui.rcc`、3 份 `.so`、`payload/configstore`、`payload/jpeg-daemon`、原厂 `baseline.sha256` 及本包 `manifest.sha256`。不携带整包固件、解包密钥或照片。库和程序必须整套使用；两个程序保留实际进程所需的 basename。

## 执行边界与前置条件

由持有设备窗口的会话确认当次装载授权，并独占正常传输入口。本说明不发起装载、不建立第二个连接，也不要求启动引闪模块。`research/mechanical_sync_session.py` 中已有的 `Session.command` 接口可作为传输来源，但该文件由主任务维护；执行者先核实当前实现与授权，不能直接运行其测试或使用旧 `formal_transfer.py` 报告代替本包校验。

执行者须确认设备当前正常清醒、无人操作、没有拍摄/编码/写卡/删除/格式化/更新及待机切换；整个装载期间维持独占。自动检查包括系统 Active、SUC/FARM/PWR 链路、UI 电源状态和 DBus owner，但这些不能独立证明存储队列已经空闲。曾报告的 1000 故障和后来正常重启均为历史观察，不能用于判断当前状态。

脚本要求 root、BusyBox 兼容 shell 工具与 systemd，固定工作目录 `/tmp/hbl-x1d-rp` 必须不存在。上传与校验在 GUI 仍运行时完成。原厂基线包括 40 个 ELF、30 个库/解释器别名和 4 份服务配置；已有 drop-in、外来 `LD_PRELOAD`/`LD_LIBRARY_PATH`、非原厂 service fragment 或摘要不一致均拒绝推进。包不是叠加在现有引闪会话上的联合安装器；执行会话自行协调已有组件的生命周期。

## 分阶段执行

先在电脑验证，命令只读本地包：

```powershell
python -B x1d/candidates/replay-next/tools/transfer_session.py
```

以下 Python 在拥有设备授权的其他会话中使用。`session` 必须是该会话已经建立且核实的传输对象；每次 `command(label, ascii_command)` 返回 `{'exit_code': 0, 'output': str, 'closed': True}`，表示本次设备句柄已经关闭。任何异常或未知响应会锁住 `Transfer`，不能重发。

```python
import sys
from pathlib import Path

repo = Path(r".")
sys.path.insert(0, str(repo / "x1d/candidates/replay-next/tools"))
from transfer_session import Transfer

# session 由本执行会话提供；这里不构造或发现相机。
transfer = Transfer(session)
transfer.upload(progress=lambda done, total: print(f"{done}/{total}"))
```

上传共 5,025 个 176 字符 base64 块，每条命令不超过 231 字节。此入口逐条关闭设备句柄，传输总时间取决于实际连接耗时；不能把宿主验证时间当作设备上传时间。解码在后台进行，结果通过临时文件原子发布。上传阶段尚未创建活动保持期限，不要提前停止 GUI。

之后每隔约 5 秒调用一次 `transfer.finish_upload()`。`False` 只表示解码尚未结束；`True` 表示远端归档 SHA-256 和解包成员摘要通过。等候应由执行会话有界管理：两分钟仍无结果则停止推进并检查现场，不重复上传或启动解码。出现异常也停止。

确认 `True` 后，仅派发一次 UI 阶段：

```python
transfer.dispatch("ui")
# 每隔约 5 秒单独观察；pending=True 时不要再次 dispatch。
result = transfer.result("ui")
```

UI 阶段创建不可续期的 20 分钟活动保持期限，只通过私有 `/run/systemd/system/victory-gui.service.d/90-x1d-replay.conf` 加载会话守护库并重启 GUI。QML 仅在健康且已醒时每 500 ms 调用原厂活动通知；不修改待机设置。检查器要求同一 UI PID 的 2 秒内新鲜脉冲，实际 GUI 渲染上下文还必须报告 `GL_MAX_TEXTURE_SIZE >= 8176`、Qt 使用的 BGRA 扩展及 NPOT 支持。任何条件不符自动尝试恢复原 GUI。

只有 UI 阶段明确返回 `pending=False, exit_code=0` 后才能派发下一阶段：

```python
transfer.dispatch("enable")
result = transfer.result("enable")  # 仍按上述方式单独轮询
```

启用顺序为 `configstore → jpeg-daemon → victory-gui`，每步检查进程可执行文件摘要、健康状态与 DBus owner；最后检查候选库确实出现在对应进程 maps。临时 drop-in 设置 `Restart=no`，避免候选故障造成自动重启循环。成功后自动释放活动保持，记录 `replay-session-loaded-awaiting-functional-validation`。这表示安装脚本完成，不表示 JPEG、预览或 Full 已实机验收。

每个阶段超过两分钟没有结束信息都停止推进，保留原 `Transfer` 和现场；时间经过不构成操作失败已结束的证据。不可同时执行 UI、enable、restore，也不可因为没有返回就重复发送启动指令。自动恢复可能仍在进行。

## 状态观察与撤销

已确认没有阶段在执行时，可用已有授权传输发送以下短命令只读观察：

```sh
sh /tmp/hbl-x1d-rp/status.sh
```

输出区分 `recorded=staged/enabled/restored` 与 `live-health`、`live-services`。后者核对当下健康/owner及可执行文件摘要；它不验证 GPU 上传，也不把旧 `enabled` 文件当作当前功能正常的证据。待机时健康不可用需要执行会话结合当前现场判断，不能据此触发唤醒、重装或重启。

成功装载且当前仍具备静止窗口时，通过同一 `Transfer` 撤销：

```python
transfer.dispatch("restore")
result = transfer.result("restore")  # 只观察，直至明确结束
```

安装失败时脚本已经自动尝试恢复；先读取该阶段退出码和日志尾部。`replay-rollback-complete` 代表恢复脚本确认原服务和 owner；`replay-rollback-incomplete` 必须交执行者处理。退出码 59 为参数错误，60–63 为包/运行环境/状态条件，64–65 为前置健康或自检，66–68 为服务/保持/GPU/drop-in，72 为中断，73 为恢复时发现未知 drop-in，74 为原服务恢复未确认。

若传输应答未知，禁止立即重发；由执行会话通过新建的只读观察确认 `.sent`、`.exit`、相应日志尾部及服务状态。存在 `.sent` 而没有 `.exit` 时不能证明后台已停止。只有明确先前阶段结束、自动恢复结果以及当下静止窗口后，才可使用恢复脚本。它提供恢复入口，不保证损坏的传输或设备一定可由软件恢复；不得把重启、刷写或恢复设置当作默认后续动作。

`restore.sh` 先核对所有待删除 drop-in 仍等于本轮模板，未知内容保留并退出；然后只删除本轮文件并重启本轮触及的原服务。恢复成功后的重复调用只验证，不重复重启。它不删除照片、回放记录、全卷数据或其他会话文件，不清理 `/tmp/hbl-x1d-rp`，不改 `/etc` 或原厂程序。已经生成的 JPEG/记录及保存过的设置不属于软件卸载可撤销的内容。

GUI 重启沿用原厂 Wayland 参数与 `ExecStartPost`，包括原定义中条件创建 RTC 链接的行为；这是服务重启的实际副作用。临时目录与 `/run` 配置不构成持久固件更新，也没有生成可刷 CIM。

## 已验证与仍待实机验证

离线通过：当前生产候选像素、缓存与 ARM provider/编码边界回归；两份新增 ARM ELF 的依赖/符号版本及 glibc 2.22 重定位表连续布局；QML 注入 Timer 14 项宿主 Qt 检查；实际 ARM provider 会话准入 4 项；安装/恢复契约 26 项；传输契约 10 项；完整归档的真实 shell 解码、tar 解包与成员摘要。详见包的证据摘要绑定。宿主 Qt6、服务/DBus/GPU 替身及 Windows ACL 均不冒充目标 Qt5.5、服务或 Linux 权限实测。

设备阶段仍要验证原动态链接器/初始化器和 QML 接入、真实 DBus/CloseFile/记录发布、预览与 Full 的颜色/方向、切图/取消/上下文重建、实际纹理上传与机内内存/速度，以及真实恢复。GPU 能力准入只排除已知缩图/通道复制条件；GL 上传内存不足仍没有自动回退，`createTextureFromImage` 成功不等于后续 bind 上传成功。单张 Full CPU 像素为 200,410,112 字节，不代表整机总峰值。

装载脚本不触发拍摄或读取测试照片。功能验证由执行会话按当次授权选取材料和安排操作，不伪造完成记录。全部本地产物只属于本候选，原 `replay-v1/v2/v3` 和无线引闪目录保持原边界。

## 本地复现

生产候选构建及核心回归见 [README](README.md)。本包的后续步骤为：

```text
python -B x1d/candidates/replay-next/tools/build_session.py
python -B x1d/candidates/replay-next/tools/audit_session.py
python -B x1d/candidates/replay-next/CodeTests/run_session_qml.py
python -B x1d/candidates/replay-next/CodeTests/run_session_gate.py
python -B x1d/candidates/replay-next/CodeTests/run_install_contract.py
python -B x1d/candidates/replay-next/CodeTests/run_transfer_contract.py
python -B x1d/candidates/replay-next/tools/audit_load_preparation.py
python -B x1d/candidates/replay-next/tools/build_session_package.py
python -B x1d/candidates/replay-next/CodeTests/run_package_contract.py
```

构建器拒绝当前源码、模块或已绑定报告的摘要失配，不会自动访问设备。任何脚本/组件改动后先重新运行受影响验证并重新生成包；旧包摘要不能覆盖新文件。
