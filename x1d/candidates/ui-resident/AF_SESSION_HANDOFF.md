# AF r4 与常驻 UI 共存交接

状态：离线交付完成，97 项检查通过。目标 Qt5.5 加载、实际交互和性能尚未验证，本任务相机请求为 0。设备由主任务独占。本包要求已完成固定 AF r3 RAM 安装并释放 hold，且已由 AF owner 应用固定 GUI r4 修复。

## 固定产物

归档：[ui-af-session.tar.gz](build/af-session/packages/83b87e750248014e/ui-af-session.tar.gz)，46,523 字节。

SHA-256：`83b87e750248014e83fa90c543babe6f7defe36f460ad008a364caaca304d28d`。

完整文件与依赖摘要：[package.json](build/af-session/packages/83b87e750248014e/package.json)。归档包含 14 个普通文件，13 项载荷均由 manifest 覆盖；没有携带 AF 替换库或 AF RCC。

| 内容 | SHA-256 |
| --- | --- |
| 新增 ARM32 库 `libhbl-ui-af.so` | `e4663c35c14bc3445501c3dc2c7000e3c9ca6b44ff3d2fd9142e8cd53896ae6c` |
| 四资源增量 `ui-af.rcc` | `ae7973382df6c805174f808df3d2355045cb81f4ea06a860ddd73bf8a6456b11` |
| `manifest.sha256` | `cc752f0e0389d721aa0881673c14aaf63d83bcf423fec4ef610deba8f9c8b16c` |
| 固定原 AF Linux 包 | `f325db70de366f52ae3b58b98f8e9fd3e496f353dbab64c6ca4712a49064cc6a` |
| 固定 AF owner GUI r4 包 | `0448c022ed474effc5130b3c541cf95a75c05cbf1dffea2f9ee7f5bb1c53435e` |
| r4 AF UI 库 | `2ded6099f968460358b2abd0bd4c89f93ee9b6e581163f26915a00fd4a24cb0c` |
| r4 AF RCC | `d9807bfacccd3f9634fc17b44060617992f865a800032a4c60eded8a9860cb7e` |
| 原样保留的 `95-hbl-af-ui-r4.conf` | `04a7ab0e5a7795b1050ba3a31b21bea222f3018a4e96fc55e90f2b0b4e3d5cf9` |

原厂基线绑定 X1D 1.25.0；脚本核验 11 个原厂文件、固定 AF 与 r4 包内文件以及主任务提供的已完成安装收据。已完成收据内容固定为 `b17e63af75ea9ee026a20a362b0b0cc7d4dfc5872d9a50120c45073550db114b`。不将离线固件版本推定为设备当前版本。

## 运行入口

在 Hasselblad local 根执行以下命令只做离线校验，不导入 USB 传输模块：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py
```

本次输出 `readyForRootStaging=true`、`targetValidated=false`、`hardwareRequests=0`。由主任务按当前硬件授权执行下列阶段；本任务没有执行：

```powershell
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py --stage
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py --phase preflight
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py --phase ui
py -3 -X utf8 -B x1d/candidates/ui-resident/af-session/delivery.py --phase status
```

要求固定 r4 已成功运行，不能将本包用于未修复 AF 页或原厂 GUI。远程目录是 `/tmp/hbl-ui-af`；唯一新增配置是 `/run/systemd/system/victory-gui.service.d/99-hbl-ui-af.conf`。保留原 AF 的 90 配置和 r4 的 95 配置，最终 preload 为：

```text
/tmp/hbl-ui-af/libhbl-ui-af.so:/tmp/hbl-x1d-combined/libhbl-af-only.so:/tmp/hbl-af-ui-r4/libhbl-af-ui.so
```

恢复命令为同一入口 `--phase restore`：仅移除本包原样 99 配置并回到 AF r4 GUI。不要调用原厂独立 UI 包的 restore。只停止/启动 GUI；GUI PID 退出后清理其遗留 0600 UI socket。后台 socket、bus、AF RAM 与持久配置均保留。检测到外部配置、继承文件或 bus PID 变化时停止并留证。

通信结果不明时使用 `--observe ui` 读取既有阶段结果，不重复派发。实际传输采用固定已有桥接入口，逐帧不超过 231 字节，并保存阶段锁与 sent/exit 文件；每次会话的本地记录只写本候选 `build/af-session/sessions/`。

## 验证与目标验收

| 离线证据 | 检查数 | 结果 |
| --- | ---: | --- |
| [实际 QML 与 Qt 资源](build/af-session/qml-validation.json) | 45 | 通过 |
| [实际 shell 安装/恢复替身](build/af-session/install-validation.json) | 22 | 通过 |
| [传输编码与阶段模型](build/af-session/transfer-validation.json) | 10 | 通过 |
| [最终归档与 ELF 审计](build/af-session/package-validation.json) | 20 | 通过 |

QML 检查包括实际 r4 页面、菜单 AF 分支、中央 AF 按钮、两种资源注册顺序与十个生效资源的 Qt 回读。正常主菜单/通用设置容器复用；AF 子页保持临时创建。实际按钮点击在 `reading=true` 时仍产生 `localEdit`，`applying=true` 时拒绝编辑；主机使用显式业务替身，没有真实 AF 提交、对焦或读取。

shell 检查覆盖错误 r4、未释放 hold、错误收据、陌生配置、错误 preload、正在提交、旧 PID 和异常诊断的前置拒绝；启动失败、组件失败、r4 绑定失败自动恢复；修改 AF 配置或 bus 身份时停止且不覆盖。归档检查确认 AF 库/RCC 未被本包替换、原配置原样保留、ARM32 两个加载 hook 与 AF 原链路符号完整。

主任务目标验收须观察：四增量资源先于 AF r4 RCC 注册，十个实际 `QFile` 摘要全部匹配；正常根对象创建；两个不同 AF 上下文存在且安装 hold 为 false；八个组件 Ready；当前 GUI PID 的 `ui-af-ready-resources10-components8-contexts2` 标记；r4 诊断 `bound=1`、`applying=0`；稳定 Active 或 Standby 健康状态；bus PID 与保护摘要未变。

以上机制已实现但尚未在目标执行。目标交互还应核对两处 AF 入口、按钮可点击、关闭返回、常驻页面多次进入与最新值刷新。Qt6 主机通过不能替代 Qt5.5 实际加载与运行结果，性能也尚未实测。

实现与构建命令见 [af-session/README.md](af-session/README.md)。原始 `0456d37b...` 四资源冻结包与 `a8a78411...` 原厂 GUI 独立会话包均保留不变。
