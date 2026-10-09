import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/health-tools',{recursive:true});let count=0;
try {
 for(const width of [320,411,720,1280]) for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage({viewport:{width,height:808}});
  await page.route('**/api/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/'+entry+'?intro=replay');
  await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-layout';state.accountRecovery=null;showStep(8,{recordHistory:false});showWorkspace('tools',{moveFocus:false});});
  await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
  for(const large of [false,true]) for(const expanded of [false,true]) {
   await page.evaluate(({large,expanded})=>{
    document.body.classList.toggle('large-text',large);
    document.querySelector('#wearable-form').closest('details').open=expanded;
   },{large,expanded});
   const result=await page.locator('#workspace-panel-tools').evaluate(panel=>{
    const cards=[...panel.querySelectorAll('.health-tool-card')];
    const elements=cards.flatMap(card=>[card,...card.querySelectorAll('.health-tool-row,.health-tool-row>div,.health-tool-actions,button,input:not(.sr-only),select,.check-card,.check-card>span')]);
    const failing=elements.filter(el=>el.getClientRects().length).map(el=>{const r=el.getBoundingClientRect();return {selector:el.id||el.className,inside:r.left>=-1&&r.right<=innerWidth+1,overflow:el.scrollWidth>el.clientWidth+2};}).filter(el=>!el.inside||el.overflow);
    return {documentFits:document.documentElement.scrollWidth<=innerWidth+1,failing};
   });
   assert.ok(result.documentFits&&result.failing.length===0,JSON.stringify({width,entry,large,expanded,result}));count++;
  }
  await page.evaluate(()=>document.getElementById('message').hidden=true);
  await page.locator('.health-tools-pending-grid').screenshot({path:'outputs/mobile/health-tools/'+entry+'-'+width+'.png'});
  await page.close();
 }
 console.log('PASS health-tool cards, upload buttons and expanded forms:',count,'states');
} finally {await browser.close();}
