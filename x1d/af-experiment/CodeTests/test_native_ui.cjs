/* 无浏览器/设备接口：验证共享 WASM ABI、配置冻结、模型时序和结果导出。 */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const base=path.resolve(__dirname,'..'),build=path.join(base,'build/native-af-r1');
assert.equal(process.cwd(),path.resolve(base,'../..'));
const read=p=>fs.readFileSync(path.join(base,p)),hash=b=>crypto.createHash('sha256').update(b).digest('hex');
vm.runInThisContext(read('ui/model-bundle.js').toString());
const data=globalThis.AF_TEST_DATA,{AfTestEngine}=require('../ui/engine.js');
const ref=JSON.parse(read('build/native-af-r1/arm-ui-reference.json')),manifest=JSON.parse(read('build/native-af-r1/offline-manifest.json'));
const resultMap={direction_valid:'directionValid',prediction_valid:'predictionValid',reason:'reason',used:'used',prediction_kind:'predictionKind',direction_metric:'directionMetric',velocity_per_tick:'velocity',frame_ticks:'frameTicks',age_ticks:'ageTicks',residual:'residual',peak_position:'peakPosition',peak_distance:'peakDistance',lead_distance:'leadDistance',required_distance:'requiredDistance',safe_speed_ratio:'safeSpeedRatio',position_step:'positionStep',prediction_velocity_per_tick:'predictionVelocity'};
const checks=[];
async function test(name,fn){await fn();checks.push({name,passed:true});console.log('PASS',name);}
async function main(){
  await test('构建与 ARM 参考来源一致',()=>{
    assert.equal(ref.payloadSha256,manifest.payload_sha256);
    assert.equal(hash(read('build/native-af-r1/offline.bin')),ref.payloadSha256);
    assert.equal(hash(Buffer.from(data.wasmBase64,'base64')),data.wasmSha256);
    for(const [p,h]of Object.entries(ref.sourceSha256))assert.equal(hash(read(p)),h,p);
    for(const [p,h]of Object.entries(data.sourceSha256))assert.equal(hash(read(p)),h,p);
    for(const p of ['native_af.c','native_af.h','native_config.c','native_config.h'])assert.equal(data.sourceSha256[p],ref.sourceSha256[p],p);
  });
  await test('ARM 与 WASM 四种输入逐字段一致',async()=>{
    const e=await AfTestEngine.create(data);
    for(const row of ref.cases){
      const ss=row.samples.map(s=>({position:s.position,cv:s.cv,sampleTick:s.sample_tick,receiveTick:s.receive_tick,frame:s.frame_id,generation:s.generation,flags:s.flags,nativeCount:s.native_count,secondaryCv:s.secondary_cv}));
      const t=row.timing,r=e.assess(ss,{now:t.now,processing:t.processing_ticks,commandDelay:t.command_ticks,known:!!t.calibrated,braking:t.braking_per_tick2,inFlight:!!t.command_in_flight,velocityBound:t.commanded_velocity_bound,commandSequence:t.command_sequence});
      for(const [k,v]of Object.entries(row.result))assert.equal(r[resultMap[k]],v,row.name+':'+k);
    }
  });
  await test('默认关闭新判向且三阶段跟随原厂',async()=>{
    const e=await AfTestEngine.create(data),c=e.readConfig();assert.equal(c.newDirection,false);
    assert.deepEqual([c.probe,c.fast,c.fine],[0,0,0]);
  });
  await test('343 组档位与正负命令保持独立',async()=>{
    const e=await AfTestEngine.create(data);
    for(const probe of data.catalog.options)for(const fast of data.catalog.options)for(const fine of data.catalog.options){
      const values=[probe.value,fast.value,fine.value];e.publish({probe:values[0],fast:values[1],fine:values[2],newDirection:false});e.latch();
      for(let stage=0;stage<3;stage++){assert.equal(e.command(stage,4321),values[stage]||4321);assert.equal(e.command(stage,-4321),-(values[stage]||4321));assert.equal(e.command(stage,0),0);}
    }
  });
  await test('同一轮保持旧配置且待用和本轮导出分开',async()=>{
    const e=await AfTestEngine.create(data);e.publish({probe:1000,fast:8000,fine:2000,newDirection:false});const run=e.latch();
    e.publish({probe:3000,fast:12000,fine:5000,newDirection:true});
    assert.equal(e.command(1,5000),8000);assert.equal(e.readConfig(true).newDirection,false);
    e.wasm.config_latch(run.generation);assert.equal(e.command(1,5000),8000);
    assert.equal(e.serializeConfig(true).newDirection,false);assert.equal(e.serializeConfig().newDirection,true);
    assert.equal(e.serializeConfig().installable,false);e.latch();assert.equal(e.command(1,5000),12000);
  });
  await test('无效档位拒绝且不改变待用配置',async()=>{
    const e=await AfTestEngine.create(data),c=e.readConfig();
    for(const value of [NaN,1001,-1000,65535,1.1])assert.throws(()=>e.publish({probe:value,fast:0,fine:0,newDirection:false}));
    assert.deepEqual(e.readConfig(),c);
  });
  await test('关闭新判向仍实际采用已选阶段速度',async()=>{
    const e=await AfTestEngine.create(data);e.publish({probe:1000,fast:8000,fine:1000,newDirection:false});const r=e.simulate({pixelNoise:0});
    assert.equal(r.enhancedUses,0);assert.ok(r.stockUses>0);assert.equal(r.events.find(x=>x.kind==='direction').effective,'original');
    assert.deepEqual(r.stageCommands,[1000,8000,1000]);assert.equal(r.commands[0].value,-1000);
    assert.ok(r.commands.some(x=>x.reason==='fast-stage'&&Math.abs(x.value)===8000));
    assert.equal(r.status,'native_fine_handoff');assert.ok(r.events.some(x=>x.kind==='fine-start'));
    assert.equal(r.commands.some(x=>x.reason==='fine-stage'),false);assert.equal(r.fineScanSimulated,false);
    assert.ok(r.commands.every(x=>x.configurationRevision===r.configuration.revision));
  });
  await test('运行后改配置不改写已有结果',async()=>{
    const e=await AfTestEngine.create(data),r=e.simulate({pixelNoise:0}),serialized=JSON.stringify(r);
    e.publish({probe:1000,fast:8000,fine:1000,newDirection:true});assert.equal(JSON.stringify(e.lastRun),serialized);
    assert.equal(r.configuration.newDirection,false);assert.equal(e.serializeConfig().newDirection,true);
    const exported=JSON.parse(e.serializeRun('手感待实机验证'));
    assert.equal(exported.configuration.newDirection,false);assert.deepEqual(exported.stageCommands,r.stageCommands);
    assert.equal(exported.userObservation,'手感待实机验证');assert.deepEqual(exported.trace,r.trace);
    const csv=e.serializeCsv().trim().split('\n');assert.equal(csv.length,r.trace.length+1);
    assert.equal(Number(csv[1].split(',')[0]),r.trace[0].tick);
  });
  await test('命令延迟零时立即生效且非零时记录执行位置',async()=>{
    for(const delay of [0,40]){
      const e=await AfTestEngine.create(data),r=e.simulate({pixelNoise:0,commandDelay:delay,imageDelay:0});
      assert.equal(r.commands[0].executeAt,delay);assert.equal(r.commands[0].actualPositionAtExecution,0);
      assert.ok(r.commands.filter(c=>c.actualPositionAtExecution!==undefined).every(c=>c.executeAt-c.sentAt===delay));
      assert.equal(r.status,'native_fine_handoff');assert.equal(r.fineScanSimulated,false);
      assert.equal(r.endTick,r.events.find(x=>x.kind==='fine-start').tick);
      assert.equal(r.totalAfDurationAvailable,false);assert.equal(r.modelPausedAtNativeFineHandoff,true);
      assert.equal(r.commands.some(x=>['fine-stage','model-end'].includes(x.reason)),false);
    }
  });
  await test('错配负例阻止增强预判并真实记录回退',async()=>{
    for(const alignment of ['arrival-position','swapped']){
      const e=await AfTestEngine.create(data);e.publish({probe:1000,fast:8000,fine:1000,newDirection:true});
      const r=e.simulate({pixelNoise:0,alignment});assert.ok(r.fallbacks>0);
      if(alignment==='arrival-position'){assert.equal(r.enhancedUses,0);assert.equal(r.events.filter(x=>x.kind==='slowdown').length,0);}
      else assert.ok(r.wrongAssociations>0);
    }
  });
  await test('队列溢出与未校准延迟可见且不声称合焦',async()=>{
    const e=await AfTestEngine.create(data);e.publish({probe:1000,fast:8000,fine:1000,newDirection:true});
    const overflow=e.simulate({frameInterval:10,imageDelay:100});assert.equal(overflow.status,'queue_overflow');
    const uncal=e.simulate({knownTiming:false,pixelNoise:0});assert.equal(uncal.events.filter(x=>x.kind==='slowdown').length,0);
    assert.equal(uncal.actualCameraTest,false);assert.equal(uncal.fullNativeAfEmulated,false);assert.equal(uncal.hardwareRequests,0);
  });
  await test('相同种子可复现且界面模型范围错误被拒绝',async()=>{
    const a=await AfTestEngine.create(data),b=await AfTestEngine.create(data);assert.deepEqual(a.simulate(),b.simulate());
    for(const model of [{frameInterval:0},{commandDelay:101},{speedGain:NaN},{pixelNoise:3}])assert.throws(()=>a.simulate(model));
  });
  fs.writeFileSync(path.join(build,'ui-tests.json'),JSON.stringify({hardwareRequests:0,wasmSha256:data.wasmSha256,payloadSha256:ref.payloadSha256,sourceSha256:Object.fromEntries(['CodeTests/test_native_ui.cjs','ui/engine.js','ui/controller.js','ui/index.html'].map(p=>[p,hash(read(p))])),passed:checks.length,checks},null,2)+'\n');
  console.log(checks.length,'checks passed');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
