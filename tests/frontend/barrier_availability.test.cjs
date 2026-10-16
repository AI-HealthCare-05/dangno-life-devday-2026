const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
for(const file of ['app.js','intro-retro-app.js']) {
 const source=fs.readFileSync(path.join(__dirname,'../../src/frontend',file),'utf8');
 function harness() {
  const state={cycle:{user_challenges:[7,8,9].map(user_challenge_id=>({user_challenge_id}))},dailyCompleted:new Set(),dailyRecordsStatus:'ready'};
  const controls=[{disabled:false},{disabled:false},{disabled:false}],attrs={};
  const nodes={'#barrier-form':{querySelectorAll:()=>controls,getAttribute:key=>attrs[key],setAttribute:(key,value)=>attrs[key]=value},
   '#barrier-status':{hidden:true,textContent:''},'#barrier-suggestion':{hidden:false}};
  const context=vm.createContext({state,$:key=>nodes[key]});
  for(const name of ['hasCurrentChallengeCycle','barrierFormAvailability','renderBarrierForm']) {
   vm.runInContext(source.match(new RegExp(`^function ${name}\\([^]*?^}`, 'm'))[0],context);
  }
  return {state,controls,attrs,nodes,render:context.renderBarrierForm,availability:context.barrierFormAvailability};
 }
 test(`${file}: all completed disables every control and hides the old adjustment`,()=>{
  const h=harness();h.state.dailyCompleted=new Set(['7','8','9']);h.render();
  assert.ok(h.controls.every(control=>control.disabled));assert.equal(h.attrs['aria-disabled'],'true');
  assert.match(h.nodes['#barrier-status'].textContent,/모두 실천/);assert.equal(h.nodes['#barrier-status'].hidden,false);
  assert.equal(h.nodes['#barrier-suggestion'].hidden,true);
 });
 test(`${file}: undo and a new day re-enable the form`,()=>{
  const h=harness();h.state.dailyCompleted=new Set(['7','8','9']);h.render();
  h.state.dailyCompleted.delete('9');h.render();assert.ok(h.controls.every(control=>!control.disabled));
  assert.equal(h.attrs['aria-disabled'],'false');assert.equal(h.nodes['#barrier-status'].hidden,true);
  h.state.dailyCompleted=new Set();h.render();assert.equal(h.availability().disabled,false);
 });
 test(`${file}: stale completion IDs do not disable a different challenge set`,()=>{
  const h=harness();h.state.dailyCompleted=new Set(['7','old1','old2']);h.render();
  assert.ok(h.controls.every(control=>!control.disabled));
 });
 test(`${file}: loading, read failure, and no cycle cannot submit a reason`,()=>{
  const h=harness();
  for(const status of ['loading','error']) {h.state.dailyRecordsStatus=status;h.render();assert.ok(h.controls.every(c=>c.disabled));}
  h.state.dailyRecordsStatus='ready';h.state.cycle=null;h.render();assert.ok(h.controls.every(c=>c.disabled));
 });
 test(`${file}: busy restore cannot re-enable an all-completed form`,()=>{
  const h=harness();h.attrs['aria-busy']='true';h.render();assert.ok(h.controls.every(c=>c.disabled));
  h.state.dailyCompleted=new Set(['7','8','9']);delete h.attrs['aria-busy'];h.controls.forEach(c=>c.disabled=false);
  h.render();assert.ok(h.controls.every(c=>c.disabled));
  assert.ok(source.includes('renderBarrierForm();'), 'daily render and submit restore use the shared availability');
 });
}
