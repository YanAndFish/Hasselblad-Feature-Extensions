/* 独立离线测试模型。配置与局部判据来自同一份C/WASM；没有设备接口。 */
(function (root) {
  'use strict';
  const sign=x=>(x>0)-(x<0), clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  function interpolate(xs,ys,x) {
    if(x<=xs[0])return ys[0];if(x>=xs.at(-1))return ys.at(-1);
    let hi=1;while(xs[hi]<x)hi++;const f=(x-xs[hi-1])/(xs[hi]-xs[hi-1]);return ys[hi-1]*(1-f)+ys[hi]*f;
  }
  function random(seed) {
    let state=seed>>>0;
    const uniform=()=>{state^=state<<13;state^=state>>>17;state^=state<<5;return ((state>>>0)+1)/4294967297;};
    return ()=>Math.sqrt(-2*Math.log(uniform()))*Math.cos(2*Math.PI*uniform());
  }
  class AfTestEngine {
    static async create(data) {
      const bytes=Uint8Array.from(atob(data.wasmBase64),x=>x.charCodeAt(0));
      const {instance}=await WebAssembly.instantiate(bytes,{});return new AfTestEngine(instance.exports,data);
    }
    constructor(exports,data) {
      this.wasm=exports;this.data=data;this.wasm.config_reset();this.lastRun=null;
      const layout=new Uint32Array(exports.memory.buffer,exports.layout_ptr(),4);
      if([...layout].join(',')!=='36,32,68,36')throw new Error('计算模块布局与界面不一致');
    }
    view(){return new DataView(this.wasm.memory.buffer);}
    readConfig(active=false) {
      const view=this.view(),p=this.wasm.bank_ptr()+8+(active?36:0),words=[];
      for(let i=0;i<9;i++)words.push(view.getUint32(p+i*4,true));
      return {magic:words[0],abi:words[1],lens:words[2],revision:words[3],probe:words[4],fast:words[5],fine:words[6],
        newDirection:!!(words[7]&1),flags:words[7],checksum:words[8]};
    }
    publish(selection) {
      const allowed=new Set(this.data.catalog.options.map(x=>x.value));
      for(const stage of ['probe','fast','fine'])if(!Number.isInteger(selection[stage])||!allowed.has(selection[stage]))throw new Error('不支持的速度档位');
      const view=this.view(),p=this.wasm.config_ptr(),revision=this.readConfig().revision+1;
      const words=[0x31435441,1,75,revision,selection.probe,selection.fast,selection.fine,selection.newDirection?1:0,0];
      words.forEach((x,i)=>view.setUint32(p+4*i,x>>>0,true));view.setUint32(p+32,this.wasm.config_checksum()>>>0,true);
      const result=this.wasm.config_publish();if(result)throw new Error('配置未接受：'+result);
      return this.readConfig();
    }
    latch() {
      const generation=this.view().getUint32(this.wasm.bank_ptr()+4,true)+1;
      const result=this.wasm.config_latch(generation);if(result)throw new Error('本轮配置锁定失败：'+result);
      return {generation,config:this.readConfig(true)};
    }
    command(stage,original){return this.wasm.stage_command(stage,original);}
    assess(samples,timing) {
      const ss=samples.slice(-5),view=this.view(),p=this.wasm.samples_ptr();
      ss.forEach((s,i)=>[s.position,s.cv,s.sampleTick,s.receiveTick,s.frame,s.generation,s.flags,s.nativeCount,s.secondaryCv]
        .forEach((v,j)=>view.setUint32(p+i*36+j*4,v>>>0,true)));
      const t=this.wasm.timing_ptr();
      [timing.now,timing.processing,timing.commandDelay,timing.known?1:0].forEach((v,i)=>view.setUint32(t+4*i,v>>>0,true));
      view.setFloat32(t+16,timing.braking,true);view.setUint32(t+20,timing.inFlight?1:0,true);
      view.setFloat32(t+24,timing.velocityBound||0,true);view.setUint32(t+28,timing.commandSequence||0,true);
      this.wasm.assess(ss.length);
      const out=this.wasm.result_ptr(),result={};
      ['directionValid','predictionValid','reason','used','predictionKind'].forEach((key,i)=>result[key]=view.getUint32(out+4*i,true));
      ['directionMetric','velocity','frameTicks','ageTicks','residual','peakPosition','peakDistance','leadDistance',
        'requiredDistance','safeSpeedRatio','positionStep','predictionVelocity'].forEach((key,i)=>result[key]=view.getFloat32(out+20+4*i,true));
      return result;
    }
    // 仅浏览器运动回放使用的原厂三点判据模型；原厂完整state3/4由ARM测试独立验证。
    stockMetric(samples) {
      if(samples.length<3)return 0;const tail=samples.slice(-3);
      const d1=tail[1].cv-tail[0].cv,d2=tail[2].cv-tail[1].cv;if(!(d1>0&&d2>0||d1<0&&d2<0))return 0;
      const low=tail.reduce((a,b)=>a.cv<b.cv?a:b),high=tail.reduce((a,b)=>a.cv>b.cv?a:b);
      const base=Math.min(...samples.map(s=>s.cv));if(!base||high.position===low.position)return 0;
      return Math.fround(Math.fround(high.cv-low.cv)/Math.fround(base))*sign(high.position-low.position);
    }
    serializeConfig(active=false) {
      const c=this.readConfig(active);
      return {kind:'xcd75p-af-experiment-config',schemaVersion:1,targetLens:'Hasselblad XCD 75P',
        installable:false,revision:c.revision,newDirection:c.newDirection,
        stageSpeeds:{probe:c.probe,fast:c.fast,fine:c.fine},checksum:c.checksum,
        speedMeaning:'0为跟随原厂；其他为协议命令幅值，非RPM',
        wasmSha256:this.data.wasmSha256,configurationScope:'速度和判向模式；不把合成延迟导入相机'};
    }
    serializeRun(observation='') {
      if(!this.lastRun)throw new Error('尚无本轮记录');
      return JSON.stringify({...this.lastRun,userObservation:String(observation)},null,2)+'\n';
    }
    serializeCsv() {
      if(!this.lastRun)throw new Error('尚无本轮记录');
      const keys=['tick','frame','position','framePosition','cv','secondaryCv','velocity','command','stage','predictionKind','predictionValid','reason','effective'];
      return keys.join(',')+'\n'+this.lastRun.trace.map(row=>keys.map(k=>row[k]??'').join(',')).join('\n')+'\n';
    }
    simulate(input={}) {
      const model={scene:'board_corner',roi:'large',metric:'gradient',frameInterval:33,commandDelay:40,imageDelay:40,
        positionDelay:0,speedGain:1,pixelNoise:1,initialDirection:-1,alignment:'correlated',maxTime:3000,seed:751250,
        blurUnits:100,peak:300,braking:.2,knownTiming:true,...input};
      for(const key of ['frameInterval','commandDelay','imageDelay','positionDelay','speedGain','pixelNoise','maxTime','blurUnits','peak','braking'])
        if(!Number.isFinite(model[key]))throw new Error('模型参数不是有限数值');
      if(model.frameInterval<5||model.frameInterval>100||model.commandDelay<0||model.commandDelay>100||model.imageDelay<0||model.imageDelay>100||
         model.positionDelay<0||model.positionDelay>100||model.speedGain<.25||model.speedGain>2||![0,1,2,4].includes(model.pixelNoise)||
         ![-1,1].includes(model.initialDirection)||model.maxTime<100||model.maxTime>5000||model.braking<=0||model.blurUnits<=0)throw new Error('模型参数超出回放范围');
      const row=this.data.images.curves.find(x=>x.scene===model.scene&&x.roi===model.roi&&x.metric===model.metric);
      const other=this.data.images.curves.find(x=>x.scene===model.scene&&x.roi===model.roi&&x.metric!==model.metric);
      if(!row||!other)throw new Error('未找到对应用户图像曲线');
      const {generation,config}=this.latch(),normal=random(model.seed),factory=this.data.catalog.modelFactoryCommands;
      const stageCommands=[0,1,2].map(stage=>this.command(stage,factory[stage]));
      const trace=[],events=[],commands=[],pendingCommands=[],messages=[],cvQueue=[],positionQueue=[];
      let position=0,velocity=0,command=0,targetVelocity=0,stage=0,accepted=[],lastPairedPosition=0,frame=0,
        priorPrediction=null,status='time_limit',enhancedUses=0,enhancedAssessments=0,stockUses=0,fallbacks=0,wrongAssociations=0;
      const send=(value,t,reason)=>{
        if(value===command)return;
        if(sign(value)&&sign(command)&&sign(value)!==sign(command)){accepted=[];priorPrediction=null;}
        command=value;const packet={sequence:commands.length+1,sentAt:t,executeAt:t+model.commandDelay,value,reason,configurationRevision:config.revision};
        commands.push(packet);
        if(model.commandDelay===0){targetVelocity=value*model.speedGain/1000;packet.actualPositionAtExecution=position;}
        else pendingCommands.push(packet);
      };
      const proxyPair=(sigma)=>{
        const noise=model.pixelNoise;
        if(!noise)return [row,other].map(curve=>Math.max(1,Math.round(interpolate(this.data.images.sigmaPixels,curve.values,sigma)*this.data.images.cvScale)));
        const models=[row,other].map(curve=>curve.noiseModels.filter(x=>x.pixelNoiseStd===noise)),xs=models[0].map(x=>x.sigma);
        const rho=clamp(interpolate(xs,models[0].map(x=>x.correlation),sigma),-1,1),z1=normal(),z2=normal();
        const zs=[z1,rho*z1+Math.sqrt(Math.max(0,1-rho*rho))*z2];
        return models.map((rows,i)=>{
          const mean=interpolate(xs,rows.map(x=>x.mean),sigma),std=interpolate(xs,rows.map(x=>x.std),sigma);
          return Math.max(1,Math.round((mean+zs[i]*std)*this.data.images.cvScale));
        });
      };
      const pastPeak=()=>accepted.length>=4&&accepted.slice(-4).every((s,i,a)=>!i||s.cv<a[i-1].cv);
      const pair=(t)=>{
        while(cvQueue.length&&positionQueue.length){
          const cv=cvQueue.shift(),p=positionQueue.shift(),matched=cv.frame===p.frame;
          if(!matched)wrongAssociations++;
          const measured=(p.position-lastPairedPosition)*1000/model.frameInterval;lastPairedPosition=p.position;
          if(!command||sign(measured)!==sign(command)||Math.abs(measured)<Math.abs(command)*.03||Math.abs(measured)>Math.abs(command)*1.97)continue;
          const mapped=model.alignment==='arrival-position'?Math.round(position):p.position;
          const aligned=matched&&model.alignment!=='arrival-position';
          const s={position:mapped,cv:cv.cv,secondaryCv:cv.secondaryCv,sampleTick:cv.sampleTick,receiveTick:cv.arrive,
            frame:cv.frame,generation,flags:aligned?15:13,nativeCount:accepted.length+1};
          accepted.push(s);if(accepted.length>500){status='sample_limit';return true;}
          const bound=Math.max(Math.abs(command),...pendingCommands.map(x=>Math.abs(x.value)))*model.speedGain/1000;
          const result=this.assess(accepted,{now:t,processing:2,commandDelay:model.commandDelay,known:model.knownTiming,
            braking:model.braking,inFlight:pendingCommands.length>0,velocityBound:bound,commandSequence:commands.length});
          let metric=0,effective='original';
          if(stage===0){
            if(config.newDirection&&![2,3].includes(result.reason)){
              metric=result.directionValid?result.directionMetric:0;enhancedAssessments++;if(result.directionValid)enhancedUses++;effective='enhanced';
            }else{metric=this.stockMetric(accepted);stockUses++;if(config.newDirection)fallbacks++;}
            if(Math.abs(metric)>.2&&Math.max(...accepted.slice(-3).map(x=>x.cv))>=50){
              const desired=sign(metric);events.push({kind:'direction',tick:t,frame:cv.frame,acceptedFrames:accepted.length,
                samplePosition:s.position,actualPosition:position,desiredDirection:desired,effective,
                correctAtSample:desired===sign(model.peak-s.position),correctAtDecision:desired===sign(model.peak-position)});
              stage=1;send(desired*stageCommands[1],t,'fast-stage');priorPrediction=null;
            }
          }else if(stage===1){
            const stable=priorPrediction&&result.predictionValid&&priorPrediction.predictionKind===result.predictionKind&&
              (result.predictionKind===1||Math.abs(priorPrediction.peakPosition-result.peakPosition)<=result.positionStep);
            if(stable&&result.safeSpeedRatio<1&&sign(command)===sign(result.velocity)){
              const limited=Math.max(stageCommands[2],Math.floor(Math.abs(command)*result.safeSpeedRatio));
              if(limited<Math.abs(command)){
                events.push({kind:'slowdown',tick:t,frame:cv.frame,samplePosition:s.position,actualPosition:position,
                  basis:result.predictionKind===1?'sampling-density':'peak-fit',velocity:result.velocity,
                  velocityBound:result.predictionVelocity,leadDistance:result.leadDistance,ratio:result.safeSpeedRatio,
                  beforeSyntheticPeak:sign(command)*position<sign(command)*model.peak});
                send(sign(command)*limited,t,'adaptive-slowdown');
              }
            }
            priorPrediction=result.predictionValid?result:null;
            if(pastPeak()){
              events.push({kind:'fine-start',tick:t,frame:cv.frame,samplePosition:s.position,actualPosition:position});
              stage=2;status='native_fine_handoff';
            }
          }
          trace.push({tick:t,frame:cv.frame,position,framePosition:s.position,cv:s.cv,secondaryCv:s.secondaryCv,
            normalizedCv:s.cv/(row.originalProxyCv||1),velocity,command,stage,queueCv:cvQueue.length,queuePosition:positionQueue.length,
            predictionKind:result.predictionKind,predictionValid:!!result.predictionValid,reason:result.reason,effective});
          if(status==='native_fine_handoff')return true;
        }
        return false;
      };
      const deliver=(t)=>{
        messages.sort((a,b)=>a.arrive-b.arrive||a.frame-b.frame);
        while(messages.length&&messages[0].arrive<=t){
          const message=messages.shift(),queue=message.type==='cv'?cvQueue:positionQueue;
          queue.push(message);
          if(queue.length>5){status='queue_overflow';return true;}
          if(pair(t))return true;
        }
        return false;
      };
      send(model.initialDirection*stageCommands[0],0,'probe-stage');
      let end=0;
      for(let t=0;t<=model.maxTime;t++){
        end=t;
        if(t>0){velocity+=clamp(targetVelocity-velocity,-model.braking,model.braking);position+=velocity;}
        while(pendingCommands.length&&pendingCommands[0].executeAt<=t){
          const applied=pendingCommands.shift();targetVelocity=applied.value*model.speedGain/1000;
          applied.actualPositionAtExecution=position;
        }
        if(position<-32760||position>32760){status='position_limit';break;}
        if(deliver(t))break;
        if(t>0&&t%model.frameInterval===0){
          frame++;const sampled=Math.round(position),sigma=Math.abs(sampled-model.peak)/model.blurUnits;
          let imageArrival=t+model.imageDelay;
          if(model.alignment==='swapped'&&frame===3)imageArrival+=2*model.frameInterval;
          const [cv,secondaryCv]=proxyPair(sigma);
          messages.push({type:'cv',frame,sampleTick:t,arrive:imageArrival,cv,secondaryCv});
          messages.push({type:'position',frame,sampleTick:t,arrive:t+model.positionDelay,position:sampled});
          if(deliver(t))break;
        }
      }
      if(!events.some(x=>x.kind==='direction')&&status==='time_limit')status='direction_undecided';
      if(command!==0&&status!=='native_fine_handoff')send(0,end,'bounded-model-end');
      const snapshot=this.readConfig(true);if(snapshot.checksum!==config.checksum)throw new Error('回放期间配置被混用');
      const report={kind:'synthetic-direction-to-native-fine-handoff',hardwareRequests:0,actualCameraTest:false,fullNativeAfEmulated:false,
        fineScanSimulated:false,totalAfDurationAvailable:false,modelPausedAtNativeFineHandoff:status==='native_fine_handoff',
        sourceImageSha256:row.inputSha256,wasmSha256:this.data.wasmSha256,generation,configuration:config,stageCommands,
        model,status,endTick:end,finalPosition:position,finalVelocity:velocity,pendingCommandCount:pendingCommands.length,
        enhancedUses,enhancedAssessments,stockUses,fallbacks,wrongAssociations,events,commands,trace,
        limitations:['静态用户图像衍生高斯模糊；不是真实离焦帧序','浏览器只回放判向和快速搜索，到精扫交接点停止',
          '噪声使用同一原像素试验的主辅相关性；制动、速度映射和三类延迟均为模型','精扫由原厂流程负责；这里不模拟其持续时间或最终合焦']};
      this.lastRun=report;return report;
    }
  }
  root.AfTestEngine=AfTestEngine;
  if(typeof module!=='undefined'&&module.exports)module.exports={AfTestEngine,interpolate};
})(globalThis);
