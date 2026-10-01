# 冻结行合成基线

这三个文件从先前离线并行读取对照的固定源码复制，字节保持不变；没有照片、固件二进制或设备数据。冻结实现用于独立对照新内存核心，不能随候选算法一起修改。

| 文件 | SHA-256 |
| --- | --- |
| baseline-onboard-four.c | d5e0bab99e70efb363a9d54ca1d66f5672f80e468ce446284ad47a373492d626 |
| baseline-small.c | 6ac49c4277c1a79f59ff49212161c02c97d3cc58ff1ce86c01be23a3bf8e169b |
| onboard_six_rows.inc | 9360df1cd6c84b9f5e187053b5e0d2b8175a6caf7c77c2603934c24b6f79f0f9 |

`baseline-small.c` 固定缩小计算区域，合成输入仍由测试脚本生成。`verify_capture_memory_pipeline.py` 使用它验证内存输出和文件路径输出；`verify_parallel_read.py` 从原尺寸基线重建缩小版本。构建需要脚本指定的 Zig 工具链，运行产物仍写入被忽略的 `x2d/outputs/`。

离线对照通过不代表原厂拍摄内存、3FR 写入器和显影器已接通，当前候选状态见 [内存流水线说明](../../../../research/4.2.0/PIXEL_MEMORY_PIPELINE.md)。
