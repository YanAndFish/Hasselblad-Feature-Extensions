# 设置恢复等待条件修复

2026-09-14 冷启动实测：boot-recovery.status 确认原厂前检通过；native报告 modules-ready，19086次请求、2415次写入，elapsedMs=202044，无未决写入。无线和AF/闪光装载流程完成，但 settings-restore.status 为 failed，协调记录 restore-settings 失败。整套用户启动尚未完成。

原因：GUI在恢复频道/ID阶段等待FV_READY，而该字段来自policy.restored()，要求无线master启用且持有准备状态。GUI直到这一阶段完成才发master设置，形成循环等待。默认Master关闭也不应该打开无线来满足这个条件。此外新会话保留UNAVAILABLE历史错误，不能把它当成已关闭配置确认失败。

修正：只在相同会话的序号确认后，对照频道/ID、master关闭、无busy/reconfiguring/shot状态进入下一阶段。关闭选项按master/power/sync精确回显确认，允许初始化遗留UNAVAILABLE/CANCELLED；启用仍严格要求ERROR=OK及相应ready。RADIO_ERROR/TIMEOUT、错误频道或开关、不空闲状态均不被接受。不自动发试闪或曝光。

CodeTests/settings_restore.test.cpp 使用真实FormalPolicy复现默认关闭且READY=0/UNAVAILABLE，并验证新的确认谓词可完成；原厂停用状态没有radio Open动作。错误/忙碌/错配/启用未ready都拒绝。ARM构建完成，更新与回退5案例通过。安装证据位于build/settings-repair-r3/installation.json。当前版本仍需正常关机开机验收整个用户启动流程。

安装已完成：410次有界请求、句柄全部关闭；新GUI库在禁用插件初始化条件下机内加载与重定位自检通过；整包与原厂基线校验通过、根分区只读、前后GUI/通信PID一致、5服务active。只更改持久GUI库及清单，当前运行RAM未重装，未重启相机。

后续冷启动已验收：用户报告进入系统，result=four-modules-loaded，boot.ready=ready，settings-restore=ready，无boot-failed和boot-incomplete，5服务active，持久包与根只读校验通过。native装载199593ms、19086次请求、2415次写入。仅证明启动链完成，未自动进行拍摄/对焦/闪光效果测试。
