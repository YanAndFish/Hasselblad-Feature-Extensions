# 原厂回放页生命周期接口与引用

范围为固定 X1D-50c 1.25.0 GUI（SHA256 见 artifacts/audit.json）。这是独立离线 QML 候选，不表示当前设备已采用它。

## 页面接口

| 阶段 | 页面与模型 | 可执行操作 |
| --- | --- | --- |
| 预建/退出后 | 完整 MediaBrowseView 和静态子控件存在；ListView/GridView.model=null，resident_idle | 只计算界面布局/纯显示属性；不消费 ack、不筛选、不写 BodySync/评级，不请求照片 |
| residentEnter(preview, evf, index) | 恢复每次会话的 flags，接入共享 SortedContentModel；图像门仍关闭 | 显式 showOnlyImages(false)，LCD 消费 ack，选定有效索引，执行所需原厂页面激活 |
| 呈现 | 打开 residentImagesEnabled；动态照片 delegate 按原视图需要创建 | 原厂翻页、九宫格、缩放、即时预览和视频流程；各 Image cache=false |
| residentLeave() | 关闭图像门及会话门、递增代次；解除两视图模型并保留页面本体 | 停动画/计时器、取消弹窗，清两路缩放 source 和 Shader.src；原退出职责执行一次 |

重复 Enter 在已呈现时只同步即时预览标志；重复 Leave 不重复清理。usedInEVF、索引和 flags 在首次呈现前设置，不利用原 Component.onCompleted 触发业务动作。页面真正销毁时调用相同 Leave，已退出的实例不再次清评级。

原生模型本身是应用共享对象，只保留其对象引用；候选没有复制照片、目录或 JPEG 到新缓存。为避免空模型访问，页面只读路径/数量通过 root.model，照片视图单独接入/断开。原厂各状态条件集中形成 residentAutomaticState，避免多个 when 接通时短暂误进九宫格；索引确定后再打开图像门。

## 照片与退出职责

| 引用/动作 | 呈现时 | 退出时 |
| --- | --- | --- |
| 单图 delegate / 元数据 / 直方图 | 原厂 delegate 加载，使用 ResidentBrowsePhoto | 断开 ListView 模型；Loader 失活并延迟销毁，旧代次不能转发结果 |
| 九宫格 Photo | 当前会话、正确代次且 grid 可见时才设 source | source 为空，不再返回原 source 自身；断开 GridView 模型并销毁 delegate |
| flick_img / flick_fullimg | 原缩放信号设置预览/全图 URL；均禁用 QML 图像缓存 | 两个 source 清空，缩放计时器/动画停止，尺寸和位置恢复 |
| Photo 的 ShaderEffect.src | 本次图片有效时指向 Image | lifecycleCurrent=false 时设为 null；对象是否存活不影响这一条件 |
| 视频预览 Photo | 独立 ResidentVideoOverlay 使用相同图像门 | 清 source；动态视频 delegate 销毁，页面 VideoOverlay 只保留空控件 |
| provider 请求 | 原厂图像 URL 继续走原厂 provider | Qt 取消当前 Image 的旧请求/结果资格；不新增 provider 缓存或自建缓冲 |
| 视频播放 | 保留原启动/状态流；记录尚未完成的启动请求 | 已播放或请求中都调用一次原停止操作；关闭防休眠并清文件名 |
| EVF 状态、评级 | 原厂呈现所需状态同步 | 清 evfBrowseViewState，调用一次 clearRatingLastExposure |
| 删除/建目录弹窗 | 原厂用户流程 | 先使会话失效再撤销 deleteFile 和 Loader，防止关闭弹窗被误当作删除确认 |

每次 Enter/Leave 都递增 residentEpoch；每个动态 delegate 在创建时固定该编号。即使旧对象因 DeferredDelete 尚未销毁，Loader 转发与 Photo 源仍必须匹配当前编号。纯 URL 和模型索引不是照片像素，退出也清除了两路缩放 URL 和视频文件名。

## 两个窗口入口

TouchWindow 的 media_browse_loader 与 EVFWindow 的 preView 均 active=true、asynchronous=true 提前创建完整页面。新 presented 字段承接原 active 的呈现用途，所有该 Loader 的原状态赋值/直接访问一起变更。退出使用 residentLeave，不清 Loader.source、不销毁 MediaBrowseView。

LCD 首次 Loaded 只连接事件与模拟布局；真正 presented 时才激活、处理待显示通知与待删除弹窗。EVF 的原 startIndex/startTimer 在呈现时传递和启动；Loaded 发生在隐藏阶段不会启动预览计时。外层事件 Connections 仅在 presented 时接通。

这里验证的是实际两个 Loader 块及完整回放页；其他 TouchWindow/EVFWindow 状态机没有作为完整窗口运行，仍需目标环境组合验证。

本目录 overlay 从原厂基线生成，尚未合成当前 UI/AF 候选。后续应把 touch/evf 资源变换应用到经确认的组合输入，核对保留其他改动；本目录输出不能直接整页覆盖当前组合资源。没有改动 UI owner 的文件。

## 原厂纹理释放的已知证据与缺口

固定 ARM 静态分析：TextureFactory 虚表的析构槽指向 0x47290；它设置共享描述对象的释放标记，存在 Texture 引用时延后实际释放。Texture 建立引用时在 0x47914 起递增计数；0x47638 析构减计数，在标记已置且归零时调用 0x7de44。该函数使用常量 FreeBuffer 构造原 storage D-Bus 调用。纹理析构中的 glDeleteTextures 还要求当前 GL context 存在。完整反汇编与哈希保存在 artifacts。

候选不替换这条原厂释放链，也不直接发送 FreeBuffer。清空 QML 图片引用只解除页面这一层的持有；已有 provider 工作、场景图、原生缓冲和存储端各自完成清理所需的时间没有实测。Qt5.15 宿主的 QImage provider 验证了 QML 行为和取消结果，不能替代 Qt5.5 ARM 与实际 GPU 的验证，更不能据此承诺 OS 缓存立即清空。
