"""将既有离线结果画成可复核图表，并生成界面内的中文验证页；不重新运行相机模型。"""
import hashlib,html,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[1]
assert Path.cwd().resolve()==ROOT.resolve()
BUILD=HERE/'build/native-af-r1';OUT=HERE/'ui/evidence';OUT.mkdir(exist_ok=True)
os.environ['MPLCONFIGDIR']=str(BUILD/'mpl-config');os.environ['TEMP']=str(BUILD/'tmp');os.environ['TMP']=str(BUILD/'tmp')
sys.path.append(str(HERE/'build/user-image-tests/packages'))
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
font=Path(os.environ['WINDIR'])/'Fonts/msyh.ttc'
font_manager.fontManager.addfont(str(font))
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(font)).get_name(),
    'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,
    'savefig.facecolor':'white','axes.labelcolor':'#38463e','text.color':'#253329'})
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=read(BUILD/'user-image-inputs.json');matrix=read(BUILD/'user-image-matrix.json')
arm=read(BUILD/'tests.json');ui=read(BUILD/'ui-tests.json');s=matrix['summary'];n=s['cases']
assert matrix['imageInputsSha256']==digest(BUILD/'user-image-inputs.json')
assert matrix['payloadSha256']==arm['payload_sha256']==ui['payloadSha256']
fig,axes=plt.subplots(1,2,figsize=(11.6,4.4),layout='constrained')
colors={'gradient':'#416b56','laplacian':'#936432'}
for ax,scene,title in zip(axes,['board_corner','wire'],['板子右上角','中央电线']):
    for row in (r for r in d['curves'] if r['scene']==scene):
        label=('大框' if row['roi']=='large' else '小框')+' · '+('梯度' if row['metric']=='gradient' else 'Laplacian')
        ax.plot(d['sigmaPixels'],[v/row['values'][0] for v in row['values']],color=colors[row['metric']],
                ls='-' if row['roi']=='large' else '--',lw=1.8,label=label)
    ax.set(title=title,xlabel='附加高斯模糊 σ（原图像素）',ylabel='代理值 / 未追加模糊时的代理值',xlim=(0,24),ylim=(0,1.04))
    ax.grid(axis='y',color='#e7ebe8');ax.legend(frameon=False,fontsize=9)
fig.suptitle('两张静态原图的八条衍生曲线；σ = 0 不是实测最佳焦点',fontsize=13)
fig.savefig(OUT/'contrast-curves.png',dpi=170);plt.close(fig)
outcomes=[]
for mode in ['original','enhanced']:
    values=[r[mode]['correctAtExecutionModel'] for r in matrix['trials'] if r[mode] is not None]
    outcomes.append([sum(v is True for v in values),sum(v is False for v in values),sum(v is None for v in values),n-len(values)])
fig,(ax,bx)=plt.subplots(2,1,figsize=(10.5,6.3),height_ratios=[2,1.5],layout='constrained')
left=[0,0];labels=['原厂判向','新判向候选']
for i,(name,color) in enumerate(zip(['方向正确','方向错误','正好在合成峰位','未作决定'],['#477762','#b06f50','#d4b268','#dce2de'])):
    vals=[row[i] for row in outcomes];ax.barh(labels,vals,left=left,label=name,color=color,height=.45)
    for j,v in enumerate(vals):
        if v>=40:ax.text(left[j]+v/2,j,str(v),ha='center',va='center',color='white' if i<2 else '#253329')
    left=[a+b for a,b in zip(left,vals)]
ax.invert_yaxis();ax.set_xlim(0,n);ax.set_xlabel('组数（每种方法均为 1 536 组）')
ax.set_title('在新命令预计执行时的位置判断方向；含画面与控制延迟',loc='left',fontsize=12)
ax.legend(frameon=False,ncols=4,fontsize=9,loc='upper center',bbox_to_anchor=(.5,-.28))
counts=[s[m]['byFrame3'] for m in ['original','enhanced']]
bx.barh(labels,counts,color=['#477762','#789480'],height=.45);bx.invert_yaxis();bx.set_xlim(0,n)
for i,value in enumerate(counts):bx.text(value+20,i,f'{value} / {n}（{value/n:.1%}）',va='center')
bx.set_title('前三个输入样本内作出决定：包含正确与错误决定',loc='left',fontsize=12);bx.set_xlabel('组数')
fig.suptitle('固定速度的离线对照：错误较少，同时未决定更多',fontsize=14)
fig.savefig(OUT/'direction-outcomes.png',dpi=170);plt.close(fig)
rows=''.join(f'<tr><th>{label}</th><td>{s["original"][key]}</td><td>{s["enhanced"][key]}</td></tr>' for label,key in [
    ('作出决定','decided'),('未作决定','undecided'),('前三帧内决定（含错误）','byFrame3'),('采样位置的错误决定','wrongAtSample'),('执行时模型位置的错误决定','wrongAtExecutionModel')])
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AF 候选依据与验证范围</title>
<style>body{{font:16px/1.75 "Segoe UI","Microsoft YaHei",sans-serif;color:#26372d;background:#f2f4f0;margin:0}}main{{max-width:950px;margin:auto;padding:28px 22px 48px}}h1{{font-size:26px;font-weight:500}}h2{{font-size:20px;font-weight:500;margin-top:32px}}a{{color:#376a4d}}img{{display:block;width:100%;height:auto;margin:20px 0}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:9px 8px;text-align:left;border-bottom:1px solid #d4ded5}}th{{font-weight:500}}code{{overflow-wrap:anywhere;font-size:12px}}.note{{color:#53665a}}.scroll{{overflow-x:auto}}</style>
<main><a class="back" href="index.html">← 返回对焦测试</a><h1>AF 候选依据与验证范围</h1>
<p>当前是电脑上的独立离线测试程序。阶段速度可分别选择，新判向默认关闭；配置在每轮开始时完整锁定。尚无相机配置传输、采样入口或可安装文件，不能用它直接比较镜头的实际手感。</p>
<h2>两个层次的执行</h2><p>ARM 离线测试执行固定 X1D 1.25.0 FARM 的原厂判向、越峰和速度封包函数。关闭新判向时确实使用原厂判向 helper。浏览器运行同一份 C 配置、判向与预判核心的 WASM 构建；运动与原厂外层门限是 JavaScript 模型。模型到精扫交接点停止，精扫使用原厂流程；这里不模拟精扫，不给出精扫耗时或完整 AF 时间。</p>
<p>{arm['tests']} 项 ARM 检查、{ui['passed']} 项 UI 核心检查通过，包含 343 组速度组合、正负方向和零命令、配置冻结、错配负例及四组 ARM/WASM 逐字段一致。这个计数不等于实机通过项目数。</p>
<h2>原图衍生输入</h2><p>板角和电线来自用户已提供的两张完整取景静态图。只使用原始未画红圈的像素，提取大小框的梯度与 Laplacian 代理；没有读取相机照片。两项指标来自同一图像，噪声模型保留它们的相关性，不能当作两个独立传感器，也不等于已经还原 FPGA A/B 核。</p>
<img src="evidence/contrast-curves.png" alt="板角与电线在附加高斯模糊下的八条代理曲线">
<h2>1 536 组对照的实际结果</h2><p>8 条曲线 × 4 个速度 × 3 个帧间隔 × 4 种控制/画面延迟组合 × 2 种噪声 × 2 个起步方向。固定轨迹在作出判向后继续前进；这组测试衡量局部判据，没有执行完整闭环对焦。</p>
<div class="scroll"><table><tr><th>每种方法均为 1 536 组</th><th>原厂</th><th>新判向</th></tr>{rows}</table></div>
<p>错误决定下降，但未决定增加，前三帧决定也减少，因此尚不能判定新方案整体更好。命令执行时正好处在合成峰位的原厂 20 组、新判向 18 组单列为无方向真值，没有计为正确。</p>
<p>本次小幅调整保留主指标连续同向的要求，只允许辅助指标一次微小量化/噪声。与调整前的同一批输入逐项比较，14 组由未决定变为正确决定，前三帧决定从 716 增到 726，原有正确、错误与峰位中性分类均未变。此结果只覆盖这批合成场景。</p>
<img src="evidence/direction-outcomes.png" alt="方向结果含正确、错误、恰好在峰位、未决定，以及前三帧决定数量">
<p>768 组朝峰轨迹中有 256 次提前减速建议，其中 187 次在合成峰前。模型没有真的采用这些减速命令；其余 69 次已越峰。原厂 750 次越峰事件也只是事件统计，不能解释为合焦成功。</p>
<h2>如何比较</h2><ol><li>先保持三段速度、样本、对焦框、指标和模型条件一致，只比较新判向关闭/开启。导出各自记录。</li><li>比较阶段速度时，每次只调整一段。观察判向帧数、延迟后的实际模型位置、越峰和未决定，不能只看是否完成回放。</li><li>“导出待用配置”保存下次选择；“导出本轮记录”和 CSV 保存本次实际使用的配置与轨迹。改动选择不会重写旧记录。</li></ol>
<p>1 000、2 000、3 000、5 000、8 000、12 000 是实验命令幅值，并非 RPM、定版参数或已验证机械范围。跟随原厂的模型示例为 5 000 / 5 000 / 3 000，不是当前 75P 的读取值。</p>
<h2>相机手工测试前仍需完成</h2><p>真实主/辅 CV、镜头位置与采样时刻的同帧关联入口；新阶段命令在途时的实际速度上界、延迟和制动标定；75P 身份及当前固件核对；有效装载区域、完整生命周期与恢复验证。目前的 ARM 地址只供 Unicorn，安装就绪标志为 false。关闭新判向不关闭独立速度选择和预判。</p>
<p class="note">全部当前离线检查硬件请求 0。没有 160 行切换，没有改写无线闪光模块，没有启用自动安装。实机 AF 的效果与手感仍待后续单独验证。</p>
<p class="note">ARM SHA-256：<code>{arm['payload_sha256']}</code><br>WASM SHA-256：<code>{ui['wasmSha256']}</code></p></main><script>if(window.self!==window.top)document.querySelector('.back').hidden=true;</script></html>'''
(HERE/'ui/validation.html').write_text(page,encoding='utf-8')
inputs=['user-image-inputs.json','user-image-matrix.json','tests.json','ui-tests.json']
manifest={'hardwareRequests':0,'inputSha256':{p:digest(BUILD/p) for p in inputs},
          'generatorSha256':digest(Path(__file__)),'outcomesAtExecution':dict(zip(['original','enhanced'],outcomes)),
          'outcomeOrder':['correct','wrong','exactSyntheticPeak','undecided'],
          'outputSha256':{str(p.relative_to(HERE)):digest(p) for p in [OUT/'contrast-curves.png',OUT/'direction-outcomes.png',HERE/'ui/validation.html']}}
(BUILD/'image-report-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'figures':2,'validationPage':True,'outcomes':outcomes,'hardwareRequests':0}))
