# 八张后持续忙灯：离线复核

本记录依据 Main 转达的用户观察、冻结 stable-r1 源码和原厂 **X1D-50c 1.25.0** 文件。未连接相机，未读取卡内照片。本文地址均属于该固定原厂版本，不能跨版本套用。原厂文件哈希及反汇编见 [factory-lifecycle.json](artifacts/diagnosis/factory-lifecycle.json)。

## 现场事实与未知项

用户最终澄清：手动回放能看前面的八张；第八张之后自动回放变黑，写卡忙灯持续红色；取卡在电脑查看，只见八张 3FR，没有 JPEG。测试中拍了十几张，但无法确认这八张是否全部来自本轮测试。Main 当时只读看到 16 个 pending 文件和服务运行状态；这些信息不能证明固定八槽耗尽。原现场已经正常重启，无法事后取得当时队列状态。

## 已确认的新增行为

冻结包 `1df99fb712e23c10ada543b2b58ded609ad289d9c16993317cf7414b340469b0` 除显示读取外，还替换 configstore、jpeg-daemon，并注入 JPEG 生产适配器。

- configstore 补丁把 JpgSizeMinMax 改为 Full；这不是把 ImageFormat 设置成 RAW+JPEG，也不是当前相机设置的读数。
- jpeg-daemon 补丁修改 VPU 错误路径及空输出处理，属于生产链变化。
- 适配器在编码请求前创建 pending；在原 writeFile 前进行结构与 EOI 位置校验。失败分支直接返回本地错误 watcher，原 writeFile 不执行。
- 结构有效却没有受支持 UniqueID 时，原 writeFile 可以执行，但不建立发布上下文。错误回执、目标不符、完成记录提交失败等也可能永久保留 pending。
- 旧 provider 在检查 pending 前已经尝试读 JPEG；pending 存在会阻止显示。catalog 只读取原 ContentModel 缓存，没有增删原列表行。

因此，“pending 不清导致无法显示”和“提前拒绝 JPEG 写入”均为真实代码分支；它们不能单独证明后续 RAW 缺失及持续红灯的唯一原因。

## 原厂完成及释放链

原厂 ConvertCall::complete 在 `0x1e2dc` 调用 `StorageProxy::writeFile`，从 `0x1e2e0` 开始不检查返回 watcher，而进入局部对象清理。

`Encoder::onEncodeFinished` 在 `0x1af04` 调用当前任务的完成回调；返回后在 `0x1af1c` 调用删除析构，`0x1af28` 清空 current，`0x1af2c` 继续队列。ConvertCall vtable 在 `0x3a094`/`0x3a098` 分别指向普通析构 `0x1d30c` 和删除析构 `0x1d75c`，完成回调槽 `0x3a0a0` 指向 `0x1e080`。删除析构检查 `this+0x18` 缓冲指针，非空时于 `0x1d7c8` 调用 `StorageProxy::freeBuffer`。另有 `Encoder::onReleaseBuffer` 的正常释放入口。

另以 Unicorn 执行了原厂 `onEncodeFinished`、`ConvertCall::complete`、删除析构和 Qt 字符串/字节数组代码：writeFile 返回空或非空指针，分别配合有/无缓冲区，共四种情况，均删除当前任务并进入下一任务；有缓冲区时均请求 freeBuffer。此测试的 writeFile、freeBuffer、日志和后续队列是替身，没有构建真实错误 watcher、等待缓冲归还回执或运行真实 D-Bus。执行还确认原厂目标扩展名为大写 `.JPG`。见 [completion-execution.json](artifacts/diagnosis/completion-execution.json)。

这些证据反对“返回一个本地 failed watcher 必然阻止任务删除和缓冲归还”的直接推断。若执行尚未到达 encodeFinished、freeBuffer 异步处理未完成，或上游存在其他停滞，仍需现场证据辨别。没有实测证明上述链在故障当时执行到了哪一步。

原 `DBusProxy::onFinished` 调用的是 `deleteLater`，不能据此认定 watcher 被抢先同步删除。原生产链涉及实际 D-Bus 回执、存储和事件循环；旧模拟测试没有完整验证成功关闭后发布与 QSaveFile 提交。

## 本次修订

reader-r1 只接入 victory-gui。包内不含生产适配器、configstore 或 jpeg-daemon 替换文件，安装和恢复不修改或重启这些服务。新增 native provider 不导入 StorageProxy 的 image、writeFile、freeBuffer，不包含记录读写或 JPEG 压缩入口。因此不再需要接管原厂完成 watcher，也不新增完成记录生命周期。

只读同目录同名 JPEG，并在内存中检查和解码；有可用 JPEG 时不另读 3FR。读取端接受解析器支持的 EOI 后最多 511 个零字节，不再额外强求 EOI 等于文件长度。这只是兼容性修正，未证明故障照片实际包含填充。原厂采集格式枚举与故障时真实设置没有完整核实，本文不把“无 JPEG”单独归因于 RAW-only 设置。

本次未复现持续红灯，不能标记现场根因已解决。原厂 Qt5 自动回放事件循环、模型采集及实际 GPU/卡操作仍需由负责实机的任务分项验收。
