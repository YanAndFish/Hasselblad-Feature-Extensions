interface Result { ok: boolean; data?: any; code?: string; message?: string; }
declare const debugClient: {
  snapshot(): Promise<Result>; simulate(scenario: string): Promise<Result>; reset(): Promise<Result>;
  connect(): Promise<Result>; disconnect(): Promise<Result>; importParameters(): Promise<Result>; exportReport(): Promise<Result>;
  replayFirmware(): Promise<Result>; readFirmware(): Promise<Result>;
};
let snapshot: any;
let page = 'overview';
let busy = false;
let searchText = '';
let category = 'all';
let toastTimer: ReturnType<typeof setTimeout>;
const $ = (id: string) => document.getElementById(id)!;
const esc = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const titles: Record<string, [string, string, string]> = {
  overview: ['诊断总览', '只读调试工作台', '先核查参数与协议，再判断三类触发链路能看见什么。'],
  parameters: ['参数目录', '参数与能力', '显示白名单内的参数；相机支持写入也不会开放编辑功能。'],
  trigger: ['触发链路', '引闪、传感器与快门', '按环节核查可观测性。以下是证据关系，不是实测物理时序。'],
  region: ['地区信息', '地区配置研究', '区分菜单语言、无线法规与销售地区，核查 JP / CN 的真实配置来源。'],
  session: ['连接与证据', '连接状态与协议证据', '读取固定六项调试快照；数据、每项通信阶段和关闭结果分别记录。'],
  firmware: ['固件内部事件', '曝光分支与固件日志', '固定日志发射点的详细内容；解析、接入条件和实机验证分别标记。']
};
function toast(text: string) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => $('toast').hidden = true, 9000); }
function setBusy(value: boolean) { busy = value; ['simulate','import','reset','export','check-connect','disconnect','fw-replay','fw-read'].forEach(id => { const element = document.getElementById(id) as HTMLButtonElement | null; if (element) element.disabled = value || id === 'fw-read' && !snapshot?.firmware.enabled; }); $('simulate').textContent = value ? '诊断中…' : '▷ 运行模拟诊断'; }
async function operation(fn: () => Promise<Result>) {
  if (busy) return;
  setBusy(true);
  try { const result = await fn(); if (!result.ok) toast(result.message ?? '操作未完成'); else if (result.data?.evidence) { snapshot = result.data; render(); } else if (result.data?.path) toast(`已导出脱敏报告：\n${result.data.path}`); }
  catch { toast('本机诊断服务暂不可用。'); }
  finally { setBusy(false); }
}
function navigate(next: string) { if (!titles[next]) return; page = next; render(); }
function sourceTag() { return snapshot.source === 'camera-usb' ? '<span class="pill verified">实机 USB</span>' : snapshot.source === 'simulated' ? '<span class="pill mock">模拟样例</span>' : snapshot.source === 'offline-import' ? '<span class="pill neutral">离线导入</span>' : '<span class="pill neutral">未读取</span>'; }
function table(rows: any[], compact = false) {
  if (!rows.length) return `<div class="empty"><div class="empty-symbol">∅</div><h3>暂无参数快照</h3><p>可运行本地模拟诊断或导入已有参数响应。<br>实机读取可在“连接与证据”中发起，结果另按来源标注。</p></div>`;
  return `<div class="table-wrap"><table><thead><tr><th>ID / 参数</th><th>显示值</th>${compact ? '' : '<th>单位 / 编码</th><th>接口能力</th>'}<th>来源</th></tr></thead><tbody>${rows.map(r => `<tr><td><span class="subtle mono">${r.id.toString().padStart(3,'0')}</span> &nbsp; ${esc(r.label)}${compact ? '' : `<span class="param-name">${esc(r.name)}</span>`}</td><td class="value-cell">${r.value === null ? `<span class="muted">${r.valueState === 'unavailable' ? '不可读取' : '陌生编码已隐藏'}</span>` : esc(r.value)}</td>${compact ? '' : `<td class="unit-cell">${esc(r.unit)}<span class="param-name">wire: string</span></td><td><span class="pill neutral">${r.canGet ? '可读' : '不可读'}</span><span class="param-name">can_set: ${r.cameraCanSet === null ? '未查询' : r.cameraCanSet}<br>客户端始终禁止写入</span></td>`}<td>${sourceTag()}</td></tr>`).join('')}</tbody></table></div>`;
}
function events() {
  if (!snapshot.events.length) return '<div class="empty"><p>尚无诊断请求。运行模拟诊断后，会在这里保留状态码、响应大小与主机耗时。</p></div>';
  return snapshot.events.slice(0,8).map((e: any) => `<div class="event"><div class="event-time">${esc(new Date(e.time).toLocaleTimeString('zh-CN',{hour12:false}))}<br>${e.elapsedMs === undefined ? '' : `${e.elapsedMs} ms`}</div><div><div class="event-operation">${esc(e.operation)}</div><div class="event-detail">${esc(e.detail)}${e.bytes === undefined ? '' : ` · ${e.bytes} B`}</div></div><span class="event-code">${esc(e.status ?? e.outcome)}</span></div>`).join('');
}
function overview() {
  const allowed = snapshot.evidence.parameters.filter((p: any) => p.displayAllowed).length;
  return `<div class="metrics"><div class="metric"><div class="metric-label">当前显示参数</div><div class="metric-value">${snapshot.rows.length}<small>/ ${allowed}</small></div><div class="metric-note">${snapshot.rows.length ? '仅保留显示白名单' : '尚无实机或导入结果'}</div></div><div class="metric"><div class="metric-label">HTTP 循环覆盖</div><div class="metric-value">139<small>个 ID</small></div><div class="metric-note">静态覆盖 ≠ 全部可读取</div></div><div class="metric"><div class="metric-label">固件条目校验</div><div class="metric-value">8<small>/ 8</small></div><div class="metric-note">官方 4.2.0 · 校验通过</div></div><div class="metric"><div class="metric-label">实机请求记录</div><div class="metric-value">${snapshot.hardwareRequests ?? "?"}<small>次</small></div><div class="metric-note">${snapshot.lastHardware?.closed ? "本次 USB 句柄已关闭" : snapshot.lastHardware ? "读取结果见诊断记录" : "尚未发起实机读取"}</div></div></div>
  <div class="grid-two"><div class="panel"><div class="panel-head"><div><h2>设备与镜头快照</h2><div class="sub">只显示可保留字段，序列号在主进程丢弃</div></div>${sourceTag()}</div>${table(snapshot.rows.filter((r: any) => [27,28,61,74,75,120].includes(r.id)),true)}<div class="table-note">版本以本次来源标记与已接受值为准；镜头挂载标志不代表镜头快门就绪。</div></div><div class="panel"><div class="panel-head"><h2>离线证据基线</h2><span class="pill verified">已复现</span></div><div class="panel-body"><div class="keyvalue"><span>固件对象</span><span>X2D 100C / 4.2.0</span></div><div class="keyvalue"><span>CIM 完整大小</span><span>175,245,312 B</span></div><div class="keyvalue"><span>SHA-256</span><span>5ae67d16…b438e03</span></div><div class="progress-line"></div><p class="small-note">八个条目全部通过内容校验。已恢复 phocus 参数目录及读取分支。</p></div></div></div>
  <div class="grid-two"><div class="panel"><div class="panel-head"><h2>触发链路可观测性</h2><button class="research-link" data-page="trigger">查看证据 →</button></div><div class="panel-body"><div class="status-research">完整 trigger trace 尚未发现</div><div class="mini-chain"><div class="mini-node">主处理器</div><span class="chain-arrow">···</span><div class="mini-node">传感器 / 镜头</div><span class="chain-arrow">···</span><div class="mini-node">MCU / 热靴</div></div><p class="list-note">电子快门、闪光 EV 补偿与回电等待有读取分支。原厂 Fsync 修正、单双同步能力与实际发光时刻尚不能由客户端读取。</p></div></div><div class="panel"><div class="panel-head"><h2>连接准备</h2><span class="pill pending">六项固定读取</span></div><div class="panel-body"><p class="list-note">USB 请求和回包已与官方两端代码对应。先读版本与运行标志，再读回电等待设置、闪光 EV、电子快门和镜头挂载标志，读完关闭本次句柄。</p><p class="small-note">六项已完成一次实机验证；当前快照仍以本次来源和值为准。</p><button class="research-link section-gap" data-page="session">查看连接证据 →</button></div></div></div>
  <div class="panel"><div class="panel-head"><div><h2>客户端通信记录</h2><div class="sub">脱敏摘要 · 不保留请求头或原始响应</div></div><span class="pill neutral">主机耗时 ≠ 硬件时序</span></div>${events()}</div>`;
}
function parameters() {
  return `<div class="panel"><div class="panel-head"><div><h2>参数快照</h2><div class="sub">${esc(snapshot.sourceLabel)} · 已丢弃 ${snapshot.hiddenFieldCount} 个非白名单字段</div></div><div class="table-controls"><input id="parameter-search" class="search" placeholder="搜索名称、ID、能力…" value="${esc(searchText)}" aria-label="搜索参数"><select id="category" aria-label="参数分类"><option value="all">全部类别</option><option value="device">设备与状态</option><option value="lens">镜头</option><option value="trigger">引闪与快门</option><option value="region">地区</option></select></div></div><div id="parameter-results"></div><div class="table-note">${esc(snapshot.evidence.schema.note)} USB 调试批次另解码已核实的字符串、整数与 double 位模式；写入能力未查询。</div></div><div class="panel section-gap"><div class="panel-head"><h2>固件参数目录</h2><span class="pill verified">4.2.0 · 当次静态提取</span></div><div class="panel-body"><p class="list-note">此处列出当前收录的参数项。处理器循环 ID 1–139；值 168 的 kExpSimStatusCamParam 位于循环之外。目录存在并不等于 can_get 为真。</p><div id="catalog-results" class="section-gap"></div></div></div>`;
}
function filterParameters() {
  const q = searchText.toLowerCase();
  const rows = snapshot.rows.filter((r: any) => (category === 'all' || r.category === category) && `${r.id} ${r.name} ${r.label}`.toLowerCase().includes(q));
  $('parameter-results').innerHTML = table(rows);
  const items = snapshot.evidence.parameters.filter((p: any) => `${p.id} ${p.name}`.toLowerCase().includes(q));
  $('catalog-results').innerHTML = `<div class="table-wrap"><table><thead><tr><th>ID</th><th>原始枚举名</th><th>HTTP 循环</th><th>本机显示</th></tr></thead><tbody>${items.map((p: any) => `<tr><td class="mono muted">${p.id}</td><td class="mono">${esc(p.name)}</td><td class="muted">${p.httpLoopIncludesId ? '覆盖，读取能力待响应确认' : '不在循环内'}</td><td><span class="pill ${p.displayAllowed ? 'verified' : 'neutral'}">${p.displayAllowed ? '白名单' : '仅目录'}</span></td></tr>`).join('')}</tbody></table></div>`;
}
function trigger() {
  return `<div class="callout">当前没有已证实的完整触发事件接口。下列卡片描述证据覆盖，不表示曝光顺序、脉冲间隔或真实机械动作；不以网络响应时间计算微秒级时序。</div><div class="trigger-grid">${snapshot.evidence.trigger.map((t: any,i: number) => `<div class="trigger-node"><div class="trigger-index">OBSERVABILITY / ${String(i+1).padStart(2,'0')}</div><div class="evidence-item-top"><h3>${esc(t.node)}</h3><span class="pill pending">${esc(t.status)}</span></div><div class="evidence-address">${esc(t.symbol)}</div><p>${esc(t.detail)}</p><div class="trigger-observable">${esc(t.observable)}</div></div>`).join('')}</div><div class="panel section-gap"><div class="panel-head"><h2>与引闪相关的参数快照</h2>${sourceTag()}</div>${table(snapshot.rows.filter((r:any) => r.category === 'trigger'))}<div class="table-note">回电等待是设置值，不表示实时充电就绪；EV 是曝光补偿；电子快门值表示启用状态。这些快照不能确定曝光或发光时刻。</div></div><div class="panel section-gap"><div class="panel-head"><h2>客户端通信记录</h2><span class="pill neutral">不是相机事件日志</span></div>${events()}</div><div class="callout section-gap">用户观察：重置传感器并感光、关闭镜间快门、遮光读出、读完再开。这一观察尚未经过同步测量。</div>`;
}
function region() {
  return `<div class="callout">“JP 改 CN 可能只需改配置”是用户回忆，尚未核实。当前提供读取与证据说明；菜单语言、无线法规地区、销售地区和制造身份分别研究。</div><div class="evidence-stack">${snapshot.evidence.region.map((r:any) => `<article class="evidence-item"><div class="evidence-item-top"><h3>${esc(r.label)}</h3><span class="pill ${r.state === '有参数读取分支' ? 'verified' : 'pending'}">${esc(r.state)}</span></div><p>${esc(r.detail)}</p><div class="evidence-address">${esc(r.evidence)}</div></article>`).join('')}</div><div class="panel section-gap"><div class="panel-head"><h2>可核查的语言参数</h2>${sourceTag()}</div>${table(snapshot.rows.filter((r:any) => r.category === 'region'))}</div>`;
}
function sessionPage() {
  return `<div class="connection-box"><div class="badges"><span class="pill neutral">默认离线</span><span class="pill pending">USB 受限读取</span></div><h2>读取固定调试快照</h2><p>${esc(snapshot.evidence.connection.reason)}</p><div class="connection-actions"><button id="check-connect" class="button primary">读取六项调试快照</button><button id="disconnect" class="button secondary">断开 / 清理会话</button></div></div><div class="evidence-stack">${snapshot.evidence.session.map((s:any) => `<article class="evidence-item"><div class="evidence-item-top"><h3>${esc(s.title)}</h3><span class="pill ${s.state.includes('当次') ? 'verified' : 'pending'}">${esc(s.state)}</span></div><p>${esc(s.detail)}</p><div class="evidence-address">${esc(s.evidence)}</div></article>`).join('')}</div><div class="panel section-gap"><div class="panel-head"><h2>结论边界</h2><span class="pill neutral">官方固件 4.2.0</span></div><div class="panel-body">${snapshot.evidence.limitations.map((x:string)=>`<p class="list-note">• ${esc(x)}</p>`).join('')}</div></div>`;
}
function firmwarePage() {
  const f = snapshot.firmware, data = f.data, last = f.lastRead;
  const artificial = f.source === 'offline-replay';
  const label = artificial ? '人工格式回放 · 全部数值为样例' : f.source === 'adb-existing' ? '本次 ADB 固定读取' : '尚未读取内部日志';
  const validated = !artificial && f.source === 'adb-existing' && last?.ok && data?.events.length > 0;
  return `<div class="grid-two"><div class="panel"><div class="panel-head"><h2>解析已实现</h2><span class="pill verified">10 个固定发射点</span></div><div class="panel-body"><p class="list-note">来源为 X2D 4.2.0 的 librcam.so。识别电子快门时间参数、长曝光分支、镜头识别异常和 FSYNC / FlashSync 失败，并关联到日志调用地址。</p><p class="small-note">缺少某条日志不能证明分支未执行或闪光成功。这里只显示记录的输出顺序。</p></div></div><div class="panel"><div class="panel-head"><h2>实机端到端</h2><span class="pill ${validated ? 'verified' : 'pending'}">${validated ? '本次取得匹配事件' : '尚未验证'}</span></div><div class="panel-body"><p class="list-note">固件存在 ADB 服务和 logcat 缓冲区，但量产配置的合法 ADB 开启入口尚未证实。六项 USB 参数读取不能取回这些日志。</p><p class="small-note">需要相机已有合法授权的 ADB 连接、已运行的本机 ADB server，并保持当前唤醒。</p></div></div></div>
  <div class="connection-box section-gap"><h2>读取现有内部记录</h2><p>先核对 camera-service 与 librcam.so 的 SHA-256，再读取 DUSS51 标签已有日志。最多 300 条，逐项过滤后保留已核实事件；错误时停止。本工具不启用 ADB 或日志开关。</p><div class="connection-actions"><button id="fw-read" class="button primary" ${f.enabled ? '' : 'disabled'}>读取已开放的 ADB 日志</button><button id="fw-replay" class="button secondary">演示格式解码（人工）</button></div>${f.issue && f.source === 'adb-existing' ? `<p class="list-note section-gap">${esc(f.issue)}</p>` : ''}</div>
  <div class="panel section-gap"><div class="panel-head"><div><h2>固件消息详情</h2><div class="sub">${esc(label)}</div></div><span class="pill ${artificial ? 'mock' : 'neutral'}">${artificial ? '不是相机执行结果' : '不是物理时序测量'}</span></div>${data?.events.length ? `<div class="table-wrap"><table id="firmware-events"><thead><tr><th>输出序号 / 事件</th><th>已解码字段</th><th>固件发射点</th></tr></thead><tbody>${data.events.map((e:any) => `<tr><td><span class="mono muted">${e.sequence}</span> ${esc(e.label)}<span class="param-name">${esc(e.meaning)}</span></td><td>${e.fields.length ? e.fields.map((x:any) => `${esc(x.label)}：<strong>${esc(x.value)}</strong> ${esc(x.unit)}`).join('<br>') : '<span class="muted">固定分支消息</span>'}</td><td class="mono">${esc(e.function)}<span class="param-name">${esc(e.emissionVa)} · 源行 ${e.sourceLine}</span></td></tr>`).join('')}</tbody></table></div>` : `<div class="empty"><h3>${last?.ok && !artificial ? '本次没有匹配事件' : '暂无内部执行数据'}</h3><p>${last?.ok && !artificial ? '读取已经完成，当前缓冲区没有这 10 类已核实消息。' : '实机接入仍待验证。人工回放用于检查消息解码和界面。'}</p></div>`}<div class="table-note">${data ? `已过滤 ${data.ignoredLines} 行，读取输入 ${data.inputBytes} B。` : ''}不保留原始日志、任务名、PID、设备标识或照片信息。</div></div>
  ${last ? `<div class="panel section-gap"><div class="panel-head"><h2>最近一次 ADB 获取</h2><span class="pill neutral">${esc(last.error ?? last.stage)}</span></div><div class="panel-body"><div class="keyvalue"><span>本机查询 / 机内命令提交</span><span>${last.hostRequests} / ${last.remoteCommandsSubmitted}</span></div><div class="keyvalue"><span>基线哈希匹配</span><span>${last.baselineMatched ? '是' : '未匹配'}</span></div><div class="keyvalue"><span>主机连接关闭</span><span>${last.closed ? '是' : '未确认'}</span></div><p class="small-note">主机耗时 ${last.elapsedMs} ms，仅表示获取耗时。提交数不证明命令完整到达；退出状态另按获取结果记录。</p></div></div>` : ''}`;
}
function render() {
  if (!snapshot) return;
  const title = titles[page];
  $('page-name').textContent = title[0]; $('heading').textContent = title[1]; $('subtitle').textContent = title[2];
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active',(el as HTMLElement).dataset.page === page));
  $('source-title').textContent = '当前参数快照：' + snapshot.sourceLabel;
  $('hardware-count').textContent = snapshot.hardwareRequests === null ? '待确认' : String(snapshot.hardwareRequests);
  $('device-status').textContent = snapshot.lastHardware?.closed ? '本次读取已结束' : snapshot.lastHardware ? '查看诊断结果' : '默认离线';
  const researchPage = ['trigger','region','session','firmware'].includes(page);
  $('source-detail').textContent = researchPage ? '本页研究证据：官方 4.2.0 静态分析；前序记录、用户观察和待验证项逐项标记，与参数快照来源分开。' : snapshot.source === 'camera-usb' ? '本次 USB 读取结果；只显示已审查字段。无持续会话，固件静态证据另按来源标注。' : snapshot.source === 'simulated' ? '参数值仅来自本进程回环模拟器。研究资料另按卡片中的来源标注。' : snapshot.source === 'offline-import' ? '只显示已审查字段；此文件不能证明是当前相机的采集结果。研究资料另按来源标注。' : '没有实时设备数据。研究资料基于官方 4.2.0 固件，不能代表当前相机版本。';
  $('source-banner').className = 'source-banner' + (snapshot.source === 'simulated' ? ' simulated' : snapshot.source === 'offline-import' ? ' imported' : '');
  $('page-content').innerHTML = page === 'overview' ? overview() : page === 'parameters' ? parameters() : page === 'trigger' ? trigger() : page === 'region' ? region() : page === 'firmware' ? firmwarePage() : sessionPage();
  if (page === 'parameters') {
    ($('category') as HTMLSelectElement).value = category; filterParameters();
    $('parameter-search').addEventListener('input',e => { searchText = (e.target as HTMLInputElement).value; filterParameters(); });
    $('category').addEventListener('change',e => { category = (e.target as HTMLSelectElement).value; filterParameters(); });
  }
}
document.addEventListener('click',e => {
  const target = (e.target as HTMLElement).closest<HTMLElement>('[data-page]');
  if (target?.dataset.page) navigate(target.dataset.page);
  if ((e.target as HTMLElement).id === 'check-connect') void operation(() => debugClient.connect());
  if ((e.target as HTMLElement).id === 'disconnect') void operation(() => debugClient.disconnect());
  if ((e.target as HTMLElement).id === 'fw-replay') void operation(() => debugClient.replayFirmware());
  if ((e.target as HTMLElement).id === 'fw-read') void operation(() => debugClient.readFirmware());
});
$('simulate').addEventListener('click',()=>void operation(()=>debugClient.simulate(($('scenario') as HTMLSelectElement).value)));
$('import').addEventListener('click',()=>void operation(()=>debugClient.importParameters()));
$('reset').addEventListener('click',()=>void operation(()=>debugClient.reset()));
$('export').addEventListener('click',()=>void operation(()=>debugClient.exportReport()));
$('connect').addEventListener('click',()=>navigate('session'));
void operation(()=>debugClient.snapshot());
