# X2D Research Components

Public entry points focus on original pixel synthesis, image utilities, target policies and offline UI. Component verification is not camera installation or capture acceptance.

| Component | Entry and scope |
| --- | --- |
| Pixel synthesis | [Four/six-frame merge](CodeTests/pixel_shift_rgb/README.md), approximately 400 MP target and plain-memory implementation |
| Eye preference | [Selection policy](CodeTests/face_edge_fix/README.md), without an autofocus device backend |
| Subject tracking | [Grayscale core](subject-tracking/README.md) and [checks](CodeTests/subject_tracking/README.md) |
| Display controls | [Design scope](CodeTests/display_controls/README.md), without a device implementation |
| Flash UI | [Offline QML](flash-ui/README.md), using original icons |
| Verification | [Test index](CodeTests/README.md) and root build entry points |

Historical paths retain short topic summaries rather than firmware addresses, internal API analysis or device records. Older source and scripts are outside this update's component verification and are not installation instructions.

See [build methods](../BUILDABILITY.md) and [updates](../PUBLIC_UPDATES.md). This directory is not an implementation for [X1D II](../X1D2/README.md) or [X2D II](../x2d2/README.md).

---

## 中文

本目录以项目自写像素合成、图像工具、目标策略与离线界面为主要公开入口。组件验证不等于整机安装或拍摄验收。

| 组件 | 内容与入口 |
| --- | --- |
| 像素超频 | [四帧／六帧合成](CodeTests/pixel_shift_rgb/README.md)，约四亿像素目标输出与通用内存实现 |
| 人眼选择 | [选择策略](CodeTests/face_edge_fix/README.md)，不提供对焦设备后端 |
| 主体跟踪 | [灰度模板核心](subject-tracking/README.md)及[测试](CodeTests/subject_tracking/README.md) |
| 显示控制 | [设计说明](CodeTests/display_controls/README.md)，尚不提供设备实现 |
| 引闪界面 | [离线 QML 页面](flash-ui/README.md)，使用原创图标 |
| 代码验证 | [测试索引](CodeTests/README.md)及根目录构建入口 |

历史路径保留为简短主题页，固件地址、内部接口分析和设备记录不再出现在当前 Markdown 中。旧源码和脚本不属于本轮新增组件验证，不能把主题页当作安装说明。

构建见 [BUILDABILITY.md](../BUILDABILITY.md)，来源见 [PUBLIC_UPDATES.md](../PUBLIC_UPDATES.md)。本目录不是 [X1D II](../X1D2/README.md)或 [X2D II](../x2d2/README.md)的实现。
