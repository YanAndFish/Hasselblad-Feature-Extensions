# 无线启动时序修复已安装

2026-09-14：用户报告永久开机显示“启动未完成”，只读诊断确认无线准备失败，后续模块 load.request 未发出。相机五项核心服务运行，原装载器记录 load-request-missing，无 boot-incomplete。

已验证：机内 brcmfmac.ko 与官方 X1D 1.25.0 输入哈希一致；静态重定位证明驱动调用 request_firmware_nowait。旧脚本在 modprobe 返回后立即恢复搜索路径，存在异步读取竞态。RAM 补丁哈希正确，但实读 marker=0xcb11，预期为0x5854。竞态与现象吻合；日志未记录当时实际打开的固件路径，因此不把回退原厂文件写成已直接观测事实。

修复使搜索路径保持到驱动就绪、一次配置、补丁标记及空闲状态全部通过，再恢复原路径。等待有上限，失败不重复装卸驱动。无线及协调脚本新增阶段记录，避免错误码重用造成误判。

离线真实 sh 替身：旧时序失败复现、修复正常、驱动不就绪、配置失败、标记不符、非空闲，共6例通过。文件事务正常、旧包不匹配、文件/清单/启用点故障回退共5例通过；启动协调6例通过。以上不等于真实冷启动验收。

用户明确要求现在安装后，已完成机内固定文件更新；61次有界请求全部关闭句柄。新包及原厂基线整体校验通过，根分区恢复只读，前后GUI/通信PID相同，5服务仍active。保留原文件备份 /opt/hbl-four-module-v1.radio-r1-backup。当前RAM和驱动未重装，失败画面不会因文件更新立即消失。

**状态：修复文件已装，下一次正常开机生效；冷启动尚未验证。** 没有自动重启、拍摄、对焦或试闪。下次用户正常关机开机后，检查 boot-failed 阶段、radio-prepare.status、boot-loader.status、settings-restore.status 和最终 boot.ready；不得盲目重放有不完整标记的装载。

证据：build/radio-repair-r1/installation.json；CodeTests/radio-async-validation.json；CodeTests/radio-repair-validation.json。最初安装报告 build/persistent-install/installation.json 保留历史身份，新安装身份以本修复报告为准。
