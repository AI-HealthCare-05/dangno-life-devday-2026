import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
let count=0;
try {
 for(const [width,height] of [[320,740],[411,808],[720,1256],[960,411],[1280,900]]) {
  for(const signedIn of [false,true]) {
   const page=await browser.newPage({viewport:{width,height}});
   const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
   await page.goto('http://127.0.0.1:8000/static/intro-retro.html?intro=replay');
   await page.waitForFunction(()=>typeof state!=='undefined');
   await page.evaluate(signedIn=>{state.token=signedIn?'synthetic-session':null;showStep(1,{recordHistory:false});},signedIn);
   for(const large of [false,true]) {
    await page.evaluate(large=>document.body.classList.toggle('large-text',large),large);
    for(const position of ['opening','greeting','disk','guide','health','results','challenge','report','forest','closing','reverse']) {
     await page.evaluate(position=>{
      const hero=document.querySelector('.retro-intro');
      const target={opening:0,greeting:140,disk:Math.max(180,(hero.offsetHeight-innerHeight)*.5),reverse:0}[position];
      const scene={guide:'story-orbit',health:'story-health',results:'story-results',challenge:'story-challenge',report:'story-report',forest:'story-forest',closing:'.story-closing'}[position];
      const y=target??(scrollY+(scene.startsWith('.')?document.querySelector(scene):document.getElementById(scene)).getBoundingClientRect().top);
      scrollTo({top:y,behavior:'instant'});
     },position);
     await page.waitForTimeout(120);
     const geometry=await page.evaluate(()=>{
      const header=document.querySelector('.topbar'),h=header.getBoundingClientRect();
      const controls=[...header.querySelectorAll('#sidebar-login,#sidebar-signup,#font-toggle,#header-my-page-toggle,#header-forest-entry,.workspace-top-nav')]
       .filter(el=>el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden')
       .map(el=>{const r=el.getBoundingClientRect();return {id:el.id||el.dataset.topWorkspace||el.dataset.topStep,fits:r.left>=h.left-1&&r.right<=h.right+1&&r.top>=h.top-1&&r.bottom<=h.bottom+1};});
      return {compact:header.classList.contains('retro-nav-compact'),headerFits:h.left>=-1&&h.right<=innerWidth+1,noOverflow:header.scrollWidth<=header.clientWidth+1,controls};
     });
     assert.ok(geometry.headerFits&&geometry.noOverflow&&geometry.controls.every(c=>c.fits),JSON.stringify({width,height,signedIn,large,position,geometry}));
     if(position==='greeting')assert.ok(geometry.compact);
     if(position==='reverse')assert.equal(geometry.compact,false);
     if(width<=760&&['forest','closing'].includes(position)) {
      const contentClear=await page.evaluate(position=>{
       const header=document.querySelector('.topbar').getBoundingClientRect();
       const section=document.querySelector(position==='forest'?'#story-forest':'.story-closing');
       return parseFloat(getComputedStyle(section).paddingTop)>=header.bottom+27;
      },position);
      assert.ok(contentClear,JSON.stringify({width,height,signedIn,large,position,reason:'Ending scene reserves the measured header'}));
     }
     count++;
    }
   }
   assert.deepEqual(errors,[]);await page.close();
  }
 }
 console.log('PASS intro scroll header and forward/reverse scenes:',count,'states');
} finally {await browser.close();}
