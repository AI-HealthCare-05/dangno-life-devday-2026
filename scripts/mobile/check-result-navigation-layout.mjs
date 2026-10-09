import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/result-layout',{recursive:true});let tabCount=0,gaugeCount=0;
try {
 for(const width of [320,411,720,1280]) for(const entry of ['index.html','intro-retro.html']) {
  const page=await browser.newPage({viewport:{width,height:950}});
  await page.route('**/api/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/'+entry+'?intro=replay');
  await page.waitForFunction(()=>typeof state!=='undefined');
  await page.evaluate(()=>{state.token='synthetic-layout';state.accountRecovery=null;});
  for(const large of [false,true]) for(const step of [3,4,5,6]) {
   await page.evaluate(({large,step})=>{document.body.classList.toggle('large-text',large);showStep(step,{recordHistory:false});window.scrollTo({top:0,behavior:'instant'});},{large,step});
   await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
   if(entry==='intro-retro.html') {assert.equal(await page.locator('#onboarding-top-nav').isVisible(),false);assert.equal(await page.locator('#workspace-top-nav').isVisible(),true);tabCount++;continue;}
   const result=await page.evaluate(()=>{
    const rect=id=>document.getElementById(id).getBoundingClientRect();
    const main=rect('workspace-top-nav'),health=rect('onboarding-top-nav'),brand=rect('header-forest-entry'),bar=document.querySelector('.topbar').getBoundingClientRect();
    const overlap=(a,b)=>a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1;
    const button=document.querySelector('[data-onboarding-step].active');
    return {mainVisible:main.width>0&&main.height>0,healthVisible:health.width>0&&health.height>0,
     separated:!overlap(main,health)&&!overlap(brand,health),below:health.top>=main.bottom-1,
     healthFits:health.left>=0&&health.right<=innerWidth+1&&health.bottom<=bar.bottom,
     headerFits:document.querySelector('.topbar').scrollWidth<=document.querySelector('.topbar').clientWidth+1,
     activeStep:Number(button?.dataset.onboardingStep)};
   });
   assert.ok(result.mainVisible&&result.healthVisible&&result.separated&&result.below&&result.healthFits&&result.headerFits,JSON.stringify({width,entry,large,step,result}));
   assert.equal(result.activeStep,step===6?5:step);tabCount++;
  }
  if(entry==='index.html') for(const large of [false,true]) for(const level of ['low','moderate','high']) {
   await page.evaluate(({large,level})=>{
    document.body.classList.toggle('large-text',large);showStep(6,{recordHistory:false});
    document.getElementById('future-prediction-result').hidden=false;
    renderTwoYearRiskForecast({age_risk_forecast:{points:[{years_from_now:2,signal_level:level}]}},{canDisplayRisk:true});
    document.getElementById('message').hidden=true;
   },{large,level});
   await page.locator('.age-risk-signal-track img').evaluate(img=>img.decode());
   const result=await page.locator('.age-risk-signal-track').evaluate(track=>{
    const r=track.getBoundingClientRect(),img=track.querySelector('img'),m=img.getBoundingClientRect(),card=track.closest('#future-risk-visual').getBoundingClientRect();
    const before=getComputedStyle(track,'::before'),bodyZoom=Number(getComputedStyle(document.body).zoom)||1;
    return {ratio:r.width/r.height,roundMarker:Math.abs(m.width-m.height)<1,imageReady:img.naturalWidth>0,
     fits:r.left>=card.left&&r.right<=card.right&&m.left>=card.left&&m.right<=card.right&&m.top>=card.top&&m.bottom<=card.bottom,
     needleLengthRatio:parseFloat(before.height)*bodyZoom/r.height,cardFits:card.left>=0&&card.right<=innerWidth+1};
   });
   assert.ok(Math.abs(result.ratio-2)<.02&&result.roundMarker&&result.imageReady&&result.fits&&result.cardFits&&result.needleLengthRatio>.66&&result.needleLengthRatio<.74,JSON.stringify({width,large,level,result}));gaugeCount++;
   if(width===411&&!large&&level==='low') {
    await page.locator('.topbar').screenshot({path:'outputs/mobile/result-layout/header-411.png'});
    await page.locator('#future-risk-visual').screenshot({path:'outputs/mobile/result-layout/gauge-411.png'});
   }
  }
  await page.close();
 }
 console.log('PASS separate health tabs:',tabCount,'states; proportional risk gauge:',gaugeCount,'states');
} finally {await browser.close();}
