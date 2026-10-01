# Fixed Algorithm Comparison Fixtures

Three fixed source files compare old and new algorithms without changing baseline bytes. Inputs are generated; no photographs or device data are included.

| File | SHA-256 |
| --- | --- |
| baseline-onboard-four.c | d5e0bab99e70efb363a9d54ca1d66f5672f80e468ce446284ad47a373492d626 |
| baseline-small.c | 6ac49c4277c1a79f59ff49212161c02c97d3cc58ff1ce86c01be23a3bf8e169b |
| onboard_six_rows.inc | 9360df1cd6c84b9f5e187053b5e0d2b8175a6caf7c77c2603934c24b6f79f0f9 |

Do not change fixtures together with the candidate algorithm. Use the [component entry](../../README.md) and specify an output directory. Passing comparisons does not establish camera-backend integration.

---

## 中文

三个固定源码文件用于新旧算法对照，字节保持不变；输入由脚本生成，不包含照片或设备数据。

| 文件 | SHA-256 |
| --- | --- |
| baseline-onboard-four.c | d5e0bab99e70efb363a9d54ca1d66f5672f80e468ce446284ad47a373492d626 |
| baseline-small.c | 6ac49c4277c1a79f59ff49212161c02c97d3cc58ff1ce86c01be23a3bf8e169b |
| onboard_six_rows.inc | 9360df1cd6c84b9f5e187053b5e0d2b8175a6caf7c77c2603934c24b6f79f0f9 |

不能随候选算法一起修改基线。从[组件入口](../../README.md)运行，明确指定输出目录。对照通过不代表相机后端接入完成。
