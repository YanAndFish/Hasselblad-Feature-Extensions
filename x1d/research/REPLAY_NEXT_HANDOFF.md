# X1D 回放候选交接

2026-09-12。对象为第一代 X1D-50c 官方 1.25.0；当前工作区为 `.`，本轮写入限于 `x1d/`。用户最新要求“做到能直接装载的程度，装载由其他会话执行”已完成为[可执行会话包及操作说明](../candidates/replay-next/SESSION_LOAD_RUNBOOK.md)。成果入口为 [replay-next](../candidates/replay-next/README.md)，产物及固定输入摘要为 [manifest.json](../candidates/replay-next/artifacts/adapter/manifest.json)。没有进行 USB 扫描、相机连接、用户照片读取、装载或拍摄。

## 可审查成果

保持 8176×6128 Full JPEG 与同文件 1108×830/Q85 预览。新增精确颜色快速表、原地方位分块、两条已验证预览缓存、非阻塞 Full 配额，以及实际候选 ARM provider/写入准备测试。v1/v2/v3 已冻结内容和 `x1d/wireless-flash` 未修改。

颜色快速表对所有 24-bit RGB 与 v3 一致。Full 方位 scratch 从 6,262,816 降至 547,729 字节；主 CPU 像素为 200,410,112 字节。宿主分阶段性能见候选报告，不换算成相机秒数。完整 Full JPEG（sRGB、方向 1）已在有界 ARM/Qt QImage/原 TurboJPEG 环境解码；原厂 Adobe ICC/方向 6 的组合执行覆盖预览尺寸。实际卡、DBus、GUI 调度和 GPU 未运行。

失败处理分三层：无法确认来源、读取/解析/解码失败或额度占用，provider 交回原回放；编码提交点的主图未成功解码时禁止写入；主图解码通过而可选预览失败时只提交一次原 JPEG。增强写入成功回执后的记录发布逻辑已有实现，但真实 CloseFile/DBus/QSaveFile 联调尚无本轮证据。

## 装载前必须满足的条件

1. **设备与组件版本对应。** 从已获授权的设备窗口确认确为 X1D-50c 1.25.0，并核对当前组件与构建清单。不能把官方输入版本当作当前实机事实，也不能用 X2D 的地址或实验结论代替。
2. **配套候选对应。** JPEG 适配库的运行校验绑定 `x1d/artifacts/jpeg-failure-v1/jpeg-daemon.elf`，不是未修改的原 `jpeg-daemon`；新拍 Full 还依赖 [Full configstore 候选](FULL_JPEG_CONFIG_PATCH.md)。GUI 与各原共享库需匹配清单中的固定摘要。只复制两份 `.so` 不足以形成可运行方案。
3. **正常装载与恢复入口。** 由拥有设备窗口的主任务确认获授权的入口及静止窗口。当前会话包提供实际传输接口、私有 `/tmp` 和 `/run` drop-in、分阶段启用与撤销脚本，安装/恢复契约 26 项、传输契约 10 项及完整包解码/解包验证通过；目标上的执行仍未验证。不能以离线通过替代装载授权，也不制作或刷写 CIM。
4. **纹理能力和内存。** 在已授权的实际 GUI/GL 上下文确认 `GL_MAX_TEXTURE_SIZE` 至少容纳 8176×6128 与旋转后的 6128×8176，并检查 Qt 所用 BGRA 扩展及实际上传分支。若不满足，当前默认 QSGPlainTexture 路径可能缩图或额外复制约 200 MB，须先调整方案。无实机总内存峰值证据；配额只约束本候选 CPU 图像，原 provider 与 GPU 的分配另计。
5. **文件完成与源身份。** 实际成功关闭后才能看到完整 v3 记录；确认 RAW/JPEG 配对、记录失败时原回放、无记录 RAW-only 的原行为。不得用伪造完成记录绕过真实写入确认。

当前仅有离线施工授权，设备连接由主任务独占协调；本任务不自行建立第二个 USB 会话。以上是必要条件和验证顺序，不是装载或拍摄指令。

2026-09-12 主任务收到交接后的状态更新：用户因引闪组件更新期间待机切换产生的 1000 故障正常重启了 X1D；主任务报告其只读核查显示新启动为正常 Active，`/tmp/hbl-wireless-flash` 不存在。这是主任务提供的设备观察，本回放任务未读取实机。上一轮临时驻留/装载证据只代表历史状态，不代表新启动仍有该组件。主任务先处理更新流程与系统待机切换问题，回放任务继续离线，不访问 USB、不自行安装。

## 后续验收顺序

2026-09-12 用户先要求“先完成这些，先不实机联调”，该阶段补充了 [装载前准备](../candidates/replay-next/LOAD_PREPARATION.md)及[离线审计](../candidates/replay-next/artifacts/load-preparation/review.json)：40 个固定 ELF 输入、四个配套组件、四进程依赖闭包/符号版本、15 个显式查找导出与服务配置，同时细化 Qt 的尺寸、BGRA、NPOT/mipmap 和上传失败边界。

随后按最新要求形成 [session.tar.gz](../candidates/replay-next/artifacts/session-package/session.tar.gz)和[包清单](../candidates/replay-next/artifacts/session-package/package.json)。新增独立 QML 活动保持、实际 GUI GPU 能力准入、检查器和安装撤销；生产库修正 Qt 调用点的装载偏移处理、加入会话准入并修正旧 glibc 所需的重定位表布局，重建后核心回归通过。安装先校验 74 项原厂文件/别名/服务，再仅加载 UI 守护确认健康与 GPU，之后按 configstore、JPEG、GUI 顺序启用；失败自动尝试恢复。`packageReadyForDelegatedLoad=true`、`targetValidated=false`，真实 DBus、GPU 上传/内存、功能/速度与恢复尚未实测。原阶段静态审计的 `loadReady=false` 保留其含义；实际操作以会话说明为准。主任务接收本次成果不表示立即装载指令。

先在正常装载入口下确认程序存活、组件摘要和返回路径，然后验证完成记录与预览，再验证放大 Full、离开放大、快速切图、连续请求、取消与 GL 上下文重建。异常检查应使用获授权的人工测试材料；真实写卡和拍摄须按当次授权另行协调。

记录分阶段耗时：请求到完整前缀、完整 JPEG 读取、解码、颜色、方向、纹理上传与最终显示。比较原回放和候选时保持同一测试材料、缓存状态、颜色/方向、屏幕与电源条件，报告首访和重复访问。主图可用性、显示分辨率、颜色/方向正确、结束后内存/额度恢复应先于速度结论。

本轮 provider 模拟能证明 QImage 共享和释放契约、失败回退及候选 CPU 数据路径，不能证明 Qt reader 的真实取消时序。额度不足当前会交回原 provider，未增加“额度空闲后自动重试 JPEG”的功能。需要实机确认该行为是否影响连续放大体验。
