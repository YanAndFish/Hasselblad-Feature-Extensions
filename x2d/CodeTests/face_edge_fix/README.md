# Left/Right Eye Preference Policy

`EyePreferencePolicy.js` contains original preference, loss-delay, reappearance switching and fallback logic. Inputs are normalized regions and validity states supplied by a caller; it neither detects faces nor controls a lens.

No firmware binding, manufacturer enum, device controller or installer is provided. Syntax and dependency checks are complete; actual detection and AF are not accepted in this public project. Source/licensing are in the file review records. See [index](../../../README.md).

---

## 中文

当前只保留项目自写的 `EyePreferencePolicy.js`：左右眼偏好、丢失延迟、重新出现时的切换和回退判定。输入为调用方提供的归一化区域与有效性状态，不识别人脸，也不操作镜头。

没有提供固件接口绑定、厂商枚举、设备控制器或安装工具。该文件的语法与依赖扫描已完成，真实检测和 AF 行为未在公开项目验收。许可和来源见仓库根目录逐文件审核记录。

当前组件与机型关系见 [公开索引](../../../README.md)。
