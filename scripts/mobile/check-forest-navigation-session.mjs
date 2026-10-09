import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const origin='http://127.0.0.1:8000';let flows=0;
try {
 for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage();let cookieCalls=0,authenticatedCalls=0;
  await page.route('**/api/**',async route=>{
   const r=route.request(),url=r.url();
   if(url.endsWith('/token/refresh')){cookieCalls++;return route.fulfill({status:401,body:'{}'});}
   if(url.endsWith('/users/me')){assert.equal((await r.allHeaders()).authorization,'Bearer synthetic-valid');authenticatedCalls++;return route.fulfill({status:200,contentType:'application/json',body:'{"id":99999,"name":"합성 검증 계정","birth_date":"1990-01-01","gender":"female"}'});}
   if(url.endsWith('/auth/logout'))return route.fulfill({status:200,body:'{}'});
   if(url.includes('/challenge-v2/')&&!url.endsWith('/capabilities'))assert.equal(r.headers().authorization,'Bearer synthetic-valid');
   return route.fulfill({status:503,body:'{}'});
  });
  await page.goto(origin+'/static/'+entry+'?intro=replay&auth=login');
  await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-valid';state.userProfile={id:99999,name:'합성 검증 계정'};syncTopNavigation();});
  assert.equal(await page.locator('#header-forest-entry').getAttribute('href'),'/forest');
  await page.locator('#header-forest-entry').click();
  await page.waitForURL('**/forest');
  await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});
  assert.equal(await page.evaluate(()=>GandangAuthSession.read()),'synthetic-valid');
  assert.equal(await page.evaluate(()=>ForestProfile.loadName()),'합성 검증 계정');
  assert.equal(cookieCalls,0,'A valid bearer must not be replaced by a missing refresh cookie');
  await page.goto(origin+'/service?workspace=home');
  await page.waitForFunction(()=>typeof state!=='undefined'&&Boolean(state.userProfile));
  assert.equal(await page.evaluate(()=>state.token),'synthetic-valid');
  assert.equal(cookieCalls,0);assert.ok(authenticatedCalls>=3);
  await page.evaluate(()=>document.getElementById('account-logout').click());
  await page.waitForFunction(()=>!state.token&&!GandangAuthSession.read());
  await page.locator('#header-forest-entry').click();
  await page.waitForURL('**/service?auth=login&returnTo=forest');
  await page.locator('#login-form').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>GandangAuthSession.read()),null);
  flows++;await page.close();
 }
 // Guests use the visible shortcut, submit the actual login form, and enter the real game without a cookie.
 for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage();
  await page.route('**/api/**',route=>{
   const url=route.request().url();
   return route.fulfill({status:url.endsWith('/auth/login')||url.endsWith('/users/me')?200:url.endsWith('/token/refresh')?401:503,contentType:'application/json',body:url.endsWith('/users/me')?'{"id":99999,"name":"합성 검증 계정"}':'{"access_token":"synthetic-valid"}'});
  });
  await page.goto(origin+'/static/'+entry+'?intro=replay&auth=login');await page.waitForFunction(()=>typeof state!=='undefined');
  await page.locator('#header-forest-entry').click();await page.waitForURL('**/service?auth=login&returnTo=forest');
  await page.locator('#login-email').fill('synthetic@example.test');await page.locator('#login-password').fill('Synthetic-test-only1!');await page.locator('#login-form button[type="submit"]').click();
  await page.waitForURL('**/forest');await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});
  assert.equal(await page.evaluate(()=>GandangAuthSession.read()),'synthetic-valid');assert.equal(await page.evaluate(()=>ForestProfile.loadName()),'합성 검증 계정');
  flows++;await page.close();
 }
 // Stored tokens never authorize entry on their own, including expired and revoked accounts.
 for(const expired of [false,true]) {
  const page=await browser.newPage();let games=0;
  await page.addInitScript(expired=>sessionStorage.setItem('gandang-auth-session-v1',JSON.stringify({token:'synthetic-revoked',expiresAt:Date.now()+(expired?-1000:60000)})),expired);
  page.on('request',r=>{if(/forest-game\.js/.test(r.url()))games++;});
  await page.route('**/api/**',r=>r.fulfill({status:401,body:'{}'}));
  await page.goto(origin+'/forest');await page.waitForURL('**/service?auth=login&returnTo=forest');
  assert.equal(games,0);assert.equal(await page.evaluate(()=>GandangAuthSession.read()),null);flows++;await page.close();
 }
 // A transient outage keeps the valid local transport and blocks the engine until retry.
 {
  const page=await browser.newPage();let recovered=false,games=0;
  await page.addInitScript(()=>sessionStorage.setItem('gandang-auth-session-v1',JSON.stringify({token:'synthetic-valid',expiresAt:Date.now()+60000})));
  page.on('request',r=>{if(/forest-game\.js/.test(r.url()))games++;});
  await page.route('**/api/**',r=>r.fulfill({status:r.request().url().endsWith('/users/me')&&recovered?200:503,contentType:'application/json',body:'{"id":99999,"name":"합성 검증 계정"}'}));
  await page.goto(origin+'/forest');await page.locator('#forest-access-retry').waitFor({state:'visible'});
  assert.equal(games,0);assert.equal(await page.evaluate(()=>GandangAuthSession.read()),'synthetic-valid');
  recovered=true;await page.locator('#forest-access-retry').click();await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'),{},{timeout:60000});
  assert.equal(games,1);flows++;await page.close();
 }
 console.log('PASS cookie-free forest, profile, home return, logout, expired/revoked token and outage retry:',flows,'flows');
} finally {await browser.close();}
