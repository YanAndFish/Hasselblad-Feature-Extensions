# 回放页实例与照片引用生命周期

本目录只处理最新重新授权的页面生命周期。四 JPEG、额外照片缓存和旧读取路线保持停止。本轮没有设备请求、真实照片、安装操作或旧包改动。

**完整原厂回放页生命周期候选及独立临时装载包已实现并冻结；重启后第三次装载成功，用户实机手测反馈“回放包没问题”。** 候选改造原 MediaBrowseView、TouchWindow 和 EVFWindow 的加载/呈现边界，保留完整页面、ListView、GridView 和静态控件实例；退出时移除照片 delegate、清空放大图，并解除 Shader 图像引用。没有增加 provider 或 JPEG 缓存。

可审查接口与引用链见 [LIFECYCLE.md](LIFECYCLE.md)。代码由 [transform.py](tools/transform.py) 对固定原厂 QRC 生成，页面会话逻辑在 [page-lifecycle.inc](qml/page-lifecycle.inc)，输出只位于本目录 build/overlay。先前 [ResidentPhotoSurface.qml](qml/ResidentPhotoSurface.qml) 是基础实验，不再作为完整目标的交付依据。

独立交付的七资源清单、占用和四模块冲突见 [DELIVERY_CONTRACT.md](DELIVERY_CONTRACT.md)；[安装撤回](INSTALL_CONTRACT.md) 对应已执行的工具，[目标验收](FunctionalTests/TARGET_ACCEPTANCE.md) 记录本轮用户手测边界。当前不合并四包。

## 冻结交付

归档为 [replay-page-session.tar.gz](build/session/packages/8d960d2309f18923/replay-page-session.tar.gz)，74424 字节，SHA256 `8d960d2309f18923d80cb7b5e1fe452fc6f225260da15d5fc87b2bb1545611ad`；逐文件与证明摘要见同目录 [package.json](build/session/packages/8d960d2309f18923/package.json)。包只适用于核验通过的原厂干净基线；当前 AF/UI 会话不满足此入口，不应直接叠加。

包内含固定七资源 RCC、ARM Qt5.5 注册库、只读健康检查器、有限命令控制器和独立装载/状态/撤回脚本。它是运行期临时包，没有跨重启持久化入口。构建与冻结、离线默认校验入口均在 session/。

2026-09-13 重启后第三轮装载的最终 GUI PID 为 `1373`，七资源、七组件、LCD/EVF 两个静默页面就绪，五个服务健康，所有设备请求句柄关闭；用户随后手动测试并报告“好的，回放包没问题”。绑定回执及明确未覆盖项见 [user-acceptance-20260913.json](artifacts/user-acceptance-20260913.json)。这构成本轮独立回放模块的用户验收通过，不代表逐项性能、GPU/provider 穷尽或四模块组合验收。

本轮离线证据：37 项完整 QML 生命周期、14 项资源合同、27 项实际 shell 事务替身、12 项传输与解码、47 项实际 ARM 控制器内存仿真、21 项最终归档检查。ARM 编译使用固定原厂 Qt5.5 库；进程、服务、健康端点仍由离线替身提供，不能据此声明相机页面、原厂 provider 或 GPU 已通过。

默认命令只检查本机冻结包，不导入设备传输模块：

```powershell
py -3 -X utf8 -B x1d/candidates/replay-page-resident/session/delivery.py
```

## 原厂固定基线事实

来源为离线 X1D-50c **1.25.0** victory-gui QRC。文件哈希见 [audit.json](artifacts/audit.json)，行号见同目录 excerpts。不是当前相机运行采样。

- TouchWindow 的 media_browse_loader 默认 active=false，进入即时预览/回放时激活；EVF 的 preView 也使用 active 切换，并在激活时 setSource 带入 usedInEVF、initIndex。Qt5.5.1 的 setActive(false) 会取消 incubation，脱离可视树并 deleteLater 对象。原厂依赖销毁重建，不是仅隐藏。
- MediaBrowseView 创建时调用 SortedContentModel.showOnlyImages(false)，LCD 还调用 getAckAddedImage 消费待处理新图。常驻隐藏实例仍可能响应 ContentModel、GlobalStateInfo。grid 状态还会写 BodySync.PLAY；提前创建不能直接照常执行这一状态机。
- root.model 是 media_grid.model 的 alias，GridView 直接绑定 SortedContentModel，ListView 再绑定 grid.model。把 model 改成 null 并非独立的释放操作：根状态和大量方法访问 model.source/listSize，索引变化还写 GlobalStateInfo、调用 clearRatingLastExposure。
- 单图 delegate 的 Photo 由 loadImage 控制 source，Photo 已有 cache=false。九宫格 source 在不可见时返回 **grid_img.source 自身**，会保留已经加载的图。仅隐藏页面不能解除它。
- flick_img 和 flick_fullimg 是独立 Image，原文没有 cache=false；缩放事件直接写 source，离开 zooming 状态才清空。Photo 的 ShaderEffect.src 指向 Image 对象。缓存、当前图像对象和场景图纹理是不同层次。
- 页面析构清除 EVF 回放状态、按需要停视频，并 clearRatingLastExposure。页面常驻后，这些操作必须迁到明确的一次退出流程；还要处理自动预览、LCD/EVF 切换、空卡/目录、视频和异步完成的顺序。

## 离线验证

[test_original_page.py](CodeTests/test_original_page.py) 执行变换后的完整原厂 MediaBrowseView、原子控件，以及从 TouchWindow/EVFWindow 提取的真实 Loader 块。业务对象、视频回复和照片 provider 为明确的本地替身；宿主为 Qt **5.15.2**。37 项检查包括预建零照片/ack/业务写入、自动回放、EVF 指定及过期索引、切图、九宫格、原 delegate 放大信号、全图退出、视频与待启动视频退出、迟到图片、删除确认取消、空目录，以及两个 Loader 的同实例重入。

退出检查同时确认照片源为空、存活 Shader.src 为空、照片 delegate 的 destroyed 信号发生。测试循环显式处理 Qt DeferredDelete 事件；只调用 processEvents 并不能证明延迟删除已执行。完整 QML 用例无运行错误；Qt5.15 对旧 Connections 写法的弃用提示单独排除。来源哈希、宿主适配项和目标未验证项均在 [original-page.json](artifacts/original-page.json)。

[test_lifecycle.py](CodeTests/test_lifecycle.py) 使用已有宿主 Qt **5.15.2**，provider 只生成 32×24 纯色 QImage，不读取照片或设备。8 项验证通过：预建零请求、隐藏设置 URL 零请求、进入正常加载、退出清空 URL/状态并保留 Image 对象、重入重新请求、退出后迟到结果不恢复旧图、连续 20 次进出、以及仅 visible=false 仍会持图的负例。证据见 [lifecycle.json](artifacts/lifecycle.json)。

运行方式（在仓库根目录，依赖已存在的本地 Qt 包）：

```powershell
py -3 -X utf8 -B x1d/candidates/replay-page-resident/tools/audit.py
py -3 -X utf8 -B x1d/candidates/replay-page-resident/tools/transform.py
py -3 -X utf8 -B x1d/candidates/replay-page-resident/CodeTests/test_lifecycle.py
py -3 -X utf8 -B x1d/candidates/replay-page-resident/CodeTests/test_original_page.py
py -3 -X utf8 -B x1d/candidates/replay-page-resident/CodeTests/test_contract.py
```

Qt5.5.1 公共源码显示空 source 会清除 QQuickPixmap 并要求下一次画面更新；异步 provider 工作有取消后结果处理。固定原厂 ARM 静态代码还显示 TextureFactory 与 Texture 的共享引用清理、最终 FreeBuffer，以及依赖当前 GL context 的 glDeleteTextures，见 [原厂纹理生命周期](artifacts/original-texture-lifetime.txt)。这些证据**不证明已经开始的 provider 操作立即终止，也不证明 GPU 纹理或 OS 页缓存当场释放**；宿主纯色 QImage provider 不覆盖原厂 ARM/GL/存储端的实际执行。

## 交付边界

本候选已完成上述必要拆分，没有采用预建外壳、每次重建 MediaBrowseView 的方式。原始源码与候选均保留版本和哈希，测试不把控件创建速度或桌面内存占用当成相机性能。

目标 Qt5.5 已实际加载并通过页面就绪门禁与用户本轮手测；原厂 provider/共享缓冲、GPU 退出执行及量化性能仍没有专项穷尽证据。没有读取或下载照片、改照片写卡或恢复旧 JPEG 缓存路线；当前相机保持本轮独立临时回放包已装状态。
