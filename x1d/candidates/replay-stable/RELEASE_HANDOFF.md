# stable-r1 完整候选交接

离线交付完成。归档为 `releases/stable-r1/session.tar.gz`，812,519 字节，包含全部 14 个目标文件。SHA-256：

```text
1df99fb712e23c10ada543b2b58ded609ad289d9c16993317cf7414b340469b0
```

本任务没有操作相机、读取照片、修改其他任务目录或执行 Git 写操作。用户已明确让本任务停止装载；硬件操作仍归主任务。本交接不自动重装旧问题包，也不将离线通过写成相机已经恢复。

## 本次实现

1. 同一份 JPEG 作为普通浏览与 Full 的图像来源。8176×6128 的输入在普通浏览时直接解码到 1022×766，像素缓冲为 3,131,408 字节；不先解码约 200 MB 再缩小。Full 保留 8176×6128。写入适配层逐字节转交原成片，不改质量或尺寸，不生成额外预览 JPEG。
2. Full 解码和 GPU 纹理共享同一个许可。上传成功后释放工厂持有的 Full CPU 像素；其他 QImage 引用和 GPU 纹理都释放后才允许下一份 Full。真实 GL 错误与纹理大小限制会拒绝上传。Qt 图层保留正确预览，切换图片或离开放大时清空旧 Full，相关 pixmap 缓存关闭。
3. 取消过期 Full 请求，在旧资源归还后有限重试。一次上传拒绝不会自动循环分配大图。异常跨上下文销毁时保守保留许可到原上下文销毁，避免把可能尚存的 GPU 资源计为空闲。
4. 先读取 JPEG。已有 v3 完成记录、新 v4 记录和没有记录的旧 JPEG 都有入口。配对限制为同目录、同卡路径、相同文件名主干；有目录缓存时使用实际 JPEG 扩展名，歧义和已记录的路径/摘要冲突拒绝。增强路径不读取 3FR 头或主体来验证身份。
5. 原厂 `File` 打开失败不能直接等同文件不存在。只有刚采集的、已结束且不超过 4096 行的原 `ContentModel` 缓存表明确包含该 RAW 而没有对应 JPEG，JPEG 探测又失败时，才单次交给原 provider。JPEG 读取成功但为空、损坏、解码失败或资源不足时，不以 RAW 掩盖失败。目录缓存不是原子存储快照；这些条件不构成物理时刻上绝对无竞态的保证。
6. 新拍摄转换开始时发布临时 pending 标记，只有成功 CloseFile 的匹配完成通知才能发布 v4 记录。pending 存在 `/tmp/x1d-replay-pending-v4`，随相机重启消失；完成记录仍使用 `/media/data/x1d-replay-v3` 以兼容旧观察器。进程、时间与计数共同区分本轮写入。原 `jpeg-failure-v1` 编码失败修正仍完整配套。
7. 两个 GUI hook 共用一次固定运行文件哈希核对。这消除了候选自身的重复核对，不能据此推导用户报告的首次回放约 6 秒已经解决。

## 证据与限制

55 组离线功能或静态检查通过，另有 34 组传输检查通过。分组与源文件/二进制绑定见 `releases/stable-r1/offline.json`。

| 验证 | 结果与边界 |
| --- | --- |
| ARM provider / 原 Qt QImage / 原 TurboJPEG | 24 次小图 Full 切换、GL 上传失败、CPU/GPU 引用释放；真实 50MP JPEG 的缩放解码及 Full 原尺寸解码通过。GL 驱动、Storage 回复、同步和部分 QObject 边界是替身。 |
| ARM 写入适配层 | Full JPEG 字节一致，额外 codec 调用和 RAW File 读取为零；无关调用仅转发一次，结构损坏拒绝。成功 watcher 发布和实际 QSaveFile 提交仍未完整联调。 |
| ARM 目录与记录 | 目录不完整、跨卡、过期、缺少 RAW 行、已有 JPEG、大小写扩展名与歧义配对等检查通过。实际 GUI 对象采集依靠固定二进制静态依据，尚未在目标 Qt 中执行。 |
| GUI 图层 | 宿主 Qt6 执行实际两图层片段，Full Ready 时保留底图，加载错误与清空 Full 后底图仍在；实际 RCC 中两个文件均解包一致。不是目标 Qt5.5/GPU 验证。 |
| 依赖 | 四个候选 ELF 的 ARM hard-float、连续重定位、依赖闭包和符号版本通过；全部输入受哈希约束。 |
| 安装兼容与传输 | 保留 74 项基线、含 `+` 的合法库名、原厂 `rw-s` 删除映射白名单；实际完整归档经宿主 shell 解码、解包后 14 个成员一致。6156 个数据块，最长命令 208 字节，限制 231 字节；不确定结果锁定且不重发。 |

尚未证明旧同名 JPEG 和 3FR 来自同一次拍摄。没有记录的旧图只采用正常同目录同名关联；在禁止读取 RAW 的条件下不能凭 JPEG 补足这个证明。当前读取还要求受支持的 JPEG 结构/色彩配置，文件大小小于 128 MiB；不支持的数据会保守拒绝。

单份 Full 的许可并非整个 GUI 的内存总上限。上传瞬间仍可能同时存在约 200 MB CPU 像素和约 200 MB GPU 纹理，以及压缩输入、原系统资源和预览缓存。GPU 的真实峰值、回收速度与驱动行为仍需实机测量。

## 原问题逐项状态

| 用户观察 | 当前状态 |
| --- | --- |
| 冷入回放约 6 秒，再进入约 1 秒多 | 用户估计值，非本任务测量；保留首次冷入分析，目标时延未测。 |
| Full 放大慢 | 已改分配、取消、上传和资源持有策略；目标时延未测。 |
| 多张 Full 后黑屏，随后仅显示 Hasselblad logo 且无响应 | 已针对资源生命周期和失败图层处理修改；根因未知。没有 OOM、崩溃栈或进程状态证据，不能诊断为 OOM，也不能宣称修复。 |
| 拍后自动回放比旧版慢 | 已去除原适配层的额外预览解码/缩放/编码；真实拍后时延未测。 |

## 主任务使用方式

使用本目录 `releases/stable-r1` 中的整套归档、`package.json` 和 `transfer.py`。不要把新 provider 与旧 RCC/session 混搭。本包是独立回放会话包；不宣称已与 AF 或其他 UI 候选组合。原有服务、挂载或其他会话所有权冲突应由主任务在其工作范围内处理，不能靠放宽此包的预检绕过。

直接执行 `transfer.py` 只做本地归档校验，没有设备发现或连接代码。已获授权的装载任务负责提供 `session.command(label, command)`，再按顺序调用：

```python
report, data = transfer.verify_package()
t = transfer.Transfer(authorized_session)
t.upload()
# finish_upload() 返回 False 表示尚在解码，只查询结果，不能重新 upload。
t.finish_upload()
t.dispatch("ui")
t.result("ui")
# ui 明确退出 0 后，才调用 enable。
t.dispatch("enable")
t.result("enable")
```

每阶段结果明确成功后才推进；阶段 pending 时只查询。异常、返回不明或会话中断后不得用新实例盲目重发。`restore` 由原接口提供，安装脚本失败时还会执行其原有回退。`/tmp/hbl-x1d-rp` 必须是本轮可用目录；接口不会删除或覆盖已有会话。

装载成功只代表服务/保持/GPU 门槛通过。还需按 [功能验收说明](FunctionalTests/replay-stability/README.md) 分别确认回放正确性、异常恢复、资源和三类时延。没有相应结果前，`targetFunctionalValidated`、`targetLatencyValidated`、`targetMemoryValidated` 保持 false。

## 离线重建

固定依赖已在本仓库缓存。使用已安装的 Python 及同一固定工具链，在本仓库运行以下脚本；它们没有设备入口：

```text
tools/build_replay_adapter.py
tools/audit_replay_adapter.py
tools/build_session.py
tools/audit_session.py
tools/audit_stable_contract.py
CodeTests/run_stable_provider.py
CodeTests/run_stable_adapter.py
CodeTests/run_stable_gate.py
CodeTests/run_stable_catalog.py
CodeTests/run_stable_records.py
CodeTests/run_stable_qml.py
CodeTests/run_session_qml.py
tools/build_stable_package.py
CodeTests/run_stable_transfer.py
```

上述路径均相对于本候选目录。构建脚本核对来源、测试二进制和证据摘要；测试旧二进制后修改源码再打包会被拒绝。最后的传输验证通过后才把离线交付标记设为 true。旧 `replay-next` 归档作为只读兼容来源保留。
