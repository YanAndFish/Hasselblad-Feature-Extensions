# Pixel-Shift Area-Array Scan Synthesis: Offline Components

Original pixel-shift area-array scan synthesis research using four/six positional samples. Samples from different shift positions reconstruct a denser spatial pixel grid. The six-sample target is 23326 × 17498, approximately 400 MP. It supports batched parallel reads, compute partitions, background writes and bounded dual-consumer processing in ordinary memory.

`capture_memory_view.h` defines a borrowed byte view owned by this project. Callers manage input lifetime; output data is released only after all consumers finish. It does not represent a manufacturer object or ABI.

```sh
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
```

Run from the root with Python 3.11+ and Zig 0.13.0. Inputs are synthetic, without camera access. Comparisons against the [fixed file algorithm](Fixtures/frozen-row-merge/README.md), cross-batch and failure-release checks passed, alongside ten C components and eleven Python checks.

Optional tools require NumPy, tifffile, rawpy, Pillow or libjpeg and are outside default testing. DNG is only a test container. Real capture, manufacturer rendering, 3FR, album and HEIF backends are not provided. See [updates](../../../PUBLIC_UPDATES.md).

---

## 中文

项目自写的像素位移面阵扫描合成实现，使用四／六个位置的采样，在更密的空间像素阵列上重建图像。六合一目标输出为 23326 × 17498，约四亿像素。支持分批并行读取、计算分区、后台写入和普通内存中的有界双路消费。

`capture_memory_view.h` 是项目自定义的借用字节视图，由调用方负责输入生命周期；输出全部消费完成后才释放数据，不对应厂商对象或 ABI。

```sh
python -B scripts/build_pixel_research.py --compiler zig --build-dir ./outputs/pixel-research
```

从根目录执行，使用 Python 3.11+ 和 Zig 0.13.0。输入自造，不访问相机。普通内存与[固定文件算法](Fixtures/frozen-row-merge/README.md)的像素对照、跨批次和失败释放通过，另有十个 C 组件与十一项 Python 检查。

可选工具需要 NumPy、tifffile、rawpy、Pillow 或 libjpeg，未纳入默认测试；DNG 仅为测试容器。公开内容不提供真实拍摄、原厂显影、3FR、相册或 HEIF 后端。详见 [公开更新](../../../PUBLIC_UPDATES.md)。
