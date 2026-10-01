# X2D Offline Code Checks

The recommended entry uses synthetic inputs, without photographs, firmware or a camera. Run from the repository root:

```sh
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
```

- [Pixel synthesis](pixel_shift_rgb/README.md): file/plain-memory comparisons, batching and bounded queues.
- [Eye preference](face_edge_fix/README.md): left/right preference policy.
- [Tracking](subject_tracking/README.md): grayscale templates and stale observations.
- [Display controls](display_controls/README.md): design boundaries.

This verification covers ten C components, eleven Python checks and memory-merge comparisons. Historical region models and AF probes were not reaccepted and are not default steps. See [updates](../../docs/publication/PUBLIC_UPDATES.md).

---

## 中文

推荐入口使用自造输入，不需要照片、固件或相机。从仓库根目录执行：

```sh
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
```

- [像素合成](pixel_shift_rgb/README.md)：文件与普通内存算法对照、分批处理和有界队列。
- [人眼选择](face_edge_fix/README.md)：通用左右眼偏好。
- [主体跟踪](subject_tracking/README.md)：灰度模板与过期观测处理。
- [显示控制](display_controls/README.md)：设计边界说明。

本轮包含十个 C 组件、十一项 Python 检查及内存合成对照。历史地区模型、对焦探针等没有在本次更新中重新验收，不作为默认步骤。摘要见 [公开更新](../../docs/publication/PUBLIC_UPDATES.md)。
