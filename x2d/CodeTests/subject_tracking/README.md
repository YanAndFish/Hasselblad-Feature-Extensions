# Offline Subject Tracking Checks

`test_subject_tracker.c` uses synthetic grayscale images to check the original `x2d/subject-tracking` core: selection, delayed observations, timeout, cancellation and mismatch. The default public verification entry builds and runs this check.

No device-memory or AF APIs, neural models, third-party post-processing or video footage are provided. Template matching does not imply neural detection or identity recognition, and no camera integration is claimed. See [index](../../../README.md).

---

## 中文

`test_subject_tracker.c` 使用合成灰度图验证 `x2d/subject-tracking` 的项目自写核心，覆盖目标选择、延迟观测、超时、取消与失配。默认公开验证入口会编译并运行该检查。

当前不提供设备内存/AF 接口、神经模型、第三方后处理代码或视频素材。灰度模板匹配不等于神经检测或身份识别；没有相机联调承诺。

当前组件与机型关系见 [公开索引](../../../README.md)。
