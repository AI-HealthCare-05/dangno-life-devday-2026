const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../src/frontend/app.js'),'utf8');
function harness(){
 const state={token:'test',cycle:{cycle_id:1}},nodes={
  '#barrier-challenge':{value:'7'},'#barrier-reason':{value:'goal_too_hard'},
  '#barrier-suggestion-text':{textContent:''},'#barrier-suggestion':{hidden:true}
 };const calls=[],messages=[];
 const ctx=vm.createContext({state,$:key=>nodes[key],isLocalPreview:()=>false,challengeDay:()=> '2026-10-02',
  api:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {suggestion:'작은 목표로 나누세요.'};},
  showMessage:(text,kind)=>messages.push({text,kind}),loadWeeklyReport:async()=>{throw new Error('report unavailable');}
 });
 vm.runInContext(source.match(/^async function saveBarrierRecord\([^]*?^}/m)[0],ctx);
 return {ctx,state,nodes,calls,messages,save:ctx.saveBarrierRecord};
}
test('reason save shows completion and the adjustment even when report refresh fails',async()=>{
 const h=harness();assert.equal(await h.save(),true);
 assert.deepEqual(h.calls,[{url:'/user-challenges/7/barriers',body:{log_date:'2026-10-02',reason_code:'goal_too_hard'}}]);
 assert.equal(h.nodes['#barrier-suggestion'].hidden,false);
 assert.equal(h.nodes['#barrier-suggestion-text'].textContent,'작은 목표로 나누세요.');
 assert.equal(h.messages[0].kind,'success');assert.match(h.messages[0].text,/기록했어요/);
});
test('failed save cannot show a completion or a new adjustment',async()=>{
 const h=harness();h.ctx.api=async()=>{throw new Error('save unavailable');};
 await assert.rejects(h.save(),/save unavailable/);assert.equal(h.messages.length,0);
 assert.equal(h.nodes['#barrier-suggestion'].hidden,true);
});
test('no selection sends no request',async()=>{
 const h=harness();h.nodes['#barrier-challenge'].value='';
 await assert.rejects(h.save(),/선택/);assert.equal(h.calls.length,0);
});
test('late response cannot announce a save for another account or cycle',async()=>{
 for(const change of ['token','cycle']){
  const h=harness();let resolve;h.ctx.api=()=>new Promise(r=>resolve=r);
  const pending=h.save();h.state[change]=change==='token'?'other':{cycle_id:2};resolve({suggestion:'test'});
  assert.equal(await pending,false);assert.equal(h.messages.length,0);assert.equal(h.nodes['#barrier-suggestion'].hidden,true);
 }
});
test('preview displays completion without writing to the server',async()=>{
 const h=harness();h.ctx.isLocalPreview=()=>true;assert.equal(await h.save(),true);
 assert.equal(h.calls.length,0);assert.equal(h.messages[0].kind,'success');
});
