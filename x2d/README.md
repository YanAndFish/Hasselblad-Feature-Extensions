# X2D Research Components

Public entry points focus on original pixel synthesis, image utilities, target policies and offline UI. Component verification is not camera installation or capture acceptance.

| Component | Entry and scope |
| --- | --- |
| Pixel-shift scan synthesis | [Area-array reconstruction](CodeTests/pixel_shift_rgb/README.md) from four/six positional samples, approximately 400 MP target and plain-memory implementation |
| Eye preference | [Selection policy](CodeTests/face_edge_fix/README.md), without an autofocus device backend |
| Autofocus optimization | [Research candidates](CodeTests/temporary_af_speed_probe/README.md), controlled sweep parameters and fine-focus transitions; not an accepted universal upgrade |
| Electronic-shutter flash | [Synchronization scope](research/history/ESHUTTER_BRANCH_ANALYSIS.md), ordinary flash under suitable exposure conditions; no HSS or measured universal threshold |
| Subject tracking | [Grayscale core](subject-tracking/README.md) and [checks](CodeTests/subject_tracking/README.md) |
| Display controls | [Design scope](CodeTests/display_controls/README.md), without a device implementation |
| Flash UI | [Offline QML](flash-ui/README.md), using original icons |
| Verification | [Test index](CodeTests/README.md) and root build entry points |

Historical paths retain short topic summaries rather than firmware addresses, internal API analysis or device records. Older source and scripts are outside this update's component verification and are not installation instructions.

See [build methods](../docs/build/BUILDABILITY.md) and [updates](../docs/publication/PUBLIC_UPDATES.md). This directory is not an implementation for [X1D II](../X1D2/README.md) or [X2D II](../x2d2/README.md).

---

## 中文

本目录以项目自写像素合成、图像工具、目标策略与离线界面为主要公开入口。组件验证不等于整机安装或拍摄验收。

| 组件 | 内容与入口 |
| --- | --- |
| 像素超频 | [像素位移面阵扫描合成](CodeTests/pixel_shift_rgb/README.md)，四／六位置采样，约四亿像素目标输出与通用内存实现 |
| 人眼选择 | [选择策略](CodeTests/face_edge_fix/README.md)，不提供对焦设备后端 |
| 对焦优化 | [研究候选](CodeTests/temporary_af_speed_probe/README.md)，受控快扫参数与精扫衔接；不是已普遍验收的升级 |
| 电子快门闪光 | [同步范围](research/history/ESHUTTER_BRANCH_ANALYSIS.md)，合适曝光条件下的普通同步；不涉及 HSS 或实测通用阈值 |
| 主体跟踪 | [灰度模板核心](subject-tracking/README.md)及[测试](CodeTests/subject_tracking/README.md) |
| 显示控制 | [设计说明](CodeTests/display_controls/README.md)，尚不提供设备实现 |
| 引闪界面 | [离线 QML 页面](flash-ui/README.md)，使用原创图标 |
| 代码验证 | [测试索引](CodeTests/README.md)及根目录构建入口 |

历史路径保留为简短主题页，固件地址、内部接口分析和设备记录不再出现在当前 Markdown 中。旧源码和脚本不属于本轮新增组件验证，不能把主题页当作安装说明。

构建见 [BUILDABILITY.md](../docs/build/BUILDABILITY.md)，来源见 [PUBLIC_UPDATES.md](../docs/publication/PUBLIC_UPDATES.md)。本目录不是 [X1D II](../X1D2/README.md)或 [X2D II](../x2d2/README.md)的实现。
