# reader-r1 完整候选交接

独立 GUI 回放整包已经完成离线验证。归档为 `releases/reader-r1/session.tar.gz`，**507,617 字节、11 个目标文件**。SHA-256：

```text
c394a539b02453af4bafb7b0ccf6cd506dea465c8d93860d83bcbec86d140a36
```

本任务没有装载或操作相机，没有读取照片，没有修改旧冻结包或其他任务目录，没有 Git 写操作。用户此前让本任务停止装载的指令继续有效。实机操作由 Main 按用户当前授权安排。

## 本次变化

包内只有 GUI provider、GUI 会话守护库、状态检查器、QML 资源、脚本与固定基线清单。**不含 jpeg-adapter、configstore 或 jpeg-daemon 替换文件；只修改和重启 victory-gui。** 原厂完整拍摄/编码/写卡链不再被此候选接管。

回放取消 pending 和完成记录依赖，不额外编码或写 JPEG，不强制 Full 设置。新增 File 入口只接受 JPEG；有对应可用 JPEG 时，直接缩放解码浏览或按该 JPEG 的原尺寸放大，不另读 3FR。原目录缓存确认缺少 JPEG 时允许一次原厂回退；缓存不足、读取错误、空图、配对歧义或不支持的 JPEG 仍保守拒绝，不能宣称所有 RAW-only 场景已通过。

Error 状态可见图增加有限 JPEG 重试，最多四次、每秒最多一次，Loading/Ready 不重读；该 Qt5 事件循环尚未实机运行。Full 仍沿用单许可、取消过期请求、检查上传失败和保留下层预览的措施；真实 GPU 峰值和回收速度未测。

## 证据

**71 组离线执行或静态检查、34 组传输检查通过。** 来源、产物及证据哈希见 `releases/reader-r1/offline.json`、`validation.json` 和 `package.json`。

- ARM provider、原 Qt QImage 与 TurboJPEG：普通无 UniqueID/Exif JPEG、EOI 后有限零填充、残留记录不阻塞、先不完整后完整、大小写配对、损坏拒绝、RAW 回退边界、Full 分配/取消/上传失败/引用释放；包括实际 8176×6128 输入的缩放与原尺寸解码。Storage、GL 驱动、同步等为替身。
- 原厂 ARM Encoder、ConvertCall 完成及删除析构：四种 writeFile 返回值/缓冲存在组合均删除当前任务并继续队列；有缓冲时发出 freeBuffer。writeFile、freeBuffer 回执和下一任务是替身，不是实机写卡结果。
- 固定 ARM ABI、依赖闭包、导入符号与资源入口通过；最终 provider 中没有记录发布、Storage 写入或 JPEG 压缩入口。
- 宿主 Qt6 QML 检查及 22 项真实安装脚本模拟通过。正常装载、阶段失败、恢复和重复恢复均只重启 GUI。
- 完整归档经宿主 shell 传输、解码、解包，11 个成员逐项一致。3846 个数据块，最长命令 208 字节，限制为 231；不明确结果锁定且不重发。目标 shell、服务、D-Bus 和 GPU 未执行。

持续红灯、只有八张 3FR 和没有 JPEG 的现场根因仍未确认。原厂释放链证据不支持把“failed watcher 导致固定八槽永不释放”写成结论。详细区分见 [DIAGNOSIS.md](DIAGNOSIS.md)。原现场已重启；本包不得标记为现场故障已经修复。

## Main 的使用方式

使用 `releases/reader-r1` 整套归档、`package.json` 和 `transfer.py`；不能与旧生产适配器或旧 RCC 混搭。它要求固定 1.25.0 原厂基线及无冲突的服务状态，未验证与 AF 或其他 UI 候选共存。不要在其他任务占用期间装载，也不要为通过预检而放宽原厂文件、服务或所有权校验。

直接运行 `transfer.py` 只核对本地包。设备会话由 Main 提供，接口顺序为：

```python
report, data = transfer.verify_package()
t = transfer.Transfer(authorized_session)
t.upload()
# finish_upload() 为 False 时，只继续查结果；不重新 upload。
t.finish_upload()
t.dispatch("ui")
t.result("ui")
# ui 明确退出 0，现场保持和 GPU 检查通过后才推进。
t.dispatch("enable")
t.result("enable")
```

每阶段 pending 时只查询结果。异常、返回不明、会话中断后不得用新实例盲目重发；安装脚本有失败回退，显式恢复入口仍为 `restore`。目标目录 `/tmp/hbl-x1d-rp` 必须无旧会话冲突，传输接口不会覆盖或删除已有目录。

前置检查只校验固定系统文件、服务和会话状态；不会核对卡内照片。装载成功只代表装载步骤完成，`installed`、`targetFunctionalValidated`、`targetLatencyValidated` 和 `targetMemoryValidated` 的实际结果应由 Main 单独记录。本包内这些实机标记保持 false。

## 待实机验收

按 [功能验收说明](FunctionalTests/reader-replay/README.md) 分别核对原厂拍摄/写卡完整性、RAW-only 与 RAW+JPEG、自动及手动回放、放大和资源恢复。JPEG 尺寸由原厂现有设置决定，本包不会为了满足 Full 回放而增加生产操作。用户报告的时延和持续忙灯尚无本包实测结果。
