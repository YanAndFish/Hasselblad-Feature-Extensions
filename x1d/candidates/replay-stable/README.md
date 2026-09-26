# X1D 回放稳定候选

本目录为 `replay-next` 的独立后继候选。离线构建和整包验证已完成；新版本没有装载到相机，尚不能认定旧版的 Full 黑屏、挂 logo 或时延问题已经实机修复。

- [完整交接说明](RELEASE_HANDOFF.md)
- [交付清单](releases/stable-r1/package.json)
- [完整装载包](releases/stable-r1/session.tar.gz)
- [独立传输接口](releases/stable-r1/transfer.py)
- [离线证据索引](releases/stable-r1/offline.json)
- [整包传输验证](releases/stable-r1/validation.json)
- [待执行的功能验收](FunctionalTests/replay-stability/README.md)

`stable-r1` 是候选编号。`packageReadyForDelegatedLoad=true` 只表示离线交付齐全，不表示新增硬件授权、通过实机稳定性测试或已安装。本任务已按用户要求停止装载；装载由主任务负责。

实现保留同一份原尺寸 JPEG。普通浏览直接使用 TurboJPEG DCT 缩放，Full 请求解码原尺寸；写入适配层不再生成或嵌入第二份预览。Full 的 CPU 与 GPU 引用共同持有一个许可；纹理上传失败时保留下面的预览图层。

所有固件、符号和结构结论绑定官方 X1D-50c 1.25.0 / Qt 5.5.1。旧版 `replay-next`、其兼容包，以及主任务的组合运行时均未被本候选修改。仅使用本页链接的当前证据；复制进来的旧 `run_provider.py` 等文件兼作测试基础设施，其旧 `run()` 入口不是当前候选的验收入口。
