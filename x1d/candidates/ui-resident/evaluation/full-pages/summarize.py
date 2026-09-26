"""核对 20 个独立宿主进程结果，生成中文评估及可核验输入清单。"""
from pathlib import Path
import hashlib,json,statistics
HERE=Path(__file__).resolve().parent
OUT=HERE/'build';CANDIDATE=HERE.parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(v):return {'median':statistics.median(v),'min':min(v),'max':max(v)}
def main():
    results={s:[read(OUT/'results'/f'{s}-r{i}.json') for i in range(1,6)] for s in ('factory','a8','all_pages','all_rows')}
    source=sha(HERE/'measure.py');catalog=read(OUT/'catalog.json');summary={}
    for strategy,runs in results.items():
        for d in runs:
            assert d['sourceSha256']==source
            assert d['catalogSha256']==sha(OUT/'catalog.json')
            assert d['hardwareRequests']==0 and not d['targetMeasured'] and not d['warnings']
            assert d['models']['mockActions']==0
            assert d['fixtureWrites']=={'crop_mode_opacity':1,'BACKLIGHT_brightness':1}
            # 部分特殊组件没有 objectName，所以同时检查实际 QML 元对象类型。
            assert not any(any(name.startswith(prefix) for prefix in ('SpiritLevelView_','GreyBalanceTool_','DateTime_','CardFormat_','GenericConfirm_')) for name in d['objects']['classes'])
            assert d['objects']['namedObjects'].get('GreyBalanceTool_root',0)==0
            if strategy in ('all_pages','all_rows'):
                assert len(d['models']['pages'])==23 and len(d['models']['menus'])==3
                assert sum(p['model'] for p in d['models']['pages'])==99
            if strategy=='all_rows':
                n=d['objects']['namedObjects']
                assert (n['baseItem'],n['EvaluationSection'],n['listDelegate'])==(99,27,26)
                assert sum(p['readyRowLoaders'] for p in d['objects']['pages'])==99
        summary[strategy]={field:stats([d['steadyHidden']['median'][field]/1048576 for d in runs]) for field in ('privateCommit','workingSet')}
        summary[strategy]['objects']=runs[0]['objects']['qObjects']
        summary[strategy]['namedObjects']=runs[0]['objects']['namedObjects']
        assert all(d['objects']['qObjects']==runs[0]['objects']['qObjects'] for d in runs)
    differences={s:{field:stats([(results[s][i]['steadyHidden']['median'][field]-results['a8'][i]['steadyHidden']['median'][field])/1048576 for i in range(5)]) for field in ('privateCommit','workingSet')} for s in ('factory','all_pages','all_rows')}
    frozen=CANDIDATE/'build/fixed/ui-resident-0456d37bc5ddbc57'
    release=read(frozen/'release.json')
    for name,expected in release['manifest']['resources'].items():assert sha(frozen/'overlay'/name.lstrip('/'))==expected['outputSha256']
    inputs={'measure.py':source,'prepare.py':sha(HERE/'prepare.py'),'catalog':sha(OUT/'catalog.json'),'input-manifest':sha(OUT/'input-manifest.json'),
        'a8Overlay':{p.relative_to(frozen/'overlay').as_posix():sha(p) for p in (frozen/'overlay').rglob('*.qml')},
        'preparedQml':{p.relative_to(OUT/'qml').as_posix():sha(p) for p in (OUT/'qml').rglob('*') if p.is_file()},
        'results':{p.name:sha(p) for p in (OUT/'results').glob('*-r[1-5].json')}}
    value={'runs':20,'targetMeasured':False,'hardwareRequests':0,'summaryMiB':summary,'pairedDifferenceVsA8MiB':differences,'inputs':inputs}
    (OUT/'summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    labels={'factory':'原厂按需，遍历后关闭','a8':'a8 两个通用实例，遍历后关闭','all_pages':'3 菜单＋23 普通页，默认虚拟化','all_rows':'3 菜单＋23 普通页，全部行保留'}
    table=[]
    for s,v in summary.items():
        p=v['privateCommit'];w=v['workingSet'];n=v['namedObjects']
        table.append(f"| {labels[s]} | {p['median']:.2f}（{p['min']:.2f}–{p['max']:.2f}） | {w['median']:.2f} | {v['objects']} | {n.get('baseItem',0)} / {n.get('EvaluationSection',0)} / {n.get('listDelegate',0)} |")
    page_table=[]
    allcounts={p['page']:p for p in results['all_rows'][0]['objects']['pages'] if p['kind']=='SettingsGeneric_root'}
    defaults={p['page']:p for p in results['all_pages'][0]['objects']['pages'] if p['kind']=='SettingsGeneric_root'}
    for page in catalog['pages']:
        name=page['name'];a=allcounts[name];v=defaults[name]
        expected=sum(r['editType']!=9 for r in page['rows']);assert a['functionalDelegates']==expected
        page_table.append(f"| {name} | {expected} | {v['functionalDelegates']} | {a['functionalDelegates']} | {a['sectionItems']} |")
    d=differences['all_rows']['privateCommit'];dp=differences['all_pages']['privateCommit'];ws=differences['all_rows']['workingSet']
    text=f'''# X1D 普通菜单与全部行常驻：离线内存评估

评估对象：X1D 1.25.0 固定原厂 GUI，SHA-256 `d29c62402091c3ad40f6f247c03ce55f248ca79e92531889b1670edeb014ed9b`。这是独立评估，不是新的装载策略或装机验收。此次设备请求为 0，冻结 a8、格式化修复包和其他任务模块均未修改。

在 Windows 64 位 Qt {results['all_rows'][0]['hostQt']} 宿主上，**全部 23 个普通页及全部功能行保留，相比 a8 增加约 {d['median']:.2f} MiB 私有提交内存**；5 轮配对差分为 {d['min']:.2f}–{d['max']:.2f} MiB。工作集差分中位数 {ws['median']:.2f} MiB。它证明该宿主夹具的增量数量级，不是相机 RAM 实测值或目标机上限。

若现在需要一个规划数字，可暂为普通菜单全行方案预留 **40 MiB 额外空间**，这是将本次约 16–17 MiB 宿主增量留出约两倍余量后向上取整的工程预算选择；不是统计置信区间，也不保证目标机足够。特殊工具、GPU、原生服务、拍摄与回放峰值仍须另计。

## 实测结果

每个策略启动 5 个独立进程；每个稳态点等待 400 ms 后，取间隔 100 ms 的 5 次采样中位数。表中再汇总跨进程中位数及最小–最大值。单位均为 MiB（2^20 字节）。所有测量结束时均关闭或隐藏页面，保留策略规定的对象。

| 策略 | 私有提交：中位数（范围） | 工作集中位数 | QObject 数 | 功能行 / 标题 / 菜单入口实例 |
|---|---:|---:|---:|---:|
{chr(10).join(table)}

全页面但默认虚拟化，相比 a8 的私有提交增量中位数为 {dp['median']:.2f} MiB。默认 ListView 只创建 88/99 功能行、20/27 标题、18/26 入口，因此“页面常驻”并不等于“全部行已就绪”。全行夹具仅在评估副本设置 `cacheBuffer=100000`，最终核对 99 个行 Loader 全部 Ready。它没有被写入生产 QML。

原厂/a8 的绝对内存接近，不能解释为 a8 无成本：a8 冷态已构造通用实例，原厂遍历后的分配器和编译缓存也会保留；微小差异小于跨进程波动。原厂最终 15 个 QObject；a8 为 203 个，功能行模型已清空但观察到 4 个分组标题残留。

## 范围和方法

- 使用真实原厂 QML、完整 Wedge 设置数组和原 `validCheck`/`enableCond` 筛选，提取并保留 267 个原始 PNG/SVG 资产（共 1,094,540 字节）。QtGraphicalEffects 使用真实模块；运行后端为软件、offscreen，不代表目标机 OpenGL/EGL 分配。
- 宿主通过 PyQt5 执行；所有 Hasselblad 原生 import 均已移除，原生代理完全为内存替身。QML 中的字体请求仍是原厂名称，但提取包不含目标字体，宿主可能回退字体。未复制完整 MainScreen/相机进程，仅使用其真实菜单 Loader 与 Connections 片段。
- 23 个普通设置页由三个菜单创建；30 个声明入口中去掉 4 个 demo 后为 26 个入口，包含 3 个特殊工具入口。普通页 126 条非 demo 记录中，99 条是功能行，27 条是分组标题；标题不是 ListModel 功能记录。
- 使用较宽能力夹具：手动模式、镜头能力开启、镜头版本占位值、隐藏 demo、显示 secret 项，使 99 个潜在功能行都进入模型。它不是实机当前能力快照，实际可见行可能更少；按钮存在不表示操作获准或执行。
- 原厂/a8 执行同一 23 页打开、关闭序列；全页面策略直接 populate 各独立页，然后隐藏，未经过原厂全部导航回调。没有构建一个可安装的多页路由或测导航加速。
- privateCommit 为 Windows `PrivateUsage`，workingSet 为 `WorkingSetSize`，不是 Linux RSS 的同义指标。QObject/视觉子树遍历在最后一次内存采样之后，减少 Python 包装对象污染采样；引擎、JS、缓存与替身仍在进程内存中。
- 所有 20 轮警告 0、模拟操作按钮调用 0。主脚本和汇总脚本检查危险弹窗与特殊组件实例，除 objectName 外还检查 QML 元对象类名；未执行格式化或其他工具动作。

## 预建副作用与未覆盖部分

真实 `SettingsGeneric.qml` 滑块的 `onValueChanged: proxy[name] = value` 在初始化时触发两次模拟属性写入：`crop_mode_opacity`、`BACKLIGHT_brightness` 各一次，四种策略均如此。此处是替身里的属性赋值，不能据此断言相机硬件值实际改变；但正式预建不能直接照搬本夹具，必须处理初始化回写、属性刷新、能力变化及隐藏时活动。

原厂/a8 的 About 导航调用模拟设备信息读取。直接预建策略未触发它们（记录为 0），因此还需要保留用户实际进入 About 时的正常刷新语义。

本报告未实例化白平衡工具 `GreyBalanceTool.qml`、日期时间 `DateTime.qml`、水平仪 `SpiritLevelView.qml`，也未打开格式化/确认弹窗及下拉选择弹层。白平衡工具 `Component.onCompleted` 会设置图片筛选并可能切换目录；水平仪完成构造会调用 `setSpiritLevel()`；日期页会创建自己的日期时间模型。它们不能按一个 Generic 页平均值直接补算。未含回放页、照片/JPEG 缓存、AF 模块、传感器/服务缓存或整机峰值。

因此已经完成的是 **全部普通菜单和潜在行的离线差分评估**，并非“整个 GUI 所有页面全部常驻”的精确总预算；特殊页内存、目标 Qt 5.5/32 位 ARM、GPU、原生服务增量和长期稳定性仍未测量。64 位指针减半不能直接推导 32 位总内存减半，也不能给该差分一个可信的目标机上下界。

## 与已有相机快照的关系

只读复核既有 [内存快照](../../build/session/sessions/memory-snapshot-20260912T205420595640Z/observation.json)：Linux MemTotal 511,832 KiB（499.84 MiB），MemAvailable 242,808 KiB（237.12 MiB），MemFree 181,420 KiB（177.17 MiB），GUI RSS 59,364 KiB（57.97 MiB），Swap 为 0。这是此前 a8 状态的一次历史快照，不是本轮新读取，不代表当前状态或总物理 RAM。

该快照显示当时存在百 MiB 级可用空间，但其中不能全部分配给 UI。不能把 57.97 MiB GUI RSS 乘页面数量，也不能把 Windows 的约 16 MiB 差分直接加到 Linux RSS 后宣称装机安全。40 MiB 规划预算约为该次 MemAvailable 的 17%，仍需要拍摄、回放、AF 并行峰值下的目标验证。当前没有据此追加装载或设备访问。

## 各普通页的对象核对

| 设置数组 | 潜在功能行 | 默认虚拟化实例 | 全行实例 | 全行标题实例 |
|---|---:|---:|---:|---:|
{chr(10).join(page_table)}

## 复现与证据

在仓库根目录执行（仅宿主，须已有固定输入和 `fixes/card-format-r1/build/python-qt515`）：

```powershell
python x1d/candidates/ui-resident/evaluation/full-pages/prepare.py
foreach ($round in 1..5) {{
    foreach ($strategy in @('factory','a8','all_pages','all_rows')) {{
        python x1d/candidates/ui-resident/evaluation/full-pages/measure.py $strategy "r$round"
        if ($LASTEXITCODE -ne 0) {{ throw 'measurement failed' }}
    }}
}}
python x1d/candidates/ui-resident/evaluation/full-pages/summarize.py
```

- [输入提取](prepare.py)、[实际测量](measure.py)、[交叉核对及报告生成](summarize.py)。
- [汇总与完整输入/结果 SHA-256](build/summary.json)、[原始进程结果](build/results)、[固定输入清单](build/input-manifest.json)、[全部设置目录](build/catalog.json)。
- a8 输入来自冻结 `ui-resident-0456d37bc5ddbc57/overlay` 的四个 QML，已逐个对照 release 中 outputSha256；原厂输入绑定上述 GUI 摘要。测量脚本 SHA-256：`{source}`。
'''
    (HERE/'REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps({'runs':20,'allRowsVsA8MiB':d,'allPagesVsA8MiB':dp,'warnings':0,'hardwareRequests':0},ensure_ascii=False))
if __name__=='__main__':main()
