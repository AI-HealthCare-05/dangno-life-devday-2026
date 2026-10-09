import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/today-card',{recursive:true});
let count=0;
try {
 for(const width of [320,390,720,1280]) for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage({viewport:{width,height:1256}});
  await page.route('**/api/**',r=>r.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/'+entry+'?intro=replay');
  await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-layout';state.accountRecovery=null;showStep(8,{recordHistory:false});showWorkspace('home',{moveFocus:false});});
  for(const large of [false,true]) for(const status of ['none','loading','partial','complete']) {
   await page.evaluate(({large,status})=>{
    document.body.classList.toggle('large-text',large);
    state.cycle=status==='none'?null:{status:'active',user_challenges:[1,2,3].map(id=>({user_challenge_id:id}))};
    state.dailyRecordsStatus=status==='loading'?'loading':'ready';
    state.dailyCompleted=new Set(status==='complete'?['1','2','3']:status==='partial'?['1','2']:[]);
    renderTodayTaskStatus();
   },{large,status});
   await page.locator('.today-card-mascot').evaluate(img=>img.decode());
   const layout=await page.locator('.today-card').evaluate(card=>{
    const rect=el=>el.getBoundingClientRect(),b=rect(card),img=rect(card.querySelector('img')),title=rect(card.querySelector('h3')),desc=rect(card.querySelector('#today-task-description'));
    const buttons=[...card.querySelectorAll('button')].filter(el=>!el.hidden),last=rect(buttons.at(-1));
    return {upper:img.bottom<=desc.top+1,noOverlap:img.left>=title.right-1,padding:b.bottom-last.bottom,fits:img.right<=b.right&&card.scrollWidth<=card.clientWidth+1};
   });
   assert.ok(layout.upper&&layout.noOverlap&&layout.fits,JSON.stringify({width,entry,large,status,layout}));
   assert.ok(layout.padding>=0&&layout.padding<40,JSON.stringify(layout));count++;
   if(status==='partial'&&!large) await page.locator('.today-card').screenshot({path:`outputs/mobile/today-card/${entry.split('.')[0]}-${width}.png`});
  }
  await page.close();
 }
 console.log('PASS today card upper mascot and compact lower spacing',count,'states');
} finally {await browser.close();}
