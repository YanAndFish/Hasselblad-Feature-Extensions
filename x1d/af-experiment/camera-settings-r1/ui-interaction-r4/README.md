# AF 页面交互修复 r4

已确认旧代码把 query 和 apply 都视为 `busy`；query 超时后同一 timer 回调立即再发 query，会持续禁用除返回外的按钮。这是确定的代码缺陷；旧实机故障是否同时涉及回复丢失或其他触控因素，尚无直接证据。原页面底部状态未取得，不阻塞本修复。

本版 query 使用 `reading`，本地编辑保持可用；apply 使用独立 `applying`，后台读取期间的保存只排队一次，读回后再次核对草稿 `expectedRevision`。保存保留会话、序号、镜头身份、校验和、配置合法性及提交内容校验。超时停止自动轮询，保留本地修改，明确要求重新读取。初次读回会合并用户已编辑字段，后台新版本不会静默改写脏草稿的基准版本。

这是 GUI-only 增量：原 AF-only 资源/hold 库、AF RAM、bus-r2 和 `90-hbl-af-only.conf` 均保留；新增 `95-hbl-af-ui-r4.conf`，只替换 GUI 使用的 AF UI 库。RCC 的 7 项资源中只有 SettingsPage 改动，其他 6 项从 f325 冻结包逐字保留，包括两个入口及原厂导航连接。

## 主任务装载入口

当前仓库根目录运行；本模块任务没有执行任何设备操作。

```powershell
python -B x1d/af-experiment/camera-settings-r1/ui-interaction-r4/main.py report
python -B x1d/af-experiment/camera-settings-r1/ui-interaction-r4/main.py stage
python -B x1d/af-experiment/camera-settings-r1/ui-interaction-r4/main.py apply --evidence <本次stage.json绝对路径>
```

`report` 离线。`stage` 只传到新建的 `/tmp/hbl-af-ui-r4`。`apply` 校验 f325 基础包及当前已释放 hold 的 AF 安装、原始 GUI drop-in 和健康状态，保存 bus PID，只停止/启动 victory-gui 并加载新 GUI。完成 gate 要求原 AF-only 库和新 AF UI 库已映射、Qt 资源加载通过、新状态文件 PID 对应当前 GUI、健康正常且 bus PID 未变化。不会操作 AF RAM，不重启 bus，不代用户点击或保存配置。

失败后脚本只尝试恢复本轮之前的 AF GUI，结果在新目录 `failure-restored` 或 `failure-restore-unknown` 及日志中。任何主机请求结果未知都停止，不重发阶段。明确需要恢复时：

```powershell
python -B x1d/af-experiment/camera-settings-r1/ui-interaction-r4/main.py restore --evidence <同一本次stage.json绝对路径>
```

恢复只撤本轮 95 配置并恢复原 AF GUI，保留旧 90、AF RAM、bus 及证据。存在其他后续 GUI drop-in 时拒绝恢复，避免覆盖其他模块；常驻 UI 应先撤自己的 99 配置，再处理 r4。不要执行 r3 整体重装或 RAM 回滚来修本页面。

## 固定产物

| 产物 | SHA-256 |
|---|---|
| `build/package/af-ui-r4.tar.gz`，57728 字节 | `0448c022ed474effc5130b3c541cf95a75c05cbf1dffea2f9ee7f5bb1c53435e` |
| `linux-build/libhbl-af-ui.so`，40920 字节 | `2ded6099f968460358b2abd0bd4c89f93ee9b6e581163f26915a00fd4a24cb0c` |
| `build/resources/af-only-ui.rcc` | `d9807bfacccd3f9634fc17b44060617992f865a800032a4c60eded8a9860cb7e` |
| `validation.json` | `f48a91561ac45f7583e764fce3cc12b9dd37ce1d4741ab4c30bf680fcdb89cbe` |

精确 95 配置字节见同名文件，SHA `04a7ab0e5a7795b1050ba3a31b21bea222f3018a4e96fc55e90f2b0b4e3d5cf9`。远程 preload 为原 `/tmp/hbl-x1d-combined/libhbl-af-only.so`，随后 `/tmp/hbl-af-ui-r4/libhbl-af-ui.so`，新增开关 `HBL_AF_UI_R4_ENABLE=1`。

新库保留 `QQmlApplicationEngine::load` 上下文 `hblAf`，并仅在开关开启时，将 Qt `QResource::registerResource(QString const&,QString const&)` 的原固定 AF RCC 路径重定向至 `/tmp/hbl-af-ui-r4/af-only-ui.rcc`；其他资源文件原样转发。没有新 `qRegisterResourceData` hook。常驻 UI 前置资源库可先注册自己的独立 RCC，并保留上述 preload 顺序与开关。QML 新状态字段为 `reading`、`applying`、`canApply`，`busy` 兼容为 `applying`；保存命令增加 `expectedRevision`。

## 匿名状态与验收边界

新 `/tmp/hbl-af-settings/ui-r4.status` 记录 `stage pid bound shown width height connected reading applying paused queries applies replies envelope config lens socket timeouts sendfail edits`，不记录配置值、报文正文或设备标识。为适配原命令回复长度，主任务可分别只读：

```sh
cut -d' ' -f1-10 /tmp/hbl-af-settings/ui-r4.status
cut -d' ' -f11-20 /tmp/hbl-af-settings/ui-r4.status
```

用户进入页面后 `shown=1`、尺寸非零；读取等待应为 `reading=1 applying=0`，编辑会增加 `edits`；`replies`、拒绝分类和超时计数可区分后续通信问题。此诊断不要求代理点击或改变配置。

132 项离屏 Qt 6.11.2 指针检查通过：两个入口、原厂父级拖动过滤、640×480/800×480/320×240 尺寸、等待读取时编辑、草稿合并与版本、保存期间禁用及返回。共享 C++ 状态/回复检查实际编译运行通过；6 项 shell 生命周期检查通过，服务/健康/包 gate 为替身。ARM 库按 Qt 5.5.1/glibc 2.22 ABI 构建，旧 loader 重定位与 stat ABI 检查通过。真实目标 Qt 5.5 GUI 运行和用户触控效果仍由主任务装载后验收。

所有执行源、包及验证结果冻结。未修改旧 r3 冻结源或包。
