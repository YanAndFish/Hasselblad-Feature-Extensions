# Generic Grayscale Template Tracker

Original 16 × 16 grayscale templates and integer-translation search. The caller serially supplies images, selection and observations; stale or mismatched observations are rejected and a region is retained for a bounded duration.

There are no device calls, model loading or lens operations, and no claimed scale, pose or identity recognition. Host checks are in `x2d/CodeTests/subject_tracking`. See [index](../../README.md).

---

## 中文

项目自写的 16 × 16 灰度模板与整数平移搜索。调用方串行提供图像、目标选择及检测观测；核心拒绝过期或不匹配的观测，保留有限时长的目标区域。

没有设备调用、模型加载或镜头操作，不宣称尺度、姿态或身份识别能力。对应主机测试位于 `x2d/CodeTests/subject_tracking`，已接入根目录 `scripts/build_pixel_research.py`。

当前组件与机型关系见 [公开索引](../../README.md)。
