# 920K 文件内预览候选

对象是第一代 X1D-50c 官方 **1.25.0**。按用户最新尺寸要求，预览固定 **1108×830＝919640 像素，JPEG 质量 85**，接近原图比例；从 Full 8176×6128 主 JPEG 以 1/4 DCT 缩放得到 2044×1532 RGB，再生成预览。没有将 1022×766 的旧中间图插值放大，也没有继续使用 640×480 或降尺寸分支。

## 封装与兼容性

920K 的复杂人工图案在 Q85 时分别产生 606824 和 674192 字节预览，超过标准 Exif APP1 可容纳范围。因此当前候选把预览存入同一主 JPEG 的自定义 **APP15 分段**，标识为 `X1DPV01\0`。它**不是标准 Exif IFD1 缩略图**，不承诺第三方软件会识别这份自定义预览。

新段放在主图 SOI 后；其后的原 JPEG 内容逐字节保留，包括 Exif TIFF、MakerNote 的内部偏移、ICC 和主图压缩流。原 ICC APP2 同时复制进预览 JPEG。方向由主图 Exif 继承，编码时不旋转像素。Pillow 已能正常打开人工封装成片，主图解码像素与封装前完全一致；这不等于已经验证所有照片软件。

每段在 `FF EF` 与两字节长度后包含以下字段，全部整数为大端：

| 字段 | 字节 | 含义 |
|---|---:|---|
| 标识 | 8 | `X1DPV01\0` |
| total | 4 | 全部预览 JPEG 字节数，包含复制的 ICC |
| index / count | 2 / 2 | 从零开始的段号与总段数 |
| offset | 4 | 本段在逻辑预览 JPEG 中的偏移 |
| 数据 | 1～65513 | 除最后一段外必须占满 65513 字节 |

总预览上限 3 MiB，段数上限 64，读取头部上限 4 MiB；总长度、连续偏移、顺序和数量必须一致。提取后再检查完整 JPEG、精确尺寸及 ICC 一致性。仅通过头目录检查不能证明预览解码成功，更不能证明主文件已写完。写入状态由原存储 CloseFile 成功回执单独约束。

## 实际验证

- [分段验证](validation/preview-segments-native.json)：4 个方法，6 个精确段边界，缺段、重复、乱序、截断、数量与长度越界、错误偏移、错误尺寸、ICC 不符，以及输入/输出容量和重叠检查；关键提取与拒绝路径在 ARM 上执行。
- [容器回归](validation/jpeg-container-native.json)：7 个方法，含大小端和方向组合、完整主图像素不变、MakerNote/ICC 保留、800 次有界变异与截断。使用人工图像。
- [原 ARM 编解码库联合验证](validation/jpeg-preview-arm-codec.json)：3 个方法。原 1.25.0 TurboJPEG 执行编解码，新 C 执行缩放和封装。人工图结果为 76910 字节、1108×830、Q85；库内存分配峰值 15009600 字节，最大单次分配 9394224 字节，结束后无残留分配。libc 内存/错误函数是有界替身，SIMD 使用 portable C 分支。
- [复杂图案容量验证](validation/preview-920k-capacity.json)：真实主机 JPEG 编解码回调配合同一 C 流程；两组复杂图保持 Q85、920K 并能逐字节提取，极小容量则失败且不发布输出。
- [颜色和方向](validation/display-pixels-native.json)：40 个 ARM 方位用例与 Pillow 一致；固定原厂 Adobe RGB ICC 转 sRGB 的 4352 组颜色与 LittleCMS 比较，最大通道差不超过 2。没有测量或校准机身屏幕。

显示转换依据为原固件 ICC 的矩阵/TRC，以及 [Adobe RGB 编码定义](https://www.adobe.com/digitalimag/pdfs/AdobeRGB1998.pdf)与 [ICC sRGB 定义](https://registry.color.org/rgb-registry/srgb)。只接受该固定原厂 ICC 或原 sRGB 路径，其他 profile 交回原回放。

## 原生接入状态

[jpeg_adapter.cpp](../native/jpeg_adapter.cpp) 已实现绑定原 `StorageProxy::image` 请求与 `writeFile`、生成预览、只提交一次写入，以及成功关闭后保存完成记录。配对使用本次请求路径、Exif `ImageUniqueID`、RAW 头指纹；目录同名本身不构成匹配。新增记录位于候选运行时的独立 `/media/data/x1d-replay-v2`，不改原数据库结构。当前电脑上没有安装或创建这份机内运行目录。

[replay_provider.cpp](../native/replay_provider.cpp) 已实现包装原 `imagestore` provider：浏览读取并提取预览段，放大读取同一文件主图并检查完整摘要。无法确认、读取/解析/解码失败时调用原 provider。没有对应记录的 RAW-only 路径不生成额外 JPEG。对有完成记录的 URL，固定 Qt 5.5.1 加载入口会跳过旧 pixmap 缓存，以免早期 RAW 回退被持续复用。

预览生成的上述约 15 MB 是测试中 codec/工作缓冲分配，不包含所有 Qt QByteArray、文件和进程内存。Full 显示使用一张约 200 MB 的 BGRA 像素缓冲；转置方向额外使用约 6.3 MB 位图，没有第二张完整像素缓冲。适配层限制同时持有的一张 Full CPU 图，并在纹理上传或对象销毁后释放；原 provider、Qt/GPU 和进程的实际总峰值仍待验证。

两份独立 ARM `.so` 已链接，见[构建清单](../artifacts/replay-adapter-v1/manifest.json)；[ABI 静态审计](validation/replay-adapter-abi.json)通过了固定调用点、hard-float、动态导入与 PLT 接入检查。**Qt 对象生命周期、实际 DBus/FARM 往返、完成记录与 GUI 的联合运行、GPU 纹理创建尚未执行联调。** 因而不能把这些候选称为已可安装、完整联调通过或已改善实机卡顿。没有生成 CIM、安装服务配置、连接相机或测量相机速度。
