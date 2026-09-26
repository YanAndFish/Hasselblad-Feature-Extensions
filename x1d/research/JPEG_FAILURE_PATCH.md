# JPEG 错误处理的离线组件候选

仅适用于官方第一代 X1D-50c **1.25.0** 的 `jpeg-daemon`。原文件 SHA-256 为 `ad4092c0a36344427d018af03c9ff8b5524c02627edadaab7217641ac3bf274a`。候选、逐区域修改和生成哈希在 [组件目录](../artifacts/jpeg-failure-v1/manifest.json)，生成器为 [patch_jpeg_failure.py](../tools/patch_jpeg_failure.py)。原官方包与基线未覆盖，没有生成 CIM。

**这一步已实现并验证错误传播候选，尚未实现完整 JPEG 回放增强，也未验证机身可安装性或速度改善。**

## 改动与原因

原 `ImxEncoderWorker` 已能分段取出并复用 8 MiB 物理码流缓冲，累计结果不是固定 8 MiB 文件上限。已发现的缺口是取出/更新失败仅记录警告，外层可能继续发送成功结果。另一个连接缺口是 `ImxEncoder::onEncodeFailed` 会发送空 `QByteArray` 完成通知，`Encoder` 随后调用 `ConvertCall`，后者原来不判空就调用存储写入。

候选保留原编码、分段复制、跨尾复制及队列结构，只改七处区域：

- `0x234fc` / `0x2354c`：Get/Update 错误返回原非零状态。
- `0x258a8` / `0x258d0`：忙循环和 GetOutputInfo 前检查取出状态，失败时先调用 `vpu_SWReset(handle, 0)`，再进入原失败通知与清理。
- `0x25904`：最终取出失败不发成功；GetOutputInfo 已返回后不追加 reset。
- `0x1e080`：`ConvertCall` 对空结果直接返回。上层原完成通知、删除 Call 与推进队列仍执行，避免因取消通知而挂住队列。
- 原输出错误前缀改为通用 transfer failure，适用于取出与 OutputInfo 失败。

新增短适配放在已重定向、不再使用的错误日志区；ELF 大小、节表、动态链接表和 ARM 异常表保持。Qt 调用的返回位置保持，适配不额外建立 C++ 栈帧。公共 1.25.0 `libvpu` 的 SWReset 已静态检查实例有效性与 pending instance，MX6 路径会请求硬件 reset 并释放相关信号量；**这些资源恢复动作没有在真实 VPU 上验证**。reset 自身失败仍阻止本次结果发布，不能据此保证后续编码资源已恢复。

## 离线验证

[ARM 验证程序](../CodeTests/jpeg_failure/test_arm_path.py) 通过 Unicorn 执行原版与候选的取出循环，以及原 `ImxEncoder`、`Encoder`、`ConvertCall` 完成链。VPU 返回、Qt 数据操作/信号递送和 Storage 是有界替身；使用人工码流，没有读取或保存用户照片。

6 个测试方法中的 **24 组执行场景**全部通过，详见 [验证结果](validation/jpeg-failure-arm.json)：

- 8 MiB 内、恰好 8 MiB、跨 8 MiB、超过 16 MiB，多阶段跨尾、空/非空末尾；原版与候选均逐字节匹配独立预期值，每个非空段消费一次。
- Get/Update 在两个中途阶段、OutputInfo 前和之后分别失败：候选仅通知一次失败，不写文件，队列推进一次。
- 原版对照复现了允许失败后继续交付部分结果、以及上层失败后将空结果交给写入的路径。这是指定替身返回下的路径证据，不是故障发生率或机身损坏记录。
- OutputInfo 失败、reset 失败不发布结果；各次 drain 返回保持 SP 和 callee-saved 寄存器。拒绝非固定基线，并检查相关 ELF 结构未变。

测试未覆盖真实 VPU 编码、完整 JPEG 解码质量、Qt/DBus 实际联调、写卡完成/断电持久性、实机资源恢复和异常注入的所有类型。下一环节是接入真实写入完成确认，随后才是 Full 替换 Quarter、同文件内嵌预览与统一回放来源。
