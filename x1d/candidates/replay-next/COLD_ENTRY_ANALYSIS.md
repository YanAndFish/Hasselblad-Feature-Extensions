# X1D 首次进入回放：当前结论

2026-09-13。静态基线为官方 X1D-50c **1.25.0**。分析对象为正在由主任务装载的独立包 `4ff2a1981ecf52546b0f743ea6eb6622a8aceac8db968c03262496a44c439a78`。本任务不连接相机，不读取照片，不改变该包；没有实机分阶段计时。

**当前包没有修完“首次进入回放特别卡顿”。原厂回放页面确实按需创建，但图片 provider 已在 GUI 启动入口注册。** 回放是在同一个 `victory-gui` 内运行的功能，不是按下回放后临时构建一个独立程序。LCD 和 EVF 各自通过 Loader 创建 `MediaBrowseView` 页面实例；源码中的 QML 解析、对象实例化和预先构建 ARM 模块是不同过程。

## 已确认的创建与显示链

| 阶段 | 固定来源与行为 | 可以得出的结论 |
|---|---|---|
| GUI 启动 | 原 GUI `0x26e6c` 构造原 provider，`0x26e7c` 调用 `QQmlEngine::addImageProvider`；其构造函数 `0x459e8` 创建 `SharedBufferPool`。候选在此包装 `imagestore`。 | 原 provider 和候选包装不随每次回放重新建立。池对象创建不证明所有后续缓冲已分配。 |
| LCD 页面 | 原 `/common/TouchWindow.qml:716` 的 Loader 初始 `active:false`，`asynchronous:true`；1833 行进入 browse_view 才按 EVF 状态激活。 | 首次进入存在页面实例化成本。Qt 5.5.1 的 `QQuickLoader::setActive(false)` 会安排删除加载对象；退出后也可能重建，并非只在开机后创建一次。 |
| EVF 页面 | 原 `/liveview/EVFWindow.qml:243` 的 Preview_loader 初始关闭，激活时 256 行 `setSource(MediaBrowseView, {usedInEVF:true, initIndex:…})`。 | LCD 与 EVF 使用独立实例，切换时不能假定另一端页面已经准备好。 |
| 模型与子页面 | `MediaBrowseView.qml:70` 完成回调调用 `showOnlyImages(false)`，LCD 还执行 `checkNewImage()`；1558 行另有异步 delegate Loader，之后按 `loadImage` 赋予图像源。模型引用 `SortedContentModel`。 | 页面 Ready、列表与首图 Ready 是不同节点。没有证明进入回放必然重扫整张卡，也没有模型阶段的硬件耗时。 |
| 图片工作线程 | 固定 Qt 的 `QQuickPixmapReader::instance(engine)` 按需创建共享 reader；provider 请求在其工作线程串行执行。 | 线程可能已经被其他异步图片启用，不能断言首次回放一定新建线程。异步加载不意味着没有排队或等待。 |
| 候选图片处理 | 完成记录 → 源身份 → JPEG 前缀及末尾 → 预览缓存 → 未命中时提取、解码、颜色与方位 → Texture factory。 | 缓存首次为空；命中也保留来源与文件校验。没有 v3 完成记录的旧图交回原 provider，安装本身不生成旧图记录或预览。 |
| 解码初始化 | `codec()` 第一次使用时 `dlopen`/绑定 TurboJPEG 导出；每次实际解码新建、销毁一个 decoder handle。 | 首次 API 绑定与每张图片解码器初始化应分开计时；`dlopen` 可能复用已映射库，不能一概称为首次从存储加载整个库。 |
| 上屏 | worker 返回 factory，随后 render 路径调用 `createTextureFromImage`，固定 Qt 上传在 texture bind 中执行。 | 图片解码完成不等于屏幕已显示；GPU 能力检查也不是纹理上传耗时或显存验收。 |

证据全文、原始行号、GUI 反汇编与摘要见 [excerpts.txt](artifacts/cold-entry/excerpts.txt) 和 [analysis.json](artifacts/cold-entry/analysis.json)。

## 当前包处理了什么

- 对有有效完成记录的照片，普通浏览取 1108×830 预览，放大才读取 8176×6128 主图。它不为所有既有照片提供同样路径。
- 两条共享预览像素缓存减少重复访问时的解码、颜色与方位计算。原厂 `Photo.qml:13` 已设置 `cache:false`；不能把原厂重复请求全部归因于候选新增的 Qt 缓存开关。
- 颜色快速表和原地方位处理减少已覆盖的 CPU 工作与 scratch。Full 配额由等待改为立即尝试；这修正的是额度占用时的等待，不是普通首次进入页面的冷启动。
- 完成记录刷新、失败回退与引用生命周期有实现和离线证据。真实首次进入、列表滚动、取消调度、DBus 与 GPU 总延迟尚未验收。

因此只能说部分图片处理步骤已经优化，不能说首次进入卡顿已修复，不能给出相机上节省的秒数或百分比。

## 新发现及下一版交付点

1. **重复运行库校验有静态证据。** `replay_provider.cpp` 的 provider 注册 hook 和 pixmap hook 各有一份独立的 `static runtimeMatches`。成功时每份校验读取并摘要固定八文件，共 19,828,732 字节。第二份位于 URL 筛选之前，可在开机图标等首次 pixmap 请求执行，不能认定它落在首次回放。下一版可在同一库内共享不可变版本校验结果，并以有效/失配输入和调用计数测试确认只执行一次；保留拒绝不匹配的行为。这减少重复工作，但不能单独作为原厂首次回放卡顿的修复。
2. **页面准备需要单独处理生命周期。** 原包没有修改 TouchWindow/EVFWindow/MediaBrowseView。预先实例化整个回放页会运行完成回调、模型与图像绑定；将 `visible` 设为 false 不会自动阻止它们。下一版若处理页面冷启动，应把组件准备与页面激活区分清楚，并覆盖 LCD/EVF、退出再入、卡或目录变化及页面销毁。此部分与常驻 UI 任务的资源所有权有关，不能在本任务偷偷覆盖主资源。
3. **先区分首图等待和界面卡死。** 后续获授权的观察应分别记录：用户进入事件、Loader Ready、provider 排队/开始、Storage 读取结束、解码结束、factory 返回、纹理 bind、包含该图的首帧。仅记录阶段与匿名请求编号，不记录路径、图像内容或捕获 ID。计时边界不能用 Image.Ready 代替首帧显示。
4. **改版仍须完整交付。** 如开展上述修改，应另版输出含安装、校验和恢复的完整包，保留本次原归档；应报告明确减少的工作与未测量环节。当前本文件是研究结论与交付范围，尚无“首次进入已修复”的新版包。

静态证据可复现：`python -B x1d/candidates/replay-next/tools/inspect_cold_entry.py`。该脚本只解析固定固件、已有 Qt 源码归档与候选源码，9 项静态约束通过；不启动其中程序。这些约束不证明实际机器上的主要耗时来源。

## 主任务回报的装载缺陷

主任务回报：本轮首次 UI 阶段以 64 退出，内部 preflight 为 62，尚未触碰服务；`common.sh` 的 baseline 路径字符白名单漏掉 `+`，因而拒绝清单内 `libstdc++.so` 路径。主任务正在自己的装载目录制作只允许额外 `+` 的可追踪小补丁，保留 74 项文件摘要及全部 ELF/RCC。该信息为主任务实机回报，本任务没有独立设备验证，也未改原冻结包。后续正式交付必须纳入此修复；它是安装检查缺陷，与首次进入回放的耗时无关。
