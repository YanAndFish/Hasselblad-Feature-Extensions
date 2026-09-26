# X1D 候选版本与审核对象

仅第一代 X1D-50c 官方 1.25.0 的本地组件候选；没有可刷 CIM，没有安装或运行原相机服务。

## 已冻结的 v1

原 `x1d/native/`、原构建工具、测试与组件产物保持原样。固定副本在 [frozen-v1/candidate.zip](../candidates/frozen-v1/candidate.zip)，逐文件清单在 [manifest.json](../candidates/frozen-v1/manifest.json)。归档 SHA-256：`3816dc4ed49127f31415db9628c6522e60dd038fd3742cf52400f7711f55bef7`。后续文档可以补充，已归档的审核内容不变。

收尾发现：原 `jpeg_adapter.cpp` 在 `enhanced.resize()` 后，封装或容器复检若失败，内部准备函数直接返回；外层仍可能选择非空的中间缓冲进行一次写入。这是需要修正的错误，v1 不应当作可安装候选。没有在相机上触发或观察过此错误。

## 独立 v2

源码与工具位于 [replay-v2](../candidates/replay-v2/)，二进制和构建清单位于 [replay-adapter-v2](../artifacts/replay-adapter-v2/manifest.json)。v2 保留 v1 并仅做两项修正：

1. 在独立 `candidate` 缓冲中封装及检查；只有全部容器检查成功后才赋给待写入的 `enhanced`。失败时保留原成片输入，原写入调用仍只有一次。
2. 两份 `.so` 各仅导出两个实际接入符号；隐藏内部 C、C++ 和 Qt inline/helper 符号，缩小动态符号替换范围。

Full 配置补丁、编码失败补丁、1108×830/Q85 预览格式、分段限制及颜色/方向核心均未改变。v2 已重新编译并通过 [静态 ARM ABI 与接入点审计](validation/replay-adapter-v2-abi.json)，导出集合与两个入口严格一致。该审计没有执行 Qt 对象生命周期、DBus/FARM 写入、GPU 上传或完整回放；新的准备函数失败路径同样尚未在这些真实组件上执行。已有 C/ARM 核心测试不能充当适配层联调结果。

两个版本都不修改 `upgrade-daemon`、`storage-daemon`、原 `victory-gui` 文件、官方升级脚本、内核、U-Boot 或控制器固件。动态库目前没有加载配置或部署脚本。官方更新和恢复能否实际工作，仍需单独的入口与运行证据。

## 固定 v3 与当前 replay-next

后续 v3 位于 [replay-v3](../candidates/replay-v3/)，产物及来源绑定见 [replay-adapter-v3/manifest.json](../artifacts/replay-adapter-v3/manifest.json)。其完成记录使用 v3 格式，主图成功解码后才允许提交，并把 Full 像素和配额绑定到最后一个 QImage 引用。v3 在本轮作为固定比较基线，未覆盖源码或产物；这些实现说明不等于真实 DBus/GPU 联调已经完成。

当前优化集中在 [replay-next](../candidates/replay-next/README.md)：精确颜色快速表、原地方位分块、两条已验证预览缓存及非阻塞 Full 配额。当前候选拥有独立构建、像素回归、ARM provider 和写入准备证据；不以 v1/v2/v3 的旧报告代替本次实际执行。原三版的逐文件摘要均已[复核一致](../candidates/replay-next/artifacts/evidence/frozen-baseline-verification.json)。

当前 next 仍未装载；GPU 上传可能缩图或发生第二份 Full 像素复制，真实写卡完成、记录发布、GUI 调度、安装和恢复仍待验证。设备协调和配套条件见 [REPLAY_NEXT_HANDOFF.md](REPLAY_NEXT_HANDOFF.md)。
