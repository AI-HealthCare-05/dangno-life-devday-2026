const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function harness(file){
 const source=fs.readFileSync(path.join(__dirname,'../../src/frontend',file),'utf8');
 const nodes={},calls=[],state={token:'synthetic',userProfile:{birthday:'1975-01-01'},visitedSteps:new Set(),
  healthCheckupHistory:[],diagnosisRecords:[],healthHistoryPage:1,healthHistoryStartDate:'',healthHistoryEndDate:'',healthConsentStatus:'active',dailyCompleted:new Set()};
 const $=key=>nodes[key]||={value:'',hidden:true,innerHTML:'',textContent:'',setAttribute(k,v){this[k]=v}};
 const analysisButton={disabled:false,setAttribute(k,v){this[k]=v}};
 const context=vm.createContext({state,$,$$:()=>[analysisButton],Intl,Date,Object,Number,Set,Array,String,
  showStep:step=>calls.push(['step',step]),showMessage:message=>calls.push(['message',message]),
  hydrateSavedEligibilityForm:()=>{},setRadioValue:()=>{},clearHealthDraft:()=>calls.push(['draft-cleared']),
  showWorkspace:()=>{},escapeHtml:String,healthHistoryDateLabel:String,
  healthHistoryValue:v=>v??'-',healthHistoryBoolean:v=>String(v),isLocalPreview:()=>false,
  loadHealthCheckupHistory:async()=>{},renderDailyRecordList:()=>{},renderDashboardRiskSummary:()=>{},
  hasSameDaySymptoms:()=>false,isSameDayAnswerUncertain:()=>false,
  showEligibilityGuidance:reasons=>calls.push(['guidance',reasons]),hydrateSavedEligibilityForm:()=>{},
  returnToForestSettings:async()=>false,resetEligibilityAnswers:()=>{},setFormBusy:()=>()=>{},
  hasUrgentSymptoms:()=>false,isUrgentAnswerUncertain:()=>false,document:{querySelector:s=>({value:s.includes('urgent-warning')?'no':'yes'})},
  api:async(route,options)=>{calls.push(['api',route,JSON.parse(options.body)]);return context.result},
 });
 function load(...names){for(const name of names){const match=source.match(new RegExp('^(?:async )?function '+name+'\\([^]*?^}','m'));assert.ok(match,name);vm.runInContext(match[0],context)}}
 load('healthRecordDate','healthRecordAnalysisBlocked','healthHistoryTimeline','diagnosisRecordId','diagnosisHistoryCard','syncDiagnosisAnalysisControls','beginNewHealthRecord','beginHealthRecordEdit','recordDiagnosisResponse');
 return {context,state,$,calls,analysisButton,load,source};
}
for(const file of ['app.js','intro-retro-app.js']){
 test(file+': re-recording keeps the original health ID and date and blocks both tabs until eligibility is saved',()=>{
  const h=harness(file), health={checkup_id:7,checkup_date:'2026-10-01'};
  h.state.healthCheckupHistory=[health];h.state.prediction={id:3};
  h.context.beginHealthRecordEdit(health);
  assert.equal(h.state.editingHealthCheckupId,7);
  assert.equal(h.state.healthRecordContextDate,'2026-10-01');
  assert.equal(h.state.newHealthEligibilityPending,true);assert.equal(h.state.prediction,null);
  assert.equal(h.analysisButton.disabled,true);assert.equal(h.$('#diagnosis-record-date').disabled,true);
  assert.ok(h.calls.some(c=>c[0]==='step'&&c[1]===3));
  h.state.newHealthEligibilityPending=false;h.state.step=3;
  h.context.document.querySelector=()=>({value:'yes'});h.context.syncDiagnosisAnalysisControls();
  assert.equal(h.analysisButton.disabled,true);
  h.context.document.querySelector=()=>({value:'no'});h.context.syncDiagnosisAnalysisControls();
  assert.equal(h.analysisButton.disabled,false);
 });
 test(file+': diagnosis history offers edit/delete and edits its linked health record',()=>{
  const h=harness(file), health={checkup_id:7,checkup_date:'2026-10-01'}, record={diagnosis_record_id:88,
   record_type:'diabetes_diagnosis',record_date:'2026-10-01',source_checkup_id:7};
  h.state.healthCheckupHistory=[health];h.state.diagnosisRecords=[record];
  const html=h.context.diagnosisHistoryCard(record);
  assert.match(html,/data-diagnosis-record-edit="88"/);assert.match(html,/data-diagnosis-record-delete="88"/);
  h.context.beginHealthRecordEdit(record);
  assert.equal(h.state.editingHealthCheckupId,7);assert.equal(h.state.editingDiagnosisRecordId,88);
  assert.equal(h.state.healthRecordContextDate,'2026-10-01');assert.equal(h.$('#diagnosis-record-date-row').hidden,false);
 });
 test(file+': deleting a diagnosis requires confirmation and keeps it visible on API failure',async()=>{
  const h=harness(file),record={diagnosis_record_id:88,record_type:'diabetes_diagnosis',record_date:'2026-10-01'};
  h.state.diagnosisRecords=[record];h.load('handleDiagnosisHistoryAction');
  const button={dataset:{diagnosisRecordDelete:'88'}},event={target:{closest:s=>s.includes('delete')?button:null},preventDefault(){},stopPropagation(){}};
  h.context.window={confirm:()=>false};h.context.setButtonBusy=()=>()=>{};
  await h.context.handleDiagnosisHistoryAction(event);
  assert.equal(h.calls.filter(c=>c[0]==='api').length,0);assert.equal(h.state.diagnosisRecords.length,1);
  h.context.window.confirm=()=>true;h.context.api=async()=>{throw new Error('offline')};
  await h.context.handleDiagnosisHistoryAction(event);assert.equal(h.state.diagnosisRecords.length,1);
  h.context.api=async(route,options)=>h.calls.push(['delete',route,options.method]);
  await h.context.handleDiagnosisHistoryAction(event);
  assert.deepEqual(h.calls.find(c=>c[0]==='delete'),['delete','/diagnosis-records/88','DELETE']);
  assert.equal(h.state.diagnosisRecords.length,0);assert.equal(h.state.currentDiagnosisRecord,null);
 });
 test(file+': diagnosis submission sends the original record context rather than today',async()=>{
  const h=harness(file);h.load('eligibilityCapabilities','inferFuturePredictionCapability','syncReturningEligibilityState');
  h.state.editingHealthCheckupId=7;h.state.editingDiagnosisRecordId=88;h.state.healthRecordContextDate='2026-10-01';
  h.$('#eligibility-birth-date').value='1975-01-01';h.$('#gender').value='FEMALE';
  h.context.document.querySelector=s=>({value:s.includes('urgent-warning')?'no':'yes'});
  h.context.result={age:51,has_diabetes_diagnosis:true,model_eligible:false,record_date:'2026-10-01',
   diagnosis_record:{diagnosis_record_id:88,record_type:'diabetes_diagnosis',record_date:'2026-10-01'}};
  const match=h.source.match(/\$\("#eligibility-form"\)\.addEventListener\("submit", async \(event\) => \{([\s\S]*?)\n\}\);/);
  vm.runInContext('async function submit(event){'+match[1]+'\n}',h.context);
  await h.context.submit({preventDefault(){},currentTarget:{},submitter:{}});
  const body=h.calls.find(c=>c[0]==='api'&&c[1]==='/eligibility-checks')[2];
  assert.equal(body.health_checkup_id,7);assert.equal(body.diagnosis_record_id,88);assert.equal(body.record_date,'2026-10-01');
  assert.equal(h.state.currentDiagnosisRecord.record_date,'2026-10-01');
 });
 test(file+': every new record starts eligibility and discards the previous analysis selection',()=>{
  const h=harness(file);h.state.checkupId=9;h.state.prediction={id:1};h.state.editingHealthCheckupId=9;
  h.context.beginNewHealthRecord();
  assert.equal(h.state.newHealthEligibilityPending,true);assert.equal(h.state.checkupId,null);
  assert.equal(h.state.prediction,null);assert.equal(h.state.editingHealthCheckupId,null);
  assert.equal(h.analysisButton.disabled,true);assert.ok(h.calls.some(c=>c[0]==='step'&&c[1]===3));
  assert.equal(h.calls.filter(c=>c[0]==='api').length,0);
 });
 test(file+': diagnosis replaces matching measurement cards and leaves other dates visible',()=>{
  const h=harness(file);
  h.state.diagnosisRecords=[{record_type:'diabetes_diagnosis',record_date:'2026-10-15',label:'당뇨병 진단'}];
  h.state.healthCheckupHistory=[{checkup_id:1,checkup_date:'2026-10-15'},{checkup_id:2,checkup_date:'2026-10-14'}];
  assert.equal(h.context.healthRecordAnalysisBlocked(h.state.healthCheckupHistory[0]),true);
  assert.equal(h.context.healthRecordAnalysisBlocked(h.state.healthCheckupHistory[1]),false);
  h.load('renderHealthCheckupHistory');h.context.renderHealthCheckupHistory();
  const html=h.$('#health-history-list').innerHTML;
  assert.match(html,/당뇨병 진단/);assert.match(html,/예측·분석 비활성화/);assert.equal(h.$('#health-history-count').textContent,'2건');
  assert.equal(h.state.healthCheckupHistory.length,2);
  assert.doesNotMatch(html,/data-health-history-(?:edit|delete|result)="1"/);
  assert.match(html,/data-health-history-edit="2"/);
  if(file==='app.js'){
   assert.doesNotMatch(html,/data-health-history-result="2" disabled/);
  }
 });
 test(file+': linked measurements are omitted before counting/pagination and return when diagnosis is removed',()=>{
  const h=harness(file);
  const records=[{checkup_id:7,checkup_date:'2026-10-14',height_cm:177.7},
   {checkup_id:8,checkup_date:'2026-10-15',height_cm:188.8},{checkup_id:9,checkup_date:'2026-10-13',height_cm:166.6}];
  h.state.healthCheckupHistory=records;
  h.state.diagnosisRecords=[{diagnosis_record_id:4,record_type:'diabetes_diagnosis',record_date:'2026-10-15',source_checkup_id:'7'}];
  h.load('renderHealthCheckupHistory');h.context.renderHealthCheckupHistory();
  const html=h.$('#health-history-list').innerHTML;
  assert.equal(h.$('#health-history-count').textContent,'2건');
  assert.doesNotMatch(html,/177\.7|188\.8|data-health-history-(?:edit|delete|result)="[78]"/);
  assert.match(html,/166\.6/);assert.match(html,/data-diagnosis-record-edit="4"/);
  assert.equal(h.state.healthCheckupHistory.length,3);
  h.state.diagnosisRecords=[];h.context.renderHealthCheckupHistory();
  assert.equal(h.$('#health-history-count').textContent,'3건');
  assert.match(h.$('#health-history-list').innerHTML,/177\.7/);
 });
 test(file+': a diagnosis response clears stale model and challenge state and preserves urgent priority',async()=>{
  const h=harness(file);h.state.prediction={id:1};h.state.cycle={cycle_id:1};
  const record={record_type:'diabetes_diagnosis',record_date:'2026-10-15',analysis_allowed:false};
  assert.equal(await h.context.recordDiagnosisResponse({has_diabetes_diagnosis:true,record_date:'2026-10-15',
   diagnosis_record:record,reason_codes:['DIAGNOSED_DIABETES','URGENT_MEDICAL_ATTENTION']}),true);
  assert.equal(h.state.diagnosisRecords.length,1);assert.equal(h.state.currentDiagnosisRecord,record);
  assert.equal(h.state.prediction,null);assert.equal(h.state.cycle,null);assert.equal(h.analysisButton.disabled,true);
  assert.ok(h.calls.find(c=>c[0]==='guidance')[1].includes('URGENT_MEDICAL_ATTENTION'));
 });
 test(file+': urgent + diagnosed submission still posts both facts and never posts model or health inputs',async()=>{
  const h=harness(file);h.load('eligibilityCapabilities','inferFuturePredictionCapability','syncReturningEligibilityState');
  h.$('#eligibility-birth-date').value='1975-01-01';h.$('#gender').value='FEMALE';
  h.context.document.querySelector=()=>({value:'yes'});
  h.context.result={age:51,has_diabetes_diagnosis:true,has_urgent_warning_sign:true,model_eligible:false,
   current_health_check_eligible:false,challenge_eligible:false,future_prediction_eligible:false,
   record_date:'2026-10-15',diagnosis_record:{record_type:'diabetes_diagnosis',record_date:'2026-10-15'},
   reason_codes:['DIAGNOSED_DIABETES','URGENT_MEDICAL_ATTENTION']};
  const match=h.source.match(/\$\("#eligibility-form"\)\.addEventListener\("submit", async \(event\) => \{([\s\S]*?)\n\}\);/);
  vm.runInContext('async function submit(event){'+match[1]+'\n}',h.context);
  await h.context.submit({preventDefault(){},currentTarget:{},submitter:{}});
  const requests=h.calls.filter(c=>c[0]==='api');assert.equal(requests.length,2);
  assert.equal(requests[1][1],'/eligibility-checks');assert.equal(requests[1][2].has_diabetes_diagnosis,true);
  assert.equal(requests[1][2].has_urgent_warning_sign,true);assert.equal(h.state.medicalGuidanceRequired,true);
 });
 test(file+': failed diagnosis storage never hides immediate urgent guidance or invents a saved record',async()=>{
  const h=harness(file);h.context.document.querySelector=()=>({value:'yes'});
  h.context.api=async()=>{throw new Error('offline')};
  const match=h.source.match(/\$\("#eligibility-form"\)\.addEventListener\("submit", async \(event\) => \{([\s\S]*?)\n\}\);/);
  vm.runInContext('async function submit(event){'+match[1]+'\n}',h.context);
  await h.context.submit({preventDefault(){},currentTarget:{},submitter:{}});
  assert.ok(h.calls.find(c=>c[0]==='guidance')[1].includes('URGENT_MEDICAL_ATTENTION'));
  assert.equal(h.state.diagnosisRecords.length,0);assert.equal(h.state.currentDiagnosisRecord,undefined);
 });
 test(file+': calendar dates use Korea midnight',()=>{
  const h=harness(file);
  assert.equal(h.context.healthRecordDate('2026-10-14T15:01:00Z'),'2026-10-15');
  assert.equal(h.context.healthRecordDate('2026-10-14T14:59:00Z'),'2026-10-14');
 });
}
test('analysis tab rejects a diagnosed day before using cached results or making requests',async()=>{
 const h=harness('app.js');h.state.currentDiagnosisRecord={record_type:'diabetes_diagnosis',record_date:'2026-10-15'};
 h.state.analysisRun={busy:false,models:{today:{status:'succeeded'}}};h.load('openAnalysisTab');
 await h.context.openAnalysisTab();assert.ok(h.calls.some(c=>c[0]==='message'));assert.ok(!h.calls.some(c=>c[0]==='api'||c[0]==='step'));
});
