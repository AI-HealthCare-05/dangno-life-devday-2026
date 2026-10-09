import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try {
 await mkdir('outputs/mobile/health-management',{recursive:true});
 for(const width of [390,720,1280]){
  const page=await browser.newPage({viewport:{width,height:1256}});
  let profile={birthday:'1975-01-01',gender:'FEMALE',name:'화면 확인'};
  let saved={eligibility_check_id:1,age:51,has_diabetes_diagnosis:false,has_urgent_warning_sign:false,
   population_in_scope:true,model_eligible:true,service_eligible:true,current_health_check_eligible:true,
   future_prediction_eligible:true,challenge_eligible:true,reason_codes:[]};
  let predictions=[], saves=0, inferenceRequests=0;
  await page.route('**/api/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname,method=request.method();
   let data={items:[]},status=200;
   if(path.endsWith('/users/me')){if(method==='PATCH')profile={...profile,...request.postDataJSON()};data=profile;}
   else if(path.endsWith('/eligibility-checks/latest'))data=saved;
   else if(path.endsWith('/eligibility-checks')&&method==='POST'){
    const body=request.postDataJSON();saves++;
    saved={...saved,eligibility_check_id:saved.eligibility_check_id+1,
     has_diabetes_diagnosis:body.has_diabetes_diagnosis,has_urgent_warning_sign:body.has_urgent_warning_sign};data=saved;
   }
   else if(path.endsWith('/consents'))data={items:[{consent_item:'health_data',version:'1.0',is_agreed:true,consent_id:1}]};
   else if(path.endsWith('/predictions'))data={items:predictions};
   else if(path.endsWith('/risk-factors'))data={status:'unavailable',display_allowed:false,items:[]};
   else if(path.endsWith('/prediction-jobs')){inferenceRequests++;status=500;}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  });
  async function restore(){
   await page.goto('http://127.0.0.1:8000/static/index.html?preview=results');
   await page.waitForFunction(()=>document.querySelector('.screen.active')?.dataset.step==='6');
   const seed=await page.evaluate(async()=>{
    const samples=[state.currentScreeningPrediction,state.prediction].filter(Boolean)
     .map((p,i)=>({...p,checkup_id:101,prediction_id:i+1}));
    window.history.replaceState({},'', '/static/index.html');state.token='synthetic-session';state.checkupId=101;state.analysisRun=null;
    state.userProfile=await api('/users/me');syncReturningEligibilityState(await api('/eligibility-checks/latest'));
    document.getElementById('message').style.setProperty('display','none','important');
    showStep(8);return samples;
   });
   if(!predictions.length)predictions=seed;
  }
  await restore();
  await page.locator('#open-health-management').click();
  await page.locator('#dashboard-edit-health').click();
  await page.waitForFunction(()=>state.step===4);
  await page.locator('[data-onboarding-step="3"]').click();
  await page.waitForFunction(()=>state.step===3);
  assert.equal(await page.locator('#eligibility-age-band-check').inputValue(),'50');
  assert.equal(await page.locator('#urgent-warning-no').isChecked(),true);
  assert.equal(await page.locator('#diagnosed-diabetes-no').isChecked(),true);
  await page.locator('#eligibility-form button[type="submit"]').click();
  await page.waitForFunction(()=>state.step===4);
  assert.equal(saves,1);
  await restore();
  await page.locator('#open-health-management').click();
  await page.locator('#dashboard-edit-health').click();
  await page.waitForFunction(()=>state.step===4);
  await page.locator('[data-onboarding-step="3"]').click();
  assert.equal(await page.locator('#urgent-warning-no').isChecked(),true);
  assert.equal(await page.locator('#diagnosed-diabetes-no').isChecked(),true);
  assert.equal(await page.locator('#eligibility-age-band-check').inputValue(),'50');
  await page.screenshot({path:`outputs/mobile/health-management/restored-${width}.png`});
  await page.locator('[data-onboarding-step="5"]').click();
  await page.waitForFunction(()=>document.querySelector('.screen.active')?.dataset.step==='6');
  assert.equal(await page.locator('.screen[data-step="5"]').isVisible(),false);
  assert.equal(await page.locator('.screen[data-step="6"]').isVisible(),true);
  assert.equal(inferenceRequests,0);
  await page.locator('[data-onboarding-step="4"]').click();
  await page.locator('[data-onboarding-step="5"]').click();
  await page.waitForFunction(()=>state.step===6);
  await page.screenshot({path:`outputs/mobile/health-management/result-${width}.png`});
  console.log(`PASS ${width}px: health management entry, eligibility save/reload, direct result tab, no inference rerun`);
  await page.close();
 }
}finally{await browser.close();}
