# 独立回放交付、资源占用与后续冲突

当前用户计划是 AF 独立正式版先收敛，UI、回放分别测试完成后再与引闪组成四模块大包。**现在不合并。** 下列内容是只读清单与接口审查，没有创建组合资源或组合安装包。

## 七资源清单

所有字节数为 UTF-8 QML 源码，不是编译后 RAM 或传输包大小；逐文件完整 SHA256 见 artifacts/contract.json 与 artifacts/transform.json。

| QRC 路径 | 操作 | 候选字节 | 比原厂增加 |
| --- | --- | ---: | ---: |
| /components/MediaBrowseView.qml | 改造完整页面生命周期 | 105800 | 14033 |
| /common/TouchWindow.qml | LCD 预建/呈现分离 | 100689 | 177 |
| /liveview/EVFWindow.qml | EVF 预建/索引/计时入口 | 17874 | 93 |
| /browseview/MediaListViewImageDelegate.qml | 照片会话门 | 13776 | 148 |
| /browseview/MediaListViewVideoDelegate.qml | 视频预览会话门 | 3313 | 219 |
| /settings/ResidentBrowsePhoto.qml | 新增回放专用 Photo | 3667 | 3667 |
| /browseview/ResidentVideoOverlay.qml | 新增回放专用 VideoOverlay | 7686 | 7686 |
| 合计 | 5 个修改、2 个新增 | 252805 | 26023 |

14 项离线合同检查确认精确资源范围、原输入/其他资源不变、重复应用/新资源重名/关键锚点漂移拒绝，以及所用 Loader、Connections、Image 属性和清理 API 在 Qt5.5.1 公共源码中存在。API 存在不等于目标 QML 执行通过。

## 占用边界

Qt5.15.2 无照片预建测量：每个完整页面有 123 个可视 Item（含页面根）；独立页面 QObject 后代为 237 个，两窗口预建各为 123 个可视 Item。预建照片 source 数为 0。该计数只用于说明实例规模，不把它乘以猜测的对象大小估算 ARM 内存。

常驻增加的是两页静态对象/绑定与必要图标资源；照片动态 delegate 只在呈现期间存在，退出后销毁，放大 Image 留下空对象。没有压缩 JPEG 槽、预取照片或新的 native provider 缓存。目标 RAM 增量、GPU 分配、瞬时峰值和回收耗时仍是 null/未测；显示期间必要的图像内存不属于新增退出后照片常驻。

## 与其他模块的已知交点

| 模块/读取来源 | 与本回放七资源直接重名 | 仍需后续审查 |
| --- | --- | --- |
| UI resident 的 tools/build.py（3 修改 + ResidentLoader） | 没有 | 共用 victory-gui、导航与事件生命周期；正式 UI 修复版本须重新冻结核对 |
| AF delivery-r6/ui/build_resources.py（7 资源） | 没有 | AF 修改 main.qml、SettingsGeneric、ControlScreen 等，使用 GUI/Bus preload 和 hold；不能重启 GUI 后假定 AF 会话不受影响 |
| 引闪 wireless-flash/build.py 所列旧 UI 输入 | 没有 | 引闪也修改 main.qml/SettingsGeneric 并使用原生装载；最终独立正式版本须由其 owner 指定，旧构建器不是最新版本声明 |

UI、AF、引闪之间已存在 SettingsGeneric.qml/main.qml 等直接重名，虽非回放新增冲突，仍必须由四模块唯一资源编排解决。回放自身与七资源之外的变化没有组合验证；资源路径不重名不能证明并行注册多个 RCC 或叠加 preload 安全。

未来协调方应冻结四个输入、按明确变换顺序生成唯一资源视图并验证摘要，保留原生 hook 的链式调用和所有权/撤回顺序。原厂基线生成的整份 TouchWindow/EVFWindow 不能直接覆盖已组合版本；若别的模块后来也改它们，需显式审查变换锚点、active/presented 语义和窗口状态。

本任务没有调用其他模块构建器、compose 或安装器。AF 的“正式版移除调参/debug UI”不适用于删除正常回放页面；本候选保留正常回放功能。

后续执行合同见 [安装与撤回](INSTALL_CONTRACT.md) 和 [目标验收](FunctionalTests/TARGET_ACCEPTANCE.md)。37 项宿主生命周期检查与本次 14 项合同检查均为离线证据，目标验收尚未通过。

## 已冻结的独立临时包

实际归档位于 `build/session/packages/8d960d2309f18923/replay-page-session.tar.gz`，74424 字节，SHA256 `8d960d2309f18923d80cb7b5e1fe452fc6f225260da15d5fc87b2bb1545611ad`。七资源 RCC 为 `cf0515438f7f649de95df5d9e735b36145e1f9ed38d6c31364dd9c2a87b17e02`。十个普通成员为 RCC、注册库、健康程序、控制器、四个 shell、原厂基线清单及九成员摘要清单；权限/ARM 导出/逐字节归档及原厂基线共 21 项检查通过。

预留路径 `/tmp/hbl-replay-page` 和 `/run/systemd/system/victory-gui.service.d/90-hbl-replay-page.conf` 均只在本机脚本中定义，尚未在目标占用。其所有权独立，入口拒绝 AF/UI/其他 drop-in。组合包、跨重启持久化、当前 AF 会话的现场迁移仍由未来独立合同负责，不能从本包独立通过推定。

构建与事务骨架参考来源的只读摘要见 artifacts/session-source-provenance.json。实际工具均在本目录 session/，所有构建、证明和测试工作副本均写本候选；未执行其他 owner 的构建器或装载入口。
