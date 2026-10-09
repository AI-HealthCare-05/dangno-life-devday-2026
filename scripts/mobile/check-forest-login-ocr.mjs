import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const origin='http://127.0.0.1:8000';let authCount=0,ocrCount=0;
await mkdir('outputs/mobile/forest-login-ocr',{recursive:true});
try {
 // A stale client token must not bypass the server's account check.
 for(const path of ['/forest','/static/forest.html']) for(const expired of [false,true]) {
  const page=await browser.newPage();let gameRequests=0;
  await page.addInitScript(()=>sessionStorage.setItem('gandang-forest-api-session-v1',JSON.stringify({accessToken:'stale-synthetic',expiresAt:Date.now()+60000})));
  page.on('request',request=>{if(/phaser|forest-game\.js/.test(request.url()))gameRequests++;});
  await page.route('**/api/**',route=>route.fulfill({status:expired&&route.request().url().includes('/token/refresh')?200:401,contentType:'application/json',body:expired?' {"access_token":"expired-synthetic"}':'{}'}));
  await page.goto(origin+path);await page.waitForURL('**/service?auth=login&returnTo=forest');
  await page.waitForFunction(()=>typeof state!=='undefined'&&state.step===2);
  assert.equal(gameRequests,0);assert.equal(await page.locator('#login-form').isVisible(),true);
  assert.equal(await page.locator('#header-forest-entry').getAttribute('href'),'/service?auth=login&returnTo=forest');
  await page.locator('#login-signup-back').click();assert.equal(await page.locator('#signup-form').isVisible(),true);assert.ok(page.url().includes('returnTo=forest'));
  authCount++;await page.close();
 }
 // Connection failure stays blocked and a successful retry starts the real engine.
 {
  const page=await browser.newPage({viewport:{width:411,height:808}});let ready=false,gameRequests=0;
  page.on('request',r=>{if(/forest-game\.js/.test(r.url()))gameRequests++;});
  await page.route('**/api/**',route=>{const url=route.request().url();const response=ready&&url.includes('/token/refresh')?{status:200,body:'{"access_token":"synthetic-account"}'}:ready&&url.endsWith('/users/me')?{status:200,body:'{"id":99999,"name":"검증 사용자"}'}:{status:503,body:'{}'};return route.fulfill({...response,contentType:'application/json'});});
  await page.goto(origin+'/forest');await page.locator('#forest-access-retry').waitFor({state:'visible'});assert.equal(gameRequests,0);
  ready=true;await page.locator('#forest-access-retry').click();
  await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});
  assert.equal(gameRequests,1);assert.equal(await page.locator('#forest-boot').isVisible(),false);
  assert.equal(await page.evaluate(()=>Boolean(window.ForestObjects&&window.Phaser)),true);
  authCount++;await page.close();
 }
 // Logging in on the forest return path does not require a pre-existing health record.
 {
  const page=await browser.newPage();
  await page.route('**/api/**',route=>{const url=route.request().url();return route.fulfill({status:url.endsWith('/auth/login')||url.endsWith('/users/me')?200:url.endsWith('/token/refresh')?401:503,contentType:'application/json',body:url.endsWith('/users/me')?' {"id":99999,"name":"검증 사용자"}':'{"access_token":"synthetic-account"}'});});
  await page.goto(origin+'/service?auth=login&returnTo=forest');await page.locator('#login-email').fill('synthetic@example.test');await page.locator('#login-password').fill('Synthetic-test-only1!');await page.locator('#login-form button[type="submit"]').click();
  await page.waitForURL('**/forest');await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});assert.equal(await page.evaluate(()=>Boolean(GandangAuthSession.read())),true);authCount++;await page.close();
 }
 // The signup form completes account setup and returns directly to the forest.
 {
  const page=await browser.newPage();const calls=[];
  await page.route('**/api/**',route=>{const url=route.request().url();calls.push({url,method:route.request().method()});return route.fulfill({status:url.endsWith('/token/refresh')?401:200,contentType:'application/json',body:url.endsWith('/auth/signup')?'{"user_id":99999}':url.includes('/auth/')?'{"access_token":"synthetic-account"}':url.endsWith('/users/me')?'{"id":99999,"name":"검증 사용자"}':'{}'});});
  await page.goto(origin+'/service?auth=signup&returnTo=forest');
  await page.locator('#signup-nickname').fill('검증 사용자');await page.locator('#email').fill('signup@example.test');await page.locator('#password').fill('Synthetic-test-only1!');await page.locator('#signup-birth-date').fill('1990-01-01');await page.locator('#personal-consent').check();await page.locator('#health-consent').check();
  await page.locator('#signup-form button[type="submit"]').click();await page.waitForURL('**/forest');await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});
  assert.ok(calls.some(c=>c.url.endsWith('/auth/signup')&&c.method==='POST'));assert.ok(calls.some(c=>c.url.endsWith('/consents')&&c.method==='POST'));assert.equal(calls.some(c=>c.url.includes('/health-checkups')),false);authCount++;await page.close();
 }
 // The moved upload control still enforces consent and previews before applying.
 for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage({viewport:{width:411,height:950}});let uploads=0,patches=0;
  await page.route('**/api/**',route=>{const r=route.request(),uploaded=r.url().includes('/ocr-drafts/from-image');if(uploaded){uploads++;assert.ok(r.postDataBuffer().toString().includes('external_provider_consent'));}if(r.method()==='PATCH')patches++;return route.fulfill({status:uploaded?201:503,contentType:'application/json',body:uploaded?'{"draft_id":"synthetic-upload","extracted_fields":{"height_cm":171.2,"weight_kg":75,"systolic_bp":128}}':'{}'});});
  await page.goto(origin+'/static/'+entry+'?intro=replay');await page.waitForFunction(()=>typeof state!=='undefined');await page.evaluate(()=>{state.token='synthetic-account';state.accountRecovery=null;showStep(4,{recordHistory:false});showHealthInputPanel('metrics');document.getElementById('health-ocr-entry').open=true;document.getElementById('height').value='160';});
  await page.locator('#upload-checkup-image').click();assert.equal(uploads,0);assert.ok((await page.locator('#message').innerText()).includes('동의'));
  await page.locator('#ocr-external-provider-consent').check();
  await page.locator('#checkup-image-input').setInputFiles({name:'synthetic-checkup.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jMZkAAAAASUVORK5CYII=','base64')});
  await page.locator('#ocr-confirm-form').waitFor({state:'visible'});assert.equal(await page.locator('#height').inputValue(),'160');await page.locator('#ocr-confirm-form button[type="submit"]').click();assert.equal(await page.locator('#height').inputValue(),'171.2');assert.equal(uploads,1);assert.equal(patches,0);ocrCount++;await page.close();
 }
 for(const entry of ['index.html','intro-retro.html']) for(const width of [320,411,720,1280]) {
  const page=await browser.newPage({viewport:{width,height:950}});const writes=[];page.on('pageerror',e=>console.log('PAGE ERROR',entry,width,e.stack));
  await page.route('**/api/**',route=>{if(['PATCH','POST'].includes(route.request().method()))writes.push(route.request().url());return route.fulfill({status:503,contentType:'application/json',body:'{}'});});
  await page.goto(origin+'/static/'+entry+'?intro=replay');await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-layout';state.accountRecovery=null;showStep(4,{recordHistory:false});showHealthInputPanel('metrics');});
  await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
  assert.equal(await page.locator('#health-ocr-panel').count(),1);
  assert.equal(await page.locator('#workspace-panel-tools #ocr-confirm-form').count(),0);
  assert.equal(await page.locator('#health-form #ocr-confirm-form').count(),0);
  for(const large of [false,true]) for(const existing of [false,true]) {
   await page.evaluate(({large,existing})=>{
    document.body.classList.toggle('large-text',large);state.checkupId=existing?'synthetic-existing':null;
    document.getElementById('height').value='160';document.getElementById('weight').value='67.5';document.getElementById('diastolic').value='80';
    showOcrPreview({draft_id:'synthetic-ocr',extracted_fields:{height_cm:168.2,weight_kg:72.4,waist_cm:86,systolic_bp:132,fasting_glucose_mg_dl:108}},'합성 검증 예시');
   },{large,existing});
   assert.equal(await page.locator('#height').inputValue(),'160');
   const layout=await page.locator('#health-ocr-panel').evaluate(panel=>[panel,...panel.querySelectorAll('.health-tool-card,button,input:not(.sr-only),.check-card>span')].filter(el=>el.getClientRects().length).every(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1&&el.scrollWidth<=el.clientWidth+2;}));
   assert.ok(layout,JSON.stringify({entry,width,large,existing}));
   await page.locator('#ocr-confirm-form button[type="submit"]').click();
   assert.equal(await page.locator('#height').inputValue(),'168.2',JSON.stringify({entry,width,large,existing,diagnostic:await page.evaluate(()=>({message:document.getElementById('message').textContent,invalid:[...document.querySelectorAll('#ocr-confirm-form input')].filter(i=>!i.checkValidity()).map(i=>({id:i.id,message:i.validationMessage,value:i.value,required:i.required}))}))}));assert.equal(await page.locator('#weight').inputValue(),'72.4');assert.equal(await page.locator('#diastolic').inputValue(),'80');
   assert.equal(await page.evaluate(()=>state.healthDraftDirty),true);assert.equal(await page.locator('#ocr-confirm-form').isVisible(),false);
   assert.equal(writes.length,0,'OCR confirmation must not modify existing server records');ocrCount++;
  }
  if(width===411) {await page.evaluate(()=>{document.body.classList.remove('large-text');document.getElementById('message').hidden=true;});await page.locator('#health-ocr-panel').screenshot({path:'outputs/mobile/forest-login-ocr/ocr-'+entry+'.png'});}
  await page.close();
 }
 console.log('PASS authenticated forest entry:',authCount,'flows; OCR preview and input-only apply:',ocrCount,'states');
} finally {await browser.close();}
