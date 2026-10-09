const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../../src/frontend/app.js'),'utf8');
function load(names, data) {
  const context=vm.createContext(data);
  for(const name of names){
    const match=source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`,'m'));
    assert.ok(match,name);vm.runInContext(match[0],context);
  }
  return context;
}
function eligibilityHarness() {
  const state={token:'account-a',userProfile:{birthday:'1975-01-01',gender:'FEMALE'}};
  const nodes={},answers={};
  const $=key=>nodes[key] ||= {value:'',hidden:true,textContent:''};
  const context=load(['hydrateSavedEligibilityForm','resetEligibilityAnswers'],{
    state,$,setRadioValue:(name,value)=>answers[name]=value,
    clearQuestionnaireAnswers:name=>delete answers[name],syncEmergencyQuestionnaire(){}
  });
  return {state,nodes,answers,$,hydrate:context.hydrateSavedEligibilityForm};
}
const saved={eligibility_check_id:1,age:51,has_diabetes_diagnosis:false,has_urgent_warning_sign:false};
test('saved no answers, profile and age band restore after a fresh session',()=>{
  const h=eligibilityHarness();h.hydrate(saved);
  assert.equal(h.$('#eligibility-birth-date').value,'1975-01-01');
  assert.equal(h.$('#gender').value,'FEMALE');
  assert.equal(h.$('#eligibility-age-band-check').value,'50');
  assert.equal(h.answers['urgent-warning'],'no');
  assert.equal(h.answers['diabetes-diagnosis'],'no');
});
test('reopening the same record preserves an unsaved draft; a new record restores saved yes answers',()=>{
  const h=eligibilityHarness();h.hydrate(saved);
  h.answers['urgent-warning']='yes';h.$('#eligibility-age-band-check').value='60';
  h.hydrate(saved);
  assert.equal(h.answers['urgent-warning'],'yes');assert.equal(h.$('#eligibility-age-band-check').value,'60');
  h.hydrate({...saved,eligibility_check_id:2,has_diabetes_diagnosis:true,has_urgent_warning_sign:true});
  assert.equal(h.answers['urgent-warning'],'yes');assert.equal(h.answers['diabetes-diagnosis'],'yes');
  assert.equal(h.$('#eligibility-age-band-check').value,'50');
});
test('a different account restores independently and clears stale symptom questionnaire answers',()=>{
  const h=eligibilityHarness();h.hydrate(saved);
  h.state.token='account-b';h.answers['urgent-summary']='yes';h.answers['diabetes-diagnosis']='yes';
  h.hydrate(saved);
  assert.equal(h.answers['urgent-summary'],undefined);assert.equal(h.answers['diabetes-diagnosis'],'no');
});
test('missing saved safety answers remain unanswered; old age bands cap at 80',()=>{
  const h=eligibilityHarness();h.answers['urgent-warning']='no';
  h.hydrate({eligibility_check_id:5,age:91});
  assert.equal(h.answers['urgent-warning'],undefined);assert.equal(h.answers['diabetes-diagnosis'],undefined);
  assert.equal(h.$('#eligibility-age-band-check').value,'80');
});
function analysisHarness() {
  const state={token:'account-a',checkupId:4};let mode='ok';const calls=[];
  const context=load(['openAnalysisTab'],{
    state,analysisInputKey:()=>JSON.stringify([state.token,state.checkupId]),isLocalPreview:()=>false,
    showStep:step=>calls.push(['step',step]),showMessage:message=>calls.push(['message',message]),
    openSavedAnalysisResult:async id=>{calls.push(['saved',id]);if(mode==='fail')throw new Error('unavailable');}
  });
  return {state,calls,open:context.openAnalysisTab,fail:()=>mode='fail'};
}
for(const [name,busy,models,expected] of [
 ['complete',false,{today:{status:'succeeded'},future:{status:'succeeded'}},6],
 ['partial result',false,{today:{status:'succeeded'},future:{status:'failed'}},6],
 ['in progress',true,{today:{status:'succeeded'},future:{status:'pending'}},5],
 ['both failed',false,{today:{status:'failed'},future:{status:'failed'}},5]
])test(`analysis tab opens ${name} in the correct view without rerunning inference`,async()=>{
  const h=analysisHarness();h.state.analysisRun={key:JSON.stringify([h.state.token,4]),busy,models};
  await h.open();assert.deepEqual(h.calls,[['step',expected]]);
});
test('a restored session loads the selected checkup; an old run never takes precedence',async()=>{
  const h=analysisHarness();h.state.analysisRun={key:'stale',busy:true,models:{today:{status:'succeeded'}}};
  await h.open();assert.deepEqual(h.calls,[['saved',4]]);assert.equal(h.state.analysisTabBusy,false);
});
test('without a health record the tab explains that input is needed',async()=>{
  const h=analysisHarness();h.state.checkupId=null;await h.open();
  assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'message');
});
test('failed saved result loading releases the lock for retry; duplicate taps are ignored',async()=>{
  const h=analysisHarness();h.fail();await assert.rejects(h.open(),/unavailable/);
  assert.equal(h.state.analysisTabBusy,false);h.state.analysisTabBusy=true;h.calls.length=0;
  await h.open();assert.equal(h.calls.length,0);
});
