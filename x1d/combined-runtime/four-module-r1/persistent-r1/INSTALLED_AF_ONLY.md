# 当前相机：独立对焦持久包

独立对焦自启动包已安装在 /opt/hbl-af-only-v1。两个启动入口已切换；旧四模块包及6个备份目录已移除，旧启动入口已移除。当前运行内存未重载，等待用户正常关机开机。相机根分区只读，核心服务PID保持不变。

只保留对焦装载和最小装载提示/操作保护。没有UI页面预热、回放增强、闪光增强或无线补丁准备。对焦正文与参数未改；批量上传/校验、原厂身份、内存归属及关键写入核验保留。仅AF重复只读检查合并后模型13042次通信，19273项离线检查通过；不是实测秒数，未达到一秒证明。

实际安装证据 build/af-only/installation-lf.json；旧包清理 build/af-only/old-package-removal.json；完整已安装副本 build/af-only/installed-package.tgz。首次暂存因CRLF失败，没有执行安装；随后仅修正文本换行，通过完整暂存摘要、shell语法和两份动态库机上链接检查后才执行唯一一次安装。原失败证据保留。

本轮尚无独立对焦冷启动结果。下次读取 /run/hbl-four-module/af-timing、af-ui.status、boot-loader.status、result，分别报告开机时间与主装载耗时。当前不应使用旧四模块install.sh做状态检查，因为其包已删除。
