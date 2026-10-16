// Synthetic UI audit only: never submits diagnosis answers or calls real locations/phones.
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';
const base=process.env.QA_BASE_URL||'http://127.0.0.1:8000';
assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname));
const output=path.resolve('outputs/mobile/diagnosis-guidance');await mkdir(output,{recursive:true});
const backSource=(await readFile('src/frontend/mobile/back-navigation.mjs','utf8')).replace('export function handleAppBack','window.qaHandleAppBack = function');
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_BIN||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const checks=[];
async function setup(width,height,large=false){
 const page=await browser.newPage({viewport:{width,height}}),errors=[],requests=[];
 const fixture={provider:'kakao_local_api',fail:false};page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());requests.push({method:request.method(),path:url.pathname});
  if(url.pathname.includes('/auth/'))return route.fulfill({status:401,json:{detail:'Synthetic audit'}});
  if(url.pathname.endsWith('/medical-facilities/nearby'))return route.fulfill(fixture.fail?{status:503,json:{detail:'Synthetic provider failure'}}:{status:200,json:{data:{
   provider_kind:fixture.provider,facilities:[{name:'검증용 기관 A',phone:'02-0000-0000',address:'검증 주소',distance_meters:100},
    {name:'검증용 기관 B',phone:'',distance_meters:200},{name:'검증용 기관 C',phone:'미등록',distance_meters:300}],retrieved_radius_meters:5000}}});
  return route.fulfill({status:200,json:{data:{items:[],enabled:false,user_id:999,fields:[],carrots_per_field:100}}});
 });
 await page.goto(base+'/static/index.html?auth=login');await page.waitForFunction(()=>typeof showEligibilityGuidance==='function');
 await page.evaluate(large=>{
  state.token='synthetic-guidance';state.userProfile={id:999,birthday:'1975-01-01',gender:'FEMALE'};state.accountRecovery=null;
  state.healthConsentStatus='active';state.newHealthEligibilityPending=false;state.diagnosisRecords=[{diagnosis_record_id:88,record_type:'diabetes_diagnosis',record_date:'2026-10-01'}];
  state.healthCheckupHistory=[{checkup_id:7,checkup_date:'2026-10-01',height_cm:177.7},{checkup_id:8,checkup_date:'2026-09-30',height_cm:166.6}];
  document.body.classList.toggle('large-text',large);showStep(3,{recordHistory:false});showEligibilityGuidance(['DIAGNOSED_DIABETES']);
 },large);
 await page.addScriptTag({content:backSource});return {page,errors,requests,fixture};
}
function noWrites(requests){assert.equal(requests.filter(r=>r.method!=='GET'&&!r.path.includes('/auth/')).length,0)}
try {
 for(const [width,height] of [[320,700],[390,900],[720,900],[1024,800]])for(const large of [false,true]){
  const {page,errors,requests}=await setup(width,height,large),panel=page.locator('#eligibility-guidance');
  await page.waitForFunction(()=>{
   const box=document.querySelector('#eligibility-guidance').getBoundingClientRect();
   const title=document.querySelector('#eligibility-guidance-title').getBoundingClientRect();
   return box.top>=0&&box.bottom<=innerHeight+1&&title.top>=0;
  },null,{timeout:5000}).catch(async error=>{
   console.log('Popup bounds',width,large,await panel.evaluate(n=>({top:n.getBoundingClientRect().top,bottom:n.getBoundingClientRect().bottom,scroll:n.scrollTop,title:n.querySelector('h3').getBoundingClientRect().top})));
   throw error;
  });
  assert.equal(await panel.evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
  assert.ok((await page.locator('#eligibility-guidance-title').boundingBox()).y>=0);
  assert.equal(await page.locator('#find-diagnosed-phone').count(),0);
  for(const id of ['view-diagnosis-history','find-diagnosed-medical','eligibility-edit-answer']){
   const button=page.locator('#'+id);await button.scrollIntoViewIfNeeded();const rect=await button.boundingBox();
   assert.ok(rect.x>=0&&rect.x+rect.width<=width+1,JSON.stringify({width,large,id,rect}));
  }
  await panel.evaluate(n=>{n.scrollTop=0;n.focus()});await page.keyboard.press('Shift+Tab');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'eligibility-edit-answer');
  await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'view-diagnosis-history');
  await panel.evaluate(n=>{n.scrollTop=0});
  await page.screenshot({path:path.join(output,`popup-${width}-${large?'large':'normal'}.png`)});
  await page.evaluate(()=>qaHandleAppBack({document,window,app:{minimizeApp:async()=>{throw Error('Unexpected minimize')}},canGoBack:true}));
  assert.equal(await panel.isHidden(),true);assert.equal(await page.evaluate(()=>state.step),3);
  await page.evaluate(()=>showEligibilityGuidance(['DIAGNOSED_DIABETES']));await page.locator('#eligibility-edit-answer').click();assert.equal(await panel.isHidden(),true);
  await page.evaluate(()=>showEligibilityGuidance(['DIAGNOSED_DIABETES']));await page.keyboard.press('Escape');assert.equal(await panel.isHidden(),true);
  await page.evaluate(()=>showEligibilityGuidance(['DIAGNOSED_DIABETES']));await page.locator('#view-diagnosis-history').click();
  assert.equal(await page.evaluate(()=>state.step),8);assert.equal(await page.locator('#home-health-management').isVisible(),true);
  assert.match(await page.locator('.health-history-diagnosis').innerText(),/당뇨병 진단/);
  assert.equal(await page.locator('#health-history-list .health-history-item').count(),2);
  assert.equal(await page.locator('[data-health-history-edit="7"]').count(),0);
  assert.equal(await page.locator('[data-health-history-edit="8"]').count(),1);
  assert.equal(await page.locator('#health-history-list').evaluate(n=>n.textContent.includes('177.7')),false);
  const record=page.locator('.health-history-diagnosis').first(),summary=record.locator('summary');
  const arrow=await summary.evaluate(n=>{const s=getComputedStyle(n,'::after');return {width:s.width,height:s.height,image:s.backgroundImage,background:s.backgroundColor}});
  assert.ok(Math.abs(parseFloat(arrow.width)-44)<.1);assert.ok(Math.abs(parseFloat(arrow.height)-44)<.1);assert.match(arrow.image,/health-history-chevron\.svg/);
  assert.equal(arrow.background,'rgb(255, 255, 255)');
  for(const item of await page.locator('#health-history-list .health-history-item, #health-history-list summary, #health-history-list .health-history-values').all()){
   assert.equal(await item.evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(255, 255, 255)');
  }
  const wasOpen=await record.evaluate(n=>n.open);
  await summary.focus();await page.keyboard.press('Enter');assert.equal(await record.evaluate(n=>n.open),!wasOpen);
  await page.keyboard.press('Enter');assert.equal(await record.evaluate(n=>n.open),wasOpen);
  await record.screenshot({path:path.join(output,`record-arrow-${width}-${large?'large':'normal'}.png`)});
  assert.deepEqual(errors,[]);noWrites(requests);checks.push({width,height,large,layout:true,close:true,escape:true,nativeBack:true,history:true});await page.close();
 }
 {
  const {page,errors,requests,fixture}=await setup(390,900);
  await page.evaluate(()=>{window.qaLocationCalls=0; navigator.geolocation.getCurrentPosition=(_success,error)=>{window.qaLocationCalls++;error({code:1})};coordinatesForAddress=async()=>({lat:37.5,lon:127})});
  await page.locator('#find-diagnosed-medical').click();
  const dialog=page.locator('#eligibility-medical-dialog');await dialog.waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>state.step),3);assert.equal(await page.evaluate(()=>window.qaLocationCalls),0);
  assert.equal(await page.locator('#eligibility-guidance').isHidden(),true);
  assert.equal(await dialog.evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
  await page.locator('#find-nearby-medical-facilities').click();
  assert.equal(await page.locator('#medical-facility-status').getAttribute('data-state'),'permission');
  assert.equal(await page.locator('#facility-address-form').isVisible(),true);
  await page.locator('#facility-address').fill('검증용 주소');await page.locator('#facility-address-form button').click();
  await page.waitForFunction(()=>document.querySelector('#medical-facility-status').dataset.state==='done');
  assert.equal(await page.locator('#medical-facility-results .medical-facility-card').count(),3);
  assert.equal(await page.locator('#medical-facility-results a[href^="tel:"]').count(),1);
  assert.equal(await page.locator('#medical-facility-results .facility-action-unavailable').filter({hasText:'전화번호 없음'}).count(),2);
  assert.match(await page.locator('#eligibility-medical-description').innerText(),/상담 가능 여부는 기관에 직접 확인/);
  await page.screenshot({path:path.join(output,'medical-unified.png')});
  assert.equal(await page.locator('.medical-facility-more').isHidden(),true);
  const searchRequestsBefore=requests.filter(r=>r.path.endsWith('/medical-facilities/nearby')).length;
  await page.evaluate(()=>renderMedicalFacilities({provider_kind:'kakao_local_api',facilities:Array.from({length:12},(_,i)=>({name:`검증용 기관 ${i+1}`,phone:'02-0000-0000',distance_meters:100+i}))}));
  const cards=page.locator('#medical-facility-results .medical-facility-card'),more=page.locator('.medical-facility-more');
  assert.equal(await cards.count(),5);await cards.first().evaluate(n=>n.dataset.preserved='yes');
  await more.click();assert.equal(await cards.count(),10);assert.equal(await cards.first().getAttribute('data-preserved'),'yes');
  await more.click();assert.equal(await cards.count(),12);assert.equal(await more.isHidden(),true);
  const positions=await cards.evaluateAll(nodes=>nodes.map(n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,bottom:b.bottom}}));
  for(let i=1;i<positions.length;i++){assert.equal(positions[i].x,positions[0].x);assert.ok(positions[i].y>=positions[i-1].bottom);}
  assert.equal(requests.filter(r=>r.path.endsWith('/medical-facilities/nearby')).length,searchRequestsBefore);
  for(const count of [6,5,0]){
   await page.evaluate(count=>renderMedicalFacilities({provider_kind:'kakao_local_api',facilities:Array.from({length:count},(_,i)=>({name:`새 검색 ${i+1}`}))}),count);
   assert.equal(await cards.count(),Math.min(count,5));
   if(count>5){await more.click();assert.equal(await cards.count(),6);}
   if(count>0)assert.equal(await more.isHidden(),true);
   else {assert.equal(await more.count(),0);assert.equal(await page.locator('#medical-facility-results').isHidden(),true);}
  }
  fixture.provider='development';await page.locator('#find-nearby-medical-facilities').click();
  await page.evaluate(()=>requestMedicalFacilities({lat:37.5,lon:127},document.querySelector('#find-nearby-medical-facilities')));
  assert.equal(await page.locator('#medical-facility-status').getAttribute('data-state'),'sample');assert.equal(await page.locator('#medical-facility-results').isHidden(),true);
  fixture.fail=true;await page.evaluate(()=>requestMedicalFacilities({lat:37.5,lon:127},document.querySelector('#find-nearby-medical-facilities')));
  assert.equal(await page.locator('#medical-facility-status').getAttribute('data-state'),'failed');
  await page.evaluate(()=>qaHandleAppBack({document,window,app:{minimizeApp:async()=>{throw Error('Unexpected minimize')}},canGoBack:true}));
  await page.locator('#eligibility-guidance').waitFor({state:'visible'});assert.equal(await dialog.count(),0);
  assert.equal(await page.locator('#medical-guidance-detail .medical-facility-list').count(),1);
  assert.equal(await page.locator('#medical-facility-results').count(),1);
  await page.locator('#find-diagnosed-medical').click();await page.locator('#eligibility-medical-dialog [data-close]').click();
  await page.locator('#eligibility-guidance').waitFor({state:'visible'});
  await page.locator('#view-diagnosis-history').click();await page.waitForFunction(()=>state.step===8);
  await page.locator('#dashboard-find-nearby-medical-facilities').click();
  await page.locator('#eligibility-medical-dialog').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>state.step),8);
  await page.locator('#eligibility-medical-dialog [data-close]').click();
  await page.locator('#eligibility-medical-dialog').waitFor({state:'detached'});
  assert.equal(await page.locator('#eligibility-guidance').isHidden(),true);
  assert.deepEqual(errors,[]);noWrites(requests);checks.push({unifiedMedicalSearch:true,verticalMoreFiveAtATime:true,locationPermissionDenied:true,addressSearch:true,phoneLinks:true,developmentHidden:true,providerFailure:true,returnToGuidance:true,noAnalysisNavigation:true});await page.close();
 }
 await writeFile(path.join(output,'audit.json'),JSON.stringify(checks,null,2));console.log('PASS diagnosis guidance audit',checks.length,'scenarios');
}finally{await browser.close()}
