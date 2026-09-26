# AF 代理曲线测试输入

公开候选使用 [SyntheticAfCurves.json](CodeTests/Fixtures/SyntheticAfCurves.json)，由 [生成器](CodeTests/generate_synthetic_curves.py) 直接计算八条解析高斯曲线。它不读取照片，不含用户图片的像素、哈希或衍生指标；各字段名仅用于兼容旧测试接口。

本次仅验证样本可重建、数据结构与数学性质，不声称历史 ARM 闭环在新样本上已通过。既有验证器读取新文件，必须重新构建和执行，不能沿用旧报告。

```powershell
python -B x1d/af-experiment/CodeTests/generate_synthetic_curves.py --output x1d/af-experiment/CodeTests/Fixtures/SyntheticAfCurves.json
```

`test_user_images.py` 保留用户自行指定本地图像的分析功能；`extract_native_user_images.py` 的历史曲线比较现在要求显式 `--reference`。这些外部输入及生成记录不随源码分发，也不纳入公开测试结论。高斯模糊或解析曲线都不等于镜头真实离焦、FPGA 统计或实机对焦效果。
