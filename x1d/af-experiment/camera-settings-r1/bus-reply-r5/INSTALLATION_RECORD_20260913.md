# r5 回包线程修复安装记录

北京时间 2026-09-13 03:51，由获授权独占硬件的 AF 任务直接安装。新增本记录，不修改冻结 validation 或旧 r4/delivery-r5 包。

- 归档：53cf5737e57f1d981bff3fc8571d6d4fdccd2dacb5a0c1a7db0c6d45011d5792，18322 字节。
- manifest：5601d09674d78d6f4e8fc1caf2c3f54f84c0c72581746f508108bdcfdc6e9d90。
- validation：df01384809309baaa2fdec4030cd8cc89f108b76c833487eb784ca10da997ca4。
- ARM lib：843bfb971a3a27012794c4667cabcee8c6cb2d5dd12689bc5773059dcf19b228。
- stage：build/sessions/af-bus-r5-stage-20260912T195117420480Z/stage.json，155 个 Linux 请求，FARM 请求零，全部句柄关闭。
- apply：build/sessions/af-bus-r5-apply-20260912T195131689969Z/result.json，8 个 Linux 请求，phase=0 / af-bus-r5-ready，全部句柄关闭。
- 基线：build/sessions/af-bus-r5-observe-20260912T195145062338Z/observation.json 与 0000.json，9 个固定只读请求，全部句柄关闭。

安装后 GUI 与 msg2dbus-farm 均 active；GUI PID 1368 保持原值。新桥接 ready，query=apply=farm=expired=0；private=returned=rx784queued=eventhandled=eventmissing=eventfull=0。UI 保留此前 16 次读取/超时、13 次编辑状态，尚未执行新修复后的读取。

设备仅新增 /tmp/hbl-af-bus-r5 与 96-hbl-af-bus-r5.conf 增量。95 的 r4 包和原 90 层保留；没有 GUI 重启、AF RAM 写入或自动 query/apply。实机闭环仍待用户手动读取一次后核对。
