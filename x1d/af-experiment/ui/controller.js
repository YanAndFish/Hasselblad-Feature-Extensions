(async function(){
  'use strict';
  const $=id=>document.getElementById(id),format=n=>Number(n).toLocaleString('en-US').replaceAll(',',' ');
  const errors=$('error');let engine,lastRun;
  function fail(e){errors.textContent=e.message||String(e);errors.classList.remove('hidden');}
  function selected(){return {probe:Number($('probe-speed').value),fast:Number($('fast-speed').value),fine:Number($('fine-speed').value),newDirection:$('new-direction').checked};}
  function configStatus(){
    const next=engine.readConfig(),active=engine.readConfig(true);
    $('direction-choice').textContent=next.newDirection?'开启 · 新判向候选':'关闭 · 使用原厂判向';
    $('config-status').textContent=lastRun&&next.revision===active.revision?`本轮已锁定配置 v${active.revision}`:
      `配置 v${next.revision} 待下一轮生效${lastRun?` · 当前回放仍用 v${active.revision}`:''}`;
  }
  function download(name,text,type='application/json'){
    const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function plot(report){
    const root=$('plot-root'),width=Math.max(250,Math.floor(root.clientWidth)),height=286,left=58,right=18,top=32,bottom=47;
    const points=report.trace.filter(x=>Number.isFinite(x.normalizedCv)),maxX=Math.max(1,report.endTick),maxY=Math.max(1,...points.map(x=>x.normalizedCv))*1.07;
    const x=t=>left+(width-left-right)*t/maxX,y=v=>height-bottom-(height-top-bottom)*v/maxY;
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('class','plot');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label','合成模型中的代理清晰度随时间变化，标出初次判向、首次减速和精扫入口');
    const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);return e;};
    add('path',{class:'axis',d:`M${left},${top}V${height-bottom}H${width-right}`});
    for(let i=0;i<=4;i++){const v=maxY*i/4,py=y(v);add('path',{class:'axis',d:`M${left-4},${py}H${left}`});add('text',{x:left-9,y:py+4,'text-anchor':'end'},v.toFixed(1));}
    const ticks=width<420?3:4;for(let i=0;i<=ticks;i++){const t=maxX*i/ticks;add('text',{x:x(t),y:height-bottom+22,'text-anchor':i===ticks?'end':i===0?'start':'middle'},Math.round(t));}
    add('text',{x:left,y:17},'相对代理值');add('text',{x:width-right,y:height-7,'text-anchor':'end'},'模型时间（ms）');
    if(points.length)add('path',{class:'cvline',d:points.map((p,i)=>`${i?'L':'M'}${x(p.tick).toFixed(2)},${y(p.normalizedCv).toFixed(2)}`).join('')});
    const labels={'direction':'判向','slowdown':'减速','fine-start':'精扫'};let labelIndex=0;
    for(const kind of Object.keys(labels)){
      const event=report.events.find(e=>e.kind===kind);if(!event)continue;const px=x(event.tick);
      add('path',{class:'phase-mark',d:`M${px},${top}V${height-bottom}`});
      add('text',{x:Math.min(width-right-7,Math.max(left+8,px+6)),y:top+17+18*labelIndex++,'text-anchor':px>width-75?'end':'start'},labels[kind]);
      const nearest=points.reduce((best,p)=>!best||Math.abs(p.tick-event.tick)<Math.abs(best.tick-event.tick)?p:best,null);
      if(nearest)add('circle',{class:'phase-dot',cx:px,cy:y(nearest.normalizedCv),r:3.3});
    }
    root.replaceChildren(svg);
  }
  function render(report){
    const statuses={native_fine_handoff:'已到精扫交接点 · 模型停止',direction_undecided:'方向证据不足',time_limit:'达到模型时间上限',queue_overflow:'五槽队列已溢出',position_limit:'达到模型位置边界',sample_limit:'达到样本上限'};
    $('run-state').textContent=statuses[report.status]||report.status;
    $('run-mode').textContent=`配置 v${report.configuration.revision} · ${report.configuration.newDirection?'新判向':'原厂判向'}\n模型回放`;
    ['probe','fast','fine'].forEach((s,i)=>$( 'active-'+s).textContent=format(report.stageCommands[i]));
    const direction=report.events.find(x=>x.kind==='direction'),slow=report.events.find(x=>x.kind==='slowdown'),fine=report.events.find(x=>x.kind==='fine-start');
    $('direction-event').textContent=direction?`第 ${direction.frame} 帧 · ${direction.tick} ms · ${direction.correctAtDecision?'朝向':'背离'}当时的合成峰位`:'本轮未确认方向';
    $('slowdown-event').textContent=slow?`${slow.tick} ms · ${slow.basis==='sampling-density'?'限制帧间变化':'峰位预判'} · ${slow.beforeSyntheticPeak?'峰前':'已经越峰'}`:'本轮未触发提前减速';
    $('fine-event').textContent=fine?`${fine.tick} ms · 交回原厂流程，精扫耗时未模拟`:'本轮未到精扫交接点';
    $('timing-event').textContent=`错配 ${report.wrongAssociations} 组 · 新判向采用 ${report.enhancedUses} 次 · 回退原厂 ${report.fallbacks} 次`;
    plot(report);configStatus();$('export-record').disabled=false;$('export-csv').disabled=false;
  }
  function model(){return {scene:$('scene').value,roi:$('roi').value,metric:$('metric').value,initialDirection:Number($('initial-direction').value),
    frameInterval:Number($('frame-interval').value),commandDelay:Number($('command-delay').value),imageDelay:Number($('image-delay').value),
    speedGain:Number($('speed-gain').value)/100,pixelNoise:Number($('pixel-noise').value),alignment:$('alignment').value};}
  try{
    engine=await AfTestEngine.create(AF_TEST_DATA);
    for(const id of ['probe-speed','fast-speed','fine-speed']){
      $(id).replaceChildren(...AF_TEST_DATA.catalog.options.map(item=>{const option=document.createElement('option');option.value=item.value;option.textContent=item.label;return option;}));
      $(id).addEventListener('change',()=>{try{engine.publish(selected());configStatus();}catch(e){fail(e);}});
    }
    $('new-direction').addEventListener('change',()=>{try{engine.publish(selected());configStatus();}catch(e){fail(e);}});
    for(const [control,label,suffix]of [['frame-interval','frame-label',' ms'],['command-delay','command-label',' ms'],['image-delay','image-label',' ms'],['speed-gain','gain-label','%']])
      $(control).addEventListener('input',()=>$(label).textContent=$(control).value+suffix);
    $('run-model').addEventListener('click',()=>{try{errors.classList.add('hidden');lastRun=engine.simulate(model());render(lastRun);}catch(e){fail(e);}});
    $('export-config').addEventListener('click',()=>{const c=engine.serializeConfig();download(`XCD75P-AF-config-v${c.revision}.json`,JSON.stringify(c,null,2)+'\n');});
    $('export-record').addEventListener('click',()=>{if(lastRun)download(`XCD75P-AF-model-v${lastRun.configuration.revision}.json`,engine.serializeRun($('manual-note').value));});
    $('export-csv').addEventListener('click',()=>{if(lastRun)download(`XCD75P-AF-trace-v${lastRun.configuration.revision}.csv`,engine.serializeCsv(),'text/csv');});
    $('validation-link').addEventListener('click',event=>{
      event.preventDefault();if(!$('validation-frame').getAttribute('src'))$('validation-frame').src='validation.html';
      $('validation-dialog').showModal();
    });
    $('close-validation').addEventListener('click',()=>$('validation-dialog').close());
    $('run-model').disabled=false;$('export-config').disabled=false;$('build-id').textContent='计算模块 '+AF_TEST_DATA.wasmSha256.slice(0,12);
    new ResizeObserver(()=>{if(lastRun)plot(lastRun);}).observe($('plot-root'));configStatus();
  }catch(e){fail(e);$('run-state').textContent='计算模块未就绪';}
})();
