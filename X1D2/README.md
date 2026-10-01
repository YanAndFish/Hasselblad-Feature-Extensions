# X1D II Face-Priority Research

This directory provides X1D II face-priority research excerpts, maintained separately from [X1D](../x1d/README.md) and [X2D II](../x2d2/README.md).

## Included material

- `face-afs/target_select.*`: detection validation and target selection, including conditionally enabled eye-geometry candidates.
- `face-afs/target_exchange.*`: project-defined target-state exchange and consistent reads.
- `face-afs/publisher.cpp`: bounded detection and preview-processing excerpts.
- `face-afs/vendor/libfacedetection/`: a fixed upstream detector and its model parameters; original files and license are unchanged.

The exchange structure is project-defined, not a manufacturer protocol or internal API. Eye-candidate calculations do not establish accepted on-camera eye autofocus.

## Dependencies and verification

The complete publisher lacks `af_request.h`, `proxy_bridge.h`, `preview_resize.h`, and `menu_control.h`. This directory cannot build the full feature, and empty files have not been used to hide those gaps.

The detector alone builds with Zig 0.13.0. A synthetic blank 160 × 120 BGR image returned zero faces. This verifies compilation and a basic call, not detection quality or camera autofocus.

From the repository root:

```sh
python -B scripts/build_x1dii_detector.py --compiler zig --build-dir ./outputs/x1dii-detector
```

## Source and licensing

Original project excerpts use [MIT](../LICENSE). The detector comes from the fixed [ShiqiYu/libfacedetection revision](https://github.com/ShiqiYu/libfacedetection/tree/acf7b254121927e7dced30e233a2e03119f28ea2). Four source files and LICENSE match upstream byte for byte and retain [BSD-3-Clause](face-afs/vendor/libfacedetection/LICENSE). See [SOURCE.md](face-afs/vendor/libfacedetection/SOURCE.md).

No device installer, manufacturer resources, photographs, runtime records or on-camera integration dependencies are supplied. See [publication scope](../PUBLICATION_SCOPE.md).

---

## 中文

本目录补充 X1D II 的人脸优先研究片段，与第一代 [X1D](../x1d/README.md)及 [X2D II](../x2d2/README.md)分别维护。

### 提供内容

- `face-afs/target_select.*`：检测结果的范围检查和目标选择，包含受条件约束的眼部几何候选。
- `face-afs/target_exchange.*`：项目自定义目标状态交换与一致性读取。
- `face-afs/publisher.cpp`：有界检测与预览处理片段。
- `face-afs/vendor/libfacedetection/`：固定上游版本的开源检测库与模型参数，原文件及许可证保持不变。

交换结构属于本项目，不是厂商协议或内部接口。眼部候选计算不代表机内人眼对焦已经验收。

### 依赖与验证

完整发布器缺少 `af_request.h`、`proxy_bridge.h`、`preview_resize.h` 和 `menu_control.h`，不能仅凭本目录构建完整功能，也没有用空文件掩盖缺口。

检测库已用 Zig 0.13.0 独立编译，对 160 × 120 的自造空白 BGR 图检测结果为零个人脸。这只验证编译和基本调用，不评估质量或真实对焦。

从仓库根目录运行：

```sh
python -B scripts/build_x1dii_detector.py --compiler zig --build-dir ./outputs/x1dii-detector
```

### 来源与许可

项目自写片段适用根目录 [MIT](../LICENSE)。检测库来自 [ShiqiYu/libfacedetection](https://github.com/ShiqiYu/libfacedetection/tree/acf7b254121927e7dced30e233a2e03119f28ea2)，四份源码及 LICENSE 与固定上游逐字节一致，适用原始 [BSD-3-Clause](face-afs/vendor/libfacedetection/LICENSE)。来源见 [SOURCE.md](face-afs/vendor/libfacedetection/SOURCE.md)。

不提供设备安装包、厂商资源、照片、运行记录或机内接入依赖，详见 [公开范围](../PUBLICATION_SCOPE.md)。
