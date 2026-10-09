import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/forest-header-entry',{recursive:true});
let count=0;
try {
 for(const width of [320,390,720,1280]) {
  for(const entry of ['index.html?preview=results','intro-retro.html?intro=replay']){
   const page=await browser.newPage({viewport:{width,height:1256}});
   await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:route.request().url().includes('/token/refresh')?'{"access_token":"synthetic-account"}':route.request().url().endsWith('/users/me')?'{"id":99999,"name":"검증 사용자"}':'{}'}));
   await page.goto('http://127.0.0.1:8000/static/'+entry);
   await page.waitForFunction(()=>typeof state!=='undefined' && Boolean(document.getElementById('header-forest-entry')));
   const image=page.locator('#header-forest-entry img');
   await image.evaluate(img=>img.decode());
   const imgSize=await image.evaluate(img=>[img.naturalWidth,img.naturalHeight]);
   assert.deepEqual(imgSize,[2055,765]);
   assert.ok((await image.getAttribute("src")).endsWith("carrot-forest-wordmark-a.png"));
   assert.equal(await page.locator('#header-forest-entry').innerText(), '');
   for(const large of [false,true]) {
    await page.evaluate(large=>document.body.classList.toggle('large-text',large),large);
    for(const step of (entry.startsWith('index')?[2,3,4,5,6,7,8]:[1,2])){
     await page.evaluate(step=>{
      state.token=step===2?null:'synthetic-session';
      state.accountRecovery=null;
      showStep(step,{recordHistory:false});
     },step);
     await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
     const result=await page.evaluate(()=>{
      const rect=id=>document.getElementById(id).getBoundingClientRect();
      const link=rect('header-forest-entry'),font=rect('font-toggle'),my=rect('header-my-page-toggle'),brand=rect('brand-home');
      const accountVisible=!document.getElementById('header-my-page').hidden;
      return {visible:link.width>0&&link.height>0,fontVisible:font.width>0&&font.height>0,below:link.top>=brand.bottom-1 && Math.abs(link.left-brand.left)<1,widthRatio:accountVisible?link.width/my.width:2,heightRatio:accountVisible?link.height/my.height:2,fits:link.left>=-1&&link.right<=innerWidth+1,headerFits:document.querySelector(".topbar").scrollWidth<=document.querySelector(".topbar").clientWidth+1,authAbove:accountVisible||rect('guest-flow-panel').top<link.top,href:document.getElementById('header-forest-entry').getAttribute('href')};
     });
     assert.ok(result.visible&&result.fontVisible&&result.below&&result.fits&&result.headerFits&&result.authAbove,JSON.stringify({width,entry,large,step,result}));
     assert.ok(Math.abs(result.widthRatio-2)<.02&&Math.abs(result.heightRatio-2)<.02);
     assert.equal(result.href,(step===2?'/service?auth=login&returnTo=forest':'/forest'));count++;
    }
   }
   await page.evaluate(()=>document.body.classList.remove('large-text'));
   await page.locator('.topbar').screenshot({path:`outputs/mobile/forest-header-entry/header-${entry.split('.')[0]}-${width}.png`});
   await page.locator('#header-forest-entry').click();
   await page.waitForURL(entry.startsWith('index')?'**/forest':'**/service?auth=login&returnTo=forest');
   assert.equal(await page.locator('dialog[open]').count(),0);
   await page.close();
  }
 }
 console.log('PASS shared forest shortcut layouts',count,'states; direct /forest links');
} finally {await browser.close();}
