# delivery-r5 实机装载记录

本记录依据主任务执行后保存的本地证据进行只读核对。本任务没有访问设备；不表示对焦效果或真实设置查询、保存已经验收。

## 已核对的安装事实

- 安装包 SHA-256：`6bbd107079f76619c959574527f692a398732a4fce6f44850a14deff10b739c1`，与冻结包一致。
- stage：`staged=true`，685 次 Linux 请求，FARM 请求 0，`allHandlesClosed=true`，`failed=false`。
- install：`completed=true`、`afInstalled=true`、`holdReleased=true`；preflight、ui、bus、release 四个阶段均观察到退出码 0。
- install 通信：28 次 Linux 请求、23753 次 AF 请求、5075 次 AF 写入；Linux 和 AF 句柄均已关闭，`failed=false`。
- 最终记录状态：`installed_settings_until_restart`；不表示重启后保留。
- 恢复事件日志共 31799 条，逐行 JSON 均可解析，末行完整，各事件的 previous 字段连续指向上一条 SHA-256。重建状态为 `installed_settings_until_restart`、`allHandlesClosed=true`、`inFlight=null`。安装器另记录了 31799 条事件的完整审计与 `incompleteTail=false`。
- `flashInstalled`、`replayInstalled`、`residentUiInstalled` 均为 false；拍摄、对焦、闪光动作计数均为 0。主任务报告没有自动执行 query/apply。

## 冻结状态与验收边界

只读复核 `validation.json` 绑定的 37 个文件，全部哈希匹配。源码、安装包和原离线验证报告未修改；本文件是独立安装记录，不改写原验证报告的验证范围。

`validation.json` SHA-256：`f6e95e55a2a201042f38c5ec462bb64b9dd1a5463a7993b66e1cc3ca6939d2b4`。

真实设置查询及保存往返仍待用户验收，不能把安装成功写成 query/save 成功。镜头适配补充尚未实施。ROI 只读核查结论不因本次装载记录而扩大。

## 证据

路径均相对此目录。

| 文件 | SHA-256 |
| --- | --- |
| [stage.json](build/sessions/af-only-stage-20260912T190629982500Z/stage.json) | `e77b97ebd457c006458a1f2e077c2308ae9afc165cd90904bac08617d456f734` |
| [installation.json](build/sessions/af-only-install-20260912T190755288312Z/installation.json) | `a254b19b76c791ca1a4b35e0123c1f4020541af1fc723084c97710c09eb32b24` |
| [恢复日志入口](recovery/af-only-first-install-20260912T190952805799Z.json) | `99e03536e84a431c2ed1bc8fb1017420e3f665c4f84dd210bb60da7296b198c4` |
| [恢复事件日志](recovery/af-only-first-install-20260912T190952805799Z.events.jsonl) | `6723d7148697c51f2d4e5a3c6b95b3892598cb424d1c3f00b44480e74288a8ea` |
