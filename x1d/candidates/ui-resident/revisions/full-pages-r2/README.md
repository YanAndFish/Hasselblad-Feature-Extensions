# full-pages-r2：页面池超时诊断与收集器修订

状态：冻结包未改。2026-09-13 在新的独占设备窗口中完成暂存、前检、一次 UI 切换和状态复核；目标门禁通过。用户随后对本轮普通 UI 手测反馈“可以，没问题”。实机过程、用户验收范围与边界见 [安装记录](INSTALLATION_R2_20260913.md)。

## 已确认的 r1 结果

2026-09-13 的 r1 实机流程使用精确包 `f2d398f8ea39b41b8dd0354a243844b750a18868f832167501d2154cc48a259d`：暂存和原厂前检成功，候选 GUI PID 1210 最终写出 `ui-resident-pool-timeout`，安装脚本返回 64 并恢复原厂。恢复后 GUI PID 1382，System2/Power0，五项服务均 active，drop-in 不存在，候选库不在进程 maps 中。证据保留在 r1 的 `build/session/sessions/`，没有重发安装。

r1 只保存了总结果，没有保存最后一次对象树快照，因此现有证据无法判定以下哪一项未完成：MainScreen/池实例数量、某个池 Loader 状态、Loader item、页面 prepared、ListView、模型行、实际 delegate，或行 Loader。不能据此猜测为 ARM 性能问题，也不能用单纯延长超时掩盖它。

## 已排除与仍未确认

- 包、RCC 和六个有效 UI 资源摘要均通过目标端检查；失败是 `pool-timeout`，不是注册、资源摘要、组件编译、QML warning 或 Loader.Error。
- r1 前检读到 D-Bus System2/Power0。对固定 SHA-256 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b` 的 `victory-gui`，本修订从 `SystemManagerProxyUI::staticMetaObject` 直接解析出 `StateUp=2`。因此 r1 的 `System.system_state === System.StateUp` 预热条件成立。详见 [元对象证据](build/meta-enum-validation.json)。旧参考重建中的五状态枚举不适用于这个二进制。
- r1 生产收集器和宿主等价收集器都用 `Loader.childItems()` 恰有一个子项来取得页面；这使宿主检查复制了生产假设，没有独立验证 Loader 的公开结果。本修订依据固定 Qt 5.5.1 头文件中的 `Q_PROPERTY(QObject *item READ item ...)`，改用公开 `item` 属性。宿主中 `item` 与唯一视觉子项指向同一对象，但生产门禁不再依赖子项数量。这是一个实际健壮性修正，尚无证据证明它就是 r1 超时的唯一原因。
- Qt5.5 隐藏 ListView 是否在目标机上创建齐全部缓存 delegate，仍需一次带诊断的目标运行才能确认。

## r2 行为

六个 QML/JS 资源和 RCC 与 r1 逐字相同；页面业务、3 菜单、23 个普通页、全部动态模型行、每行 Loader.Ready、200 ms 连续三次及 30 秒期限均未改变。r2 只改原生收集器和诊断：

1. 通过 Loader 的公开 `item` 属性取得装载对象。
2. 在 `/tmp/hbl-ui-full-r2/ui.diag` 原子覆盖写入 schema 1 快照。对象结构变化时写一次；结构稳定时最多每两秒写一次；终态再写一次。
3. 总行记录 MainScreen、顶层池、子池、Native Loader 的 Null/Loading/Ready/Error 数、菜单/页面/prepared/ListView 数，以及模型行、delegate、行 Loader 的数量与状态。
4. 每个池只记录固定 catalog key、`menu/page/other` 和数字状态。不会记录序列号、照片、镜头版本、菜单文字、设置值或完整 warning 文本。

如果以后获得新授权，成功仍要求完整门禁；失败恢复后读取 `ui.diag` 即可指出缺失层级，禁止在没有该证据时重复修改超时值。

## 离线验证

- [诊断收集器](build/diagnostic-validation.json)：8 项；真实 Qt5.15.2 宿主树中看到 26 池、3 菜单、23 页、125 个模型/delegate，其中 99 个普通页行 Loader 全 Ready；真实制造一池错误后为 25 Ready、1 Error。
- [固定二进制元对象](build/meta-enum-validation.json)：直接解析 ELF/QMetaObject，确认完整八状态枚举和 `StateUp=2`。
- [r1 资源复用](build/reuse-validation.json)：六资源与 r1 冻结包及 194 QML、11 竞态、10 旧门禁、86 Qt5.5 标识符、5 组内存证据绑定。
- [ARM 构建](build/session/native/build.json)：ARM32，固定 Qt5.5.1 库，连续重定位；注册库 SHA-256 为 `f49feacfe8845c20c5f1d13c4a9cdf18c4996c1d7870cb41bc17122b5216152b`。这仍不是目标执行通过。
- [事务脚本](build/session/install-validation.json)：31 项，包含 pool error/timeout/永久 pending 自动恢复、待机前检拒绝；服务、PID、健康、UID 为替身。
- [传输](build/session/transfer-validation.json)：12 项；[最终归档审计](build/session/package-validation.json)：26 项，实际 RCC 读取、ARM hooks、9 成员/13 基线、231 字节帧和经典解码往返。

## 冻结包

- [包报告](build/session/packages/0669df8606b91a6b/package.json)
- [诊断包](build/session/packages/0669df8606b91a6b/ui-full-pages-diagnostic-r2.tar.gz)，62,905 字节。
- 包 SHA-256：`0669df8606b91a6bd8876b6066be9fa31259a9d21924e989669ae1d35e9a8f14`。
- RCC SHA-256：`1c794a21fe7f61a4bdab50f40b5eb02bc428fcd584e9ed2d9d8119c97223b551`。
- 独立目标目录：`/tmp/hbl-ui-full-r2`；当前会话已装载。

在仓库根运行 `python x1d/candidates/ui-resident/revisions/full-pages-r2/delivery.py` 仍只做离线绑定验证。任何后续状态读取、恢复或重装仍须由主任务取得新的独占设备窗口；不得把本次授权复用于其他模块。r1 的冻结包、报告和实机证据均未改写。
