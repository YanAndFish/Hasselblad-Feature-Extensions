# 当前固件四模块永久装载

本轮用户确认当前五档标定版本已稳定，无须继续微调，要求永久装载，并明确排除升级、降级场景。范围为 X1D-50c 1.25.0 下正常关机再开机自动加载对焦、引闪、UI 与回放；首次显示界面即为合包版本。

引闪设置全部修改即保存：总开关、功率发送、同步发送、调节步长、频道、无线 ID、各组启用/功率/造型灯、显示组和五档绝对延迟。运行会话、曝光令牌及测试动作不保存、不重放。

“实时取景仅用于电子取景器”及当前两秒提示同样来自已装版本，随开机整包保留。用户已再次明确：以现在相机上全部功能为范围，无需再确认模块清单。

## 当前状态

2026-09-14（北京时间）永久启动文件已安装，双 systemd drop-in、包内容与根分区只读状态均已核验。相机进程没有重启，当前临时版继续运行；冷启动自动装载仍待用户正常关机开机验证。详情见 `PERSISTENT_INSTALL_RESULT.md`。

来源为用户验收的临时标定版，摘要见 `accepted-inputs.json`。设置编码完成 2337 项离线检查；完整机内装载核心通过 23079 项故障模型检查，C++ 重定位结果与三个合法堆地址独立链接结果逐字节一致。机内重定位、设置文件往返/非法值/异常长度/符号链接拒绝和 observer 转发自检全部通过。

原厂 GUI 和消息服务文件不直接覆盖。包位于相机 `/opt/hbl-four-module-v1`，两个独立 systemd drop-in 在下次启动调用 wrapper。文件事务不执行 daemon-reload、服务重启或相机重启，并把根分区恢复只读。

开机时两个服务仍为 Type=simple；GUI 的 ExecStartPost 完成后，原有 `media-data.mount` 可启动。wrapper 只等待挂载结果，不新增反向 systemd 依赖。新版 GUI 第一次启动就加载合包资源，保持加载画面；协调脚本等 UI、回放和活动保持校验通过后才发布本进程装载请求。

机内装载通过已验证的 MessageIO_UART Qt slot 串行发送诊断请求，不另开串口。原厂前检、缓存执行证明、原厂堆分配与归属头检查、AF 重定位上传与读回、AF 入口同步、暂存清理、HFS1 上传与入口同步、再次检查 AF、最后启用引闪依次执行。图形界面等待设置恢复完成后开放操作。不重放曝光令牌或测试动作。

启动状态写入相机 `/run/hbl-four-module`；设置和失败记录写入 `/media/data/hbl-four-module`。未完成装载标记阻止自动重放，未知 SGI 完成状态不自动恢复回调或重发。部分写入失败时不能宣称已回原厂；须按日志进行独立检查。

证据：`build/boot-model/validation.json`、`build/boot-data/relocation-proof.json`、`CodeTests/persistent-transaction-validation.json`、`CodeTests/boot-coordinate-validation.json`。设备自检与文件安装最终状态见 `build/persistent-install/installation.json`。离线通过不等于实机开机通过。

原厂动态闪光修正、电子 B 路与当前机械退出空闲起点保持不变。本轮不自动触发拍摄、对焦或试闪。
