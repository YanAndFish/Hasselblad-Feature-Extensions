import manifest from '../research/firmware-manifest.json';
import catalog from '../research/parameter-catalog.json';
import { DEFINITIONS } from './protocol';

export const EVIDENCE = Object.freeze({
  model: 'Hasselblad X2D 100C（第一代）', firmware: '4.2.0', manifest,
  connection: { authorized: true, paused: false, protocolReady: true, reason: '固定读取六项：27 固件版本、28 运行标志、25 回电等待设置、87 闪光 EV 补偿、88 电子快门启用状态、61 镜头挂载标志。先确认版本 4.2.0 与运行标志 1；不符合即停止。六项已在 2026-09-09 的验证批次中读取成功；当前值以本次读取为准。读完关闭本次句柄，默认离线。' },
  parameters: catalog.parameters.map(p => ({ ...p, displayAllowed: DEFINITIONS.some(d => d.id === p.id) })),
  schema: { method: 'GET', route: '/v1/parameters', fields: ['can_get: boolean', 'can_set: boolean', 'range: string', 'value: string'],
    note: '外层键是十进制参数 ID。name 字段受固件日志开关影响，客户端使用本地目录。JSON 没有独立的 type 或 unit 字段。' },
  session: [
    { title: '正常 USB 控制路径', state: '两端当次静态复核', detail: '官方 PC 客户端对 VID 2756 / PID 0009 使用 AppsMessage 直接封装；相机 msg2dbus 将控制端点内容转给 Phocus ReadParameter。固定路由节点不是个人凭据，不读取无线白名单。', evidence: 'Phocus PC 4.1.1：0x1805cbe06、0x1805c8050；X2D 4.2.0 msg2dbus：0x10ae18；phocus：0x83298' },
    { title: '按 ID 读取与回包', state: '当次静态复核', detail: '请求类型固定为 2，响应类型 0x82 保留序号。白名单只允许 27、28、25、87、88、61，未知类型、路由、长度、序号或值即停止后续读取。EV 由固件先除以 12，再编码 double 位模式；客户端只还原数值。', evidence: 'ReadParameter 0x90c60；ID87 getter 0x92908；ToString 0x9573c；USB 回复映射 0x3fec8–0x3fee8' },
    { title: 'USB 生命周期与范围', state: '本地更正实现', detail: '官方虚表与 FunctionFS 描述符均对应第二对 bulk 控制端点；更正实现只在这些端点读取，完成即关闭。首轮曾因误选数据 OUT 而超时，未取得参数；其报告单独保留。', evidence: 'PC 虚表 +0x68 → 0x1805bab50；相机 ep2/ep4；USB_ENDPOINT_CORRECTION.md' },
    { title: '无线 HTTP 的访问检查', state: '仍未实现', detail: 'HTTP 的 X-Phocus-Client-Id 必须匹配 active client，成功会更新心跳。其名单与正常配对尚未闭环；这些限制没有被绕过，也不作为 USB 客户端的身份来源。', evidence: '/bin/phocus：validateClientId 0xc0260；readDeviceIdFile 0xe2268' },
    { title: '会话登记的已知副作用', state: '当次静态复核', detail: 'addTetheredClient 会申请 wakelock、更新客户端列表和拍摄客户端模式。此前已有相应唤醒授权；当前受限 USB 读取不调用该登记动作。', evidence: 'addTetheredClient 0x6cdd0；0x6cf10 → wakelock；0x6d1f8 → updateTetheredCaptureClients' },
    { title: '调试记录能看到什么', state: '本地实现 / 相机接口待证', detail: '保存每个白名单 ID 的发送完成、回复完成、USB 回包字节数（含补齐）和主机耗时。尚未在已查明的正常接口中证实曝光、同步脉冲或传感器事件日志入口，不开启相机日志。', evidence: 'DEBUG_READ_BATCH.md；客户端记录不等于相机内部事件日志' }
  ],
  trigger: [
    { node: '主处理器 / 电子快门分支', symbol: 'Camx_StartExpo · 0xa43ac / 0xa43f4', status: '当次静态复核', observable: '普通同步路径可达性：部分已证实', detail: '电子快门分支将 w25 清零；此前该寄存器曾保存同步模式 3，不能当作既有布尔许可。镜头相关路径在另一处清零；单处不清除尚不是完整方案。' },
    { node: '传感器 / 感光与读出', symbol: 'DjiImgSys_SetExposure · StillStartExpose', status: '调用点当次复核', observable: '共同曝光窗口：未测量', detail: '已复核曝光设置与启动调用点；函数调用顺序不等于各行实际感光起止。IMX461 细节仍属前序记录，较慢曝光的具体适用阈值尚未证实。' },
    { node: '镜头 / 镜间快门', symbol: 'DjiLensDrv_HBMount_SetFsyncAdjust · HasDoubleFSync', status: '参数映射待验证', observable: '原厂修正与单双同步能力：当前客户端未实现读取', detail: '当前 141 个 eCamDevParam 枚举中没有这些名称，不排除其他正常接口或别名。镜头版本、产品 ID 与微调能力不能替代它们。' },
    { node: 'MCU / 同步脉冲', symbol: 'DjiLensDrv_HBMount_ConfigXsync · TIM1 / TIM3', status: '前序静态结论', observable: '延迟、模式和脉冲事件：尚未证实正常读取接口', detail: '前序记录有非负延迟及最低钳制分支；不代表新提前量范围。两次同步的物理含义尚未证明。' },
    { node: '热靴 / 普通闪光同步', symbol: 'FsyncCtrl_TriggerXsync · 0xa76b8', status: '当次静态复核', observable: '实际分路与发光时刻：未测量', detail: '直接分路先请求同步有效，再 USleep(1000)，最后撤销；此片段无反馈读取。等待不是无线提前量或发光时长；未接灯也不能假定额外调用不影响时序。' }
  ],
  region: [
    { label: '菜单语言', state: '有参数读取分支', detail: 'ID 118 → SystemProxyDbus::language_index → Cam2Phocus_Language。它不是销售地区。', evidence: '4.2.0 /bin/phocus：0x92ae8，0x12afb0' },
    { label: '无线法规地区', state: '配置路径当次复核', detail: 'ProdInfo::setWifiRegion 使用 Identity/WifiRegion 键，经制造分区可写切换和 QSettings 写入。未证实正常外部读取或修改接口，也不能据此等同销售区 JP / CN。', evidence: '4.2.0 /bin/camera-system：0xeab30 → setConfigParam 0xe8de8' },
    { label: '销售地区 JP / CN', state: '待验证', detail: '用户回忆可能通过独立配置修改。尚未找到该字段的确切存储、正常接口、消费者或签名约束。', evidence: '用户回忆；不能由菜单语言或固件版本推断' },
    { label: '制造、售后与身份数据', state: '不在显示白名单', detail: '参数目录含设备和镜头序列相关项，当前解析器在主进程丢弃它们。不读取制造/NVM/校准存储。', evidence: '不提供地区写入、身份修改或固件更新功能' }
  ],
  limitations: [
    'USB 白名单现为六项；六项已在一次完整实机批次中通过验证，当前快照仍以本次来源和值为准。没有完整拍摄客户端登记或触发功能。',
    '回电等待设置不等于充电就绪，电子快门启用状态不等于曝光进行状态，镜头挂载不等于同步能力。',
    '当前正常协议中未证实 FsyncAdjust、HasDoubleFSync、实际同步时刻和相机事件日志的读取入口。',
    '官方 4.2.0 是分析基线；当前机身版本必须由本次已接受的 ID 27 数据确认。',
    '模拟值仅用于验证解析和界面；离线导入也不证明字段来自当前相机。',
    '正常连接与唤醒已获授权；相机操作边界仍为受限读取，不含拍摄、闪光、参数写入或固件修改。',
    '显示目录中的名称不保证 can_get 为真；未知编码会隐藏，单位未经核实则保留待核实标记。'
  ]
});
