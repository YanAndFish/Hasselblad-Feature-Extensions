# X1D replay-next 装载前准备

2026-09-12。仅针对第一代 X1D-50c 官方 **1.25.0**。本轮按用户“先完成这些，先不实机联调”继续离线准备；没有连接相机、读取用户照片、启动设备服务或安装组件。

**本页保留装载前的静态分析；可执行交付现从 [SESSION_LOAD_RUNBOOK.md](SESSION_LOAD_RUNBOOK.md) 进入。** 用户随后要求完成可直接装载的交接包，已有分阶段传输、安装、健康/GPU 检查与撤销脚本，`packageReadyForDelegatedLoad=true`。本页静态报告仍为 `loadReady=false`，实机版本、映射、服务、入口执行和 GPU 上传仍未验证。旧的恢复研究描述的是当时状态，不代表相机目前仍处于错误 1000。

## 组件与依赖核对

总报告：[review.json](artifacts/load-preparation/review.json)。完整文件摘要、原包链接关系及依赖图分别见 [inputs.json](artifacts/load-preparation/inputs.json) 和 [dependencies.json](artifacts/load-preparation/dependencies.json)。

从固定原包补提取了 40 个 ELF 文件，共 42,024,994 字节，仅存入本候选的 `artifacts/load-preparation/inputs/`；未覆盖旧缓存、旧候选或运行组件。原 CIM SHA-256 为 `1b224ebe1f53d04a4352897c1ac1f50bc858d08048957382e4cb51ab16a5adf2`，解密后的 rootfs 摘要与既有固定清单一致。提取时只在内存中解析既有参考解包器的固定 Git blob，没有保存参考源码或密钥。

| 配套产物 | 消费者与用途 | 离线结果 |
|---|---|---|
| `full-jpeg-v1/configstore.elf` | 新启动的 configstore，X1D JPEG 尺寸范围固定 Full | 原输入、候选摘要、52 字节补丁与清单完全对应 |
| `jpeg-failure-v1/jpeg-daemon.elf` | JPEG 编码进程，失败传播 | 原输入、候选摘要及全部补丁字节对应；也是适配库运行校验要求的程序 |
| `libx1d-jpeg-adapter.so` | 仅匹配 JPEG 进程；验证主图、制作预览、完成回执后登记 | 当前构建及既有 ARM 模拟证据一致 |
| `libx1d-replay-provider.so` | 仅匹配原 `victory-gui`；JPEG 预览/Full 回放、记录更新通知 | 当前构建及既有 ARM 模拟证据一致 |

以上不是四个独立可随意混用的安装包。新拍 Full 需要整套配合；只装 provider 不会为旧照片补造完成记录。`storage-daemon`、Qt、原共享库及 GUI 保持固定输入版本，本方案没有 storage 补丁。确切本地产物路径和完整 SHA-256 由报告逐项提供，未来接收者必须重新核对，不能只凭文件名。

依赖核查分别建立每个进程的 `DT_NEEDED` 递归闭包，包含 ELF 解释器和候选显式打开的 TurboJPEG，按符号名称、默认/非默认版本和各库的版本定义匹配：

| 进程 | 闭包文件数（含候选/进程） | 匹配符号引用数 | 缺失强符号 |
|---|---:|---:|---:|
| jpeg-daemon | 30 | 3,984 | 0 |
| victory-gui | 35 | 8,778 | 0 |
| configstore | 19 | 2,217 | 0 |
| storage-daemon | 30 | 5,275 | 0 |

另外核查了 15 个 `dlsym`/`RTLD_NEXT` 所需的原导出。闭包相互重叠，表中引用数不等于唯一符号数。报告保留未匹配弱符号；弱引用允许为空，不据此推导所有运行路径安全。没有执行原 Linux 动态链接器、重定位或初始化器，也未覆盖运行时选中的 Wayland/QML 插件；多份导出都存在不能证明实际 interposition 顺序正确。

运行校验还需注意：检查磁盘文件摘要不等于检查进程已映射的内容。原 GUI/JPEG 为 `ET_EXEC`；固定 QtQuick 为 `ET_DYN`，首个链接时装载地址为 `0x4bcb0000`。会话包中的完成通知跟踪已由固定返回地址改成实际 `QQuickImageBase::load` 地址加 `0x1a8`；原版本对应 `0x4be613cc`。该偏移经原 Qt 调用点静态核对，尚无本轮实际装载偏移与运行绑定证据。

## 装载与回退流程约束

原包的四份服务配置已经逐项对照固定摘要，见 [services.json](artifacts/load-preparation/services.json)。JPEG、GUI、configstore、storage 均配置自动重启；GUI 还以 Wayland 平台启动，带环境变量和 RTC 链接处理的 `ExecStartPost`。不能把启动程序或替换文件当成无副作用的文件操作。

下表是装载/回退约束；对应实现和准确执行命令现见[会话操作说明](SESSION_LOAD_RUNBOOK.md)。脚本契约已离线验证，实际入口与恢复执行尚未实机验证。

| 阶段 | 必须得到的证据 | 不满足时 |
|---|---|---|
| 接收前核对 | 主任务确认独占设备窗口；实机型号/固件、当前文件与映射、当前服务状态，且待机切换问题已处理 | 保持离线候选，不启动装载 |
| 准备回退 | 记录此次涉及的原组件摘要和启动配置；明确候选启用位置、撤销方法、失败时仍可到达的恢复入口 | 不进入会改变服务状态的步骤 |
| 进入装载窗口 | 按确认的方法处理自动重启与待机；证明无活动写卡/编码，不用强杀代替写入完成 | 停止推进并由设备任务处理当前状态 |
| 暂存与核对 | 四个配套文件逐项匹配；作用域只落在目标进程；保留原程序与配置；候选不能通过全局预加载影响其他服务 | 不启用候选 |
| 按依赖启用 | 正常启动入口得到确认后，先有有效 configstore，再确认 storage 就绪，随后验证 JPEG 与 GUI 的目标实例及实际绑定 | 单一进程存活不足以判成功；按预定回退入口处理 |
| 后续受控验收 | 先看绑定与原回放，再验证真实完成记录/预览，最后在 GPU 条件满足后验证 Full | 出现异常停止扩大测试；记录具体阶段 |
| 回退验收 | 撤销本次候选的启用配置，恢复匹配原组件及原启动方式；确认原 JPEG 尺寸行为、回放和服务稳定 | 不把“重启过”或“文件已恢复”作为恢复成功 |

回退不包括删除照片、重置全部设置、清理整个 `/media/data` 或使用 Firmware Update Retry。v3 完成记录与用户图像均不作为安装器的清理对象；原程序不消费这些增强记录。即使只恢复 configstore 程序，也仍需核对有效配置，不能承诺服务运行期间的持久设置自动全部还原。

对用户态临时装载，已加载到旧进程中的库不会因磁盘文件替换而自动更新；撤销文件也不会自动卸载当前进程里的库。未来必须通过已确认的服务生命周期管理完成启用/撤销，且不能引入重启循环。

整包 CIM 是另一条路径，当前不制作可刷包。固定脚本会改另一组 Linux 分区并涉及 FARM、SUC、FX3 等控制器；Linux 试启动回退不能覆盖全部控制器。详见 [INSTALLATION_FEASIBILITY.md](../../research/INSTALLATION_FEASIBILITY.md)。它不能作为本候选用户态装载失败时的默认恢复动作。

## GPU 判定条件

固定 Qt 5.5.1 的完整相关片段和条件推导见 [qt-texture-path.txt](artifacts/load-preparation/qt-texture-path.txt)、[gpu-path.json](artifacts/load-preparation/gpu-path.json)。当前工厂使用 `createTextureFromImage`；以下针对其默认 QSGPlainTexture 路径，尚无实际 GPU 上下文执行证据。

候选传入 `Format_RGB32`，行跨度恰为 `width * 4`，可避开固定代码中的初始格式转换和行跨度复制。其余分支仍需要条件满足：

| 条件 | 固定 Qt 的行为 | 验收要求 |
|---|---|---|
| 最大纹理边长 ≥8176，未触发 NPOT/mipmap 重采样 | 可保留 8176×6128；旋转时为 6128×8176 | 核对真实尺寸与上传尺寸，不能只看 provider 报告的尺寸 |
| 任一维超过上限 | 每维分别取上限后缩图，例如假设上限 4096 时变成 4096×4096 | 当前路径不能通过 Full 分辨率验收；须调整实现后另测 |
| 真实走 Qt 支持的 BGRA 分支 | 无需 BGRA→RGBA 的 CPU 通道交换 | 核对 Qt 实际采用的扩展分支，仍须测驱动内存 |
| 不走 BGRA 分支且未先缩放 | 对共享/只读 QImage 做交换可额外分配 200,410,112 字节，约 191.1 MiB | 当前不能认定排除了第二份 Full CPU 像素 |
| 请求 mipmap 且缺少 Qt 的 NPOTTextures 能力 | 8176×6128 可扩成 8192×8192，仅重采样缓冲就有 268,435,456 字节 | 明确实际 mipmap/NPOT 状态并验证；该数字还未包括 mipmap 存储 |

固定 GUI 的 QML 未发现 `mipmap` 文本声明；这不是最终纹理状态证据，也不能排除原生代码改变过滤设置。表中 4096/8192 都是假设值，不是相机实测上限。

原 provider 的 CPU 失败回退发生在返回 texture factory 之前。实际 GL 上传在后续 `QSGPlainTexture::bind()` 内发生；GL 内存不足、上传错误不在当前回退逻辑覆盖范围。普通纹理创建成功也不代表上传成功。候选本轮没有改写这一点，不将失败回退测试扩大解释为 GPU 故障回退。

如实机能力不满足，先暂停 Full 验收，离线评估专用上传或分块纹理方案；目前没有已实现的 GPU 自动降级、分块 Full 显示或上传错误回退。即使 BGRA 分支无额外 Qt 像素复制，JPEG 数据、两条预览缓存、旧 provider、驱动 staging 和 GPU 仍会另占内存，总峰值只能后续实测。

## 后续设备窗口需补充的最小证据

- 当前型号/固件、配套组件摘要、实际映射地址与原导出绑定；不记录设备序列号或照片身份。
- 正常装载/撤销入口、原启动配置、写入与服务静止条件；由主任务确认待机与更新切换可用。
- 实际 GUI 渲染上下文的纹理尺寸上限、Qt BGRA/NPOT 分支、mipmap 设置、最终上传尺寸、错误与峰值内存。其他进程新建的 GL 上下文不能直接替代它。
- 装载后的真实 DBus、CloseFile、记录发布与切图/取消/上下文重建证据；后续拍摄和写卡按当时授权另行安排。

本轮不采集以上设备证据，也不填写为通过。

## 复核

当前已补齐输入，以下命令均只使用本地文件，写入仅限本候选报告：

```text
python -B x1d/candidates/replay-next/tools/prepare_load_inputs.py
python -B x1d/candidates/replay-next/tools/audit_load_preparation.py
```

首次缺少输入时，`prepare_load_inputs.py --fetch-reference` 才会读取固定参考 Git blob，并从已有官方 CIM 提取依赖；不会读取相机或生成 CIM。普通运行不会联网。审计成功退出表示离线条件与固定输入一致，报告仍保留 `loadReady=false`，不会据此自动安装。
