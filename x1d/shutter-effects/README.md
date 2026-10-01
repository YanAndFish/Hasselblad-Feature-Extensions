# Animation and Audio Routing Policies

Original UI and state logic, with offline components only.

- `index.html`: local browser animation using drawn paths and installed fonts.
- `X1dShutterAnimation.qml`: property-driven QML animation without camera or audio APIs; on-camera execution has not been reverified here.
- `audio_route.h`: an abstract backend policy; no device backend is provided.
- `CodeTests/audio_route_test.cpp`: nine substitute scenarios passed.

No recordings, generated audio, fonts or manufacturer UI assets are bundled. Animation duration is a design value, not a measured camera blackout time. See [build guide](../../docs/build/BUILDABILITY.md) and [index](../../README.md).

---

## 中文

本模块来自项目自写界面和状态逻辑，当前仅保留离线部分。

- `index.html`：浏览器本地动画预览，使用程序绘制路径和本机字体。
- `X1dShutterAnimation.qml`：只响应传入属性的 QML 动画，无相机或音频接口；尚未在当前公开环境重新验证机内运行。
- `audio_route.h`：抽象读写后端的状态策略，本目录不提供设备后端。
- `CodeTests/audio_route_test.cpp`：九项替身测试已通过。

未附带录音、合成音频、字体或原厂界面资源。这里的动画时长是设计值，不是对相机黑屏时间的测量。构建方法见 [根目录说明](../../docs/build/BUILDABILITY.md)。

当前组件与机型关系见 [公开索引](../../README.md)。
