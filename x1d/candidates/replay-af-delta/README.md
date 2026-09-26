# AF 基础上的回放增量准备

本目录仅保存独立候选及离线证据。本任务没有连接、装载或控制相机。实机仍由 AF 任务负责。

读取 provider 逐字复用冻结 `reader-r1`，原包 SHA-256 为 `c394a539b02453af4bafb7b0ccf6cd506dea465c8d93860d83bcbec86d140a36`。本次只增加独立 GUI 会话和 RCC 合成；不写 AF 参数、不重做 AF RAM 安装、不重启 msg2dbus-farm、configstore、jpeg-daemon 或 storage-daemon。

## 当前可交接程度

**未形成可装载包。** `artifacts/package-staging/draft.json` 明确为 `packageReadyForDelegatedLoad=false`。当前测试合同绑定原 AF r5：包摘要 `6bbd107079f76619c959574527f692a398732a4fce6f44850a14deff10b739c1`，清单摘要 `bd347c5f9919eaba4710fac9e62d7212bf6fb15f4bd65783a7c3f426e566ca6e`。AF 正在处理查询超时，最终增量必须根据修正后实际交付重新生成配置、输入哈希、状态检查和资源，并重新验证；不能宽松接受未知 AF 文件。

`tools/prepare_r5_contract.py` 生成的脚本和 ELF 只是离线测试材料。没有传输器、冻结归档或实机功能通过记录，不能将 staging 目录当成装载交付。

补充本地只读核对：`bus-reply-r5/INSTALLATION_RECORD_20260913.md` 记录 AF owner 已在原 delivery-r5 上叠加 bus-transport-r4 的 95 和 bus-reply-r5 的 96。新 bus 库摘要为 `843bfb971a3a27012794c4667cabcee8c6cb2d5dd12689bc5773059dcf19b228`。这不是本任务对设备的观察，实机读取闭环在该记录中仍待用户验收。

新 bus-reply-r5 的 `common.sh::gui_same()` 将 GUI PID 绑定到自身 `gui.pid`，`new_ready()` 和恢复前置条件依赖它。本回放增量将来重启 GUI 会让这份证明失效，即使 bus 及原 AF 参数没有变化。因此还须形成支持 GUI 代次变化的组合恢复合同，不能仅更新 bus 哈希或静默修改 AF 证明。当前候选会拒绝这套新增 95/96 的现场，不会错误放行。

## 增量范围

新文件位于独立 `/tmp/hbl-x1d-rpa`，仅拟增加 GUI 的 `95-x1d-replay-af.conf`。原 AF 两个 `90-hbl-af-only.conf`、原 AF 安装证明、原 hold.release 和 AF 包保持原样。预期装载时只停止并启动 GUI 一次。

AF host 保留唯一 `qRegisterResourceData` 钩子，新会话只重定向它对固定 AF RCC 文件的 `QResource::registerResource` 请求。合成资源保留原 AF 六个非 main 文本；main 增加本轮独立有期限 hold 和原 ContentModel 绑定，另外加入冻结读取端的 MediaBrowseView。动态接入顺序为本轮 session、reader provider、AF host、AF UI。

安装前要求 AF UI 未显示、未查询、未应用，并核对原 AF 及生产服务身份。失败恢复只移除内容完全匹配本轮的 GUI 增量，恢复到原 AF GUI；未知 drop-in 保留并报错。原 AF 保持释放，本轮 hold 独立释放。保护证据只含程序/配置摘要和进程身份，不读取 AF RAM 或照片。

## 验证边界

已构建固定 ARM 产物，完成 ELF 依赖审计和宿主 QML 验证。`CodeTests/run_delta_contract.py` 检查 RCC 回读、原 AF 文本、provider 一致性、导出和配置顺序。`CodeTests/run_delta_linux.py` 用实际 shell 脚本执行隔离的服务/PID/权限/socket 替身；真实 Linux systemd、Qt5 链接器、GPU、AF 界面和回放功能均未执行。

Windows 模拟器每次服务/权限查询需启动子进程，测试的宿主 600 秒上限不是相机装载时长或性能承诺。故障恢复、实际 Qt5 资源遮盖顺序、自动回放和历史回放仍需负责实机的任务分项验收。
