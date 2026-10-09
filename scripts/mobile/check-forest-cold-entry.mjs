import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/forest',{recursive:true});
try {
 for (const width of [390,720]) {
  for (const mode of ['fallback','missing-background','phaser']) {
   const page = await browser.newPage({viewport:{width,height:1256}});
   const errors=[];page.on('pageerror', e=>errors.push(e.message));
   await page.addInitScript(()=>{
    window.firstEntryPaint={retiredVehicle:0,fieldImages:0,rects:0};
    const fill=CanvasRenderingContext2D.prototype.fillRect;
    CanvasRenderingContext2D.prototype.fillRect=function(...args){
     if(this.canvas.id==='forest-canvas') {
      window.firstEntryPaint.rects++;
      if(['#c84e30','#f58e38','#1f3434'].includes(this.fillStyle)) window.firstEntryPaint.retiredVehicle++;
     }
     return fill.apply(this,args);
    };
    const image=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(source,...args){
     if(this.canvas.id==='forest-canvas' && source.src?.includes('carrot-forest-world-v9.png')) window.firstEntryPaint.fieldImages++;
     return image.call(this,source,...args);
    };
   });
   await page.route('**/api/**',r=>r.fulfill({status:503,contentType:'application/json',body:'{}'}));
   if(mode!=='phaser') await page.route('**/forest-phaser.js*',r=>r.fulfill({contentType:'text/javascript',body:''}));
   if(mode==='missing-background') await page.route('**/carrot-forest-world-v9.png*',r=>r.abort());
   await page.goto('http://127.0.0.1:8000/static/forest.html?demo=1');
   await page.waitForFunction(()=>document.documentElement.classList.contains('forest-script-ready'));
   if(mode!=='missing-background') await page.waitForFunction(()=>firstEntryPaint.fieldImages>0);
   else await page.waitForFunction(()=>firstEntryPaint.rects>0);
   if(mode==='phaser') await page.waitForFunction(()=>document.documentElement.classList.contains('phaser-world-ready'));
   const paint=await page.evaluate(()=>firstEntryPaint);
   assert.equal(paint.retiredVehicle,0,JSON.stringify({width,mode,paint}));
   assert.deepEqual(errors,[]);
   if(mode!=='missing-background') await page.screenshot({path:`outputs/mobile/forest/clean-entry-${mode}-${width}.png`});
   console.log('PASS cold entry',width,mode,JSON.stringify(paint));
   await page.close();
  }
 }
} finally {await browser.close();}
