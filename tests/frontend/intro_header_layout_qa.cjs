// Synthetic header-only browser QA. No accounts, health data or live API calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../../src/frontend');
const html = fs.readFileSync(path.join(root, 'intro-retro.html'), 'utf8');
const head = html.match(/<head>([\s\S]*?)<\/head>/)[1].replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '');
const header = html.match(/<header class="topbar">[\s\S]*?<\/header>/)[0];
const entry = fs.readFileSync(path.join(root, 'mobile-download-entry.js'), 'utf8');
async function main() {
  const browser = await chromium.launch({headless:true, ...(process.env.CHROME_BIN ? {executablePath:process.env.CHROME_BIN} : {})});
  try {
    const page = await browser.newPage({reducedMotion:'reduce'});
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'header-qa.test' || !url.pathname.startsWith('/static/')) return route.abort();
      const file = path.resolve(root, decodeURIComponent(url.pathname.slice('/static/'.length)));
      if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.abort();
      await route.fulfill({path:file});
    });
    let checks = 0;
    for (const mode of ['guest-web', 'guest-native', 'signed-in']) {
      for (const width of [320,360,390,412,520,640,641,760,1024,1440]) {
        for (const large of [false,true]) {
          await page.setViewportSize({width,height:900});
          await page.setContent(`<html><head><base href="http://header-qa.test/">${head}</head><body class="intro-mode">${header}<div class="retro-intro"></div></body></html>`, {waitUntil:'load'});
          await page.evaluate(({mode,large}) => {
            document.body.classList.toggle('large-text', large);
            window.Capacitor = {isNativePlatform:()=>mode==='guest-native'};
            if (mode==='signed-in') {
              document.body.classList.add('intro-authenticated');
              document.querySelector('#guest-flow-panel').hidden=true;
              document.querySelector('#header-my-page').hidden=false;
              document.querySelector('#workspace-top-nav').hidden=false;
            }
          }, {mode,large});
          await page.evaluate(entry);
          const geometry = await page.evaluate(() => {
            const selectors=['.header-brand-stack','#guest-flow-panel','.header-utilities','.intro-mobile-download'];
            const boxes=selectors.map(selector=>{
              const el=document.querySelector(selector),r=el.getBoundingClientRect();
              return {selector,x:r.x,y:r.y,right:r.right,bottom:r.bottom,visible:r.width>0&&r.height>0};
            });
            const signup=document.querySelector('#sidebar-signup').getBoundingClientRect();
            return {boxes,signup:{x:signup.x,right:signup.right,width:signup.width},guestColumn:getComputedStyle(document.querySelector("#guest-flow-panel")).gridColumnStart,width:innerWidth,scroll:document.documentElement.scrollWidth};
          });
          const label=`${mode} ${width}px large=${large}`;
          assert.ok(geometry.scroll<=width+1, `${label}: horizontal overflow`);
          const visible=geometry.boxes.filter(r=>r.visible);
          for (const r of visible) assert.ok(r.x>=-1&&r.right<=width+1, `${label}: ${r.selector} outside viewport`);
          for(let i=0;i<visible.length;i++)for(let j=i+1;j<visible.length;j++){
            const a=visible[i],b=visible[j];
            const overlap=Math.min(a.right,b.right)-Math.max(a.x,b.x)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1;
            assert.equal(overlap,false,`${label}: ${a.selector} overlaps ${b.selector}`);
          }
          const download=geometry.boxes.find(r=>r.selector==='.intro-mobile-download');
          assert.equal(download.visible,mode!=='guest-native',`${label}: download visibility`);
          if(mode==='guest-web'){
            assert.ok(Math.abs((download.x+download.right)/2-width/2)<=2,`${label}: download centered`);
            assert.ok(geometry.signup.right>width*0.7,`${label}: signup on right`);
          }
          if(mode==='guest-native') assert.equal(geometry.guestColumn, '2', `${label}: native guest column preserved`);
          if(mode==='signed-in') assert.ok(await page.locator('#header-my-page-toggle').isVisible());
          assert.equal(await page.locator('.header-forest-entry').getAttribute('href'),'/forest');
          assert.equal(await page.locator('.intro-mobile-download').getAttribute('href'),'/mobile-downloads');
          checks++;
        }
      }
    }
    console.log(`PASS ${checks} header scenarios: centered guest download, right account controls, no overlaps/overflow; native hiding and signed-in navigation preserved.`);
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
