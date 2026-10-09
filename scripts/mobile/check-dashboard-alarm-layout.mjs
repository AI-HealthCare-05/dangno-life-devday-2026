import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/alarm-layout',{recursive:true});let count=0;
try {
 for(const width of [320,411,720,1280]) for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage({viewport:{width,height:808}});
  await page.route('**/api/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/'+entry+'?intro=replay');
  await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-layout';state.accountRecovery=null;showStep(8,{recordHistory:false});});
  await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
  for(const workspace of ['home','challenge','report','together']) for(const large of [false,true]) {
   await page.evaluate(({workspace,large})=>{document.body.classList.toggle('large-text',large);showWorkspace(workspace,{moveFocus:false});document.querySelector('.profile-menu').open=false;},{workspace,large});
   if(workspace==='tools'&&entry==='index.html') {assert.equal(await page.locator('.dashboard-hero').isVisible(),false);count++;continue;}
   const result=await page.locator('.dashboard-hero').evaluate(hero=>{
    const rect=el=>el.getBoundingClientRect();const h=rect(hero),style=getComputedStyle(hero);
    const bell=rect(hero.querySelector('summary')),eyebrow=rect(document.querySelector('#dashboard-eyebrow'));
    const title=rect(document.querySelector('.dashboard-title-row')),lead=rect(document.querySelector('#dashboard-lead'));
    const zoom=Number(getComputedStyle(document.body).zoom)||1;
    const borderTop=parseFloat(style.borderTopWidth)*zoom,borderRight=parseFloat(style.borderRightWidth)*zoom,borderBottom=parseFloat(style.borderBottomWidth)*zoom;
    const pdf=hero.querySelector('.report-pdf-hero-control');const bottom=pdf?.getClientRects().length?rect(pdf).bottom:lead.bottom;
    return {topRight:Math.abs(bell.top-h.top-borderTop-parseFloat(style.paddingTop)*zoom)<2&&Math.abs(h.right-bell.right-borderRight-parseFloat(style.paddingRight)*zoom)<2,
     textSeparate:eyebrow.right<=bell.left+1&&title.top>=bell.bottom&&lead.top>=title.bottom,
     compactBottom:Math.abs(h.bottom-bottom-borderBottom-parseFloat(style.paddingBottom)*zoom)<2,
     fits:h.left>=-1&&h.right<=innerWidth+1, width:innerWidth, heroLeft:h.left, heroRight:h.right, documentWidth:document.documentElement.scrollWidth};
   });
   assert.ok(result.topRight&&result.textSeparate&&result.compactBottom&&result.fits,JSON.stringify({width,entry,workspace,large,result}));
   const summary=page.locator('.dashboard-hero summary');await summary.focus();await page.keyboard.press('Enter');
   assert.equal(await page.locator('.profile-menu').evaluate(el=>el.open),true);
   const menu=await page.locator('.profile-menu-panel').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;});assert.ok(menu);
   assert.equal(await page.locator('#profile-notification-settings').innerText(),'웹 알림 설정');
   await page.keyboard.press('Enter');count++;
   if(width===411&&workspace==='home'&&!large) {
    await page.evaluate(()=>{document.getElementById('message').hidden=true;document.querySelector('.dashboard-hero').scrollIntoView({block:'center',behavior:'instant'});});
    await page.locator('.dashboard-hero').screenshot({path:'outputs/mobile/alarm-layout/'+entry+'-411.png'});
   }
  }
  await page.close();
 }
 console.log('PASS alarm placement, spacing, keyboard menu and viewport:',count,'states');
} finally {await browser.close();}
