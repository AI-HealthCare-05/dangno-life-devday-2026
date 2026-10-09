import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
await mkdir('outputs/mobile/photo-review-ui',{recursive:true});
try {
 for(const width of [390,720,1280]){
  const page=await browser.newPage({viewport:{width,height:1256}});
  await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/index.html?preview=meal-photo');
  await page.waitForFunction(()=>typeof state !== 'undefined' && state.recordTarget?.item?.verification_type===1);
  await page.locator('[data-demo-name="demo-pass.png"]').click();
  await page.waitForFunction(()=>document.getElementById('v3-photo-file').files.length===1);
  await page.locator('input[name="v3-photo-value"][value="1"]').evaluate(el=>el.closest("label").click());
  await page.evaluate(()=>{
   state.token='synthetic-ui-session';
   api=async()=>{throw Object.assign(new Error('서버의 보안 설정이 사진 분석 프로그램 실행을 차단하고 있어요. 사진 문제가 아니며, 서버 실행 환경을 복구해야 합니다. 기록은 완료되지 않았어요.'),{status:503});};
  });
  await page.locator('#confirm-photo-record').click();
  await page.waitForFunction(()=>!document.getElementById('photo-state-fail').hidden);
  assert.equal(await page.locator('#photo-fail-title').textContent(),'사진 검토를 진행할 수 없어요');
  const geometry=await page.locator('#photo-state-fail').evaluate(el=>{
   const box=el.getBoundingClientRect();return {left:box.left,right:box.right,width:document.documentElement.clientWidth,overflow:el.scrollWidth>el.clientWidth};
  });
  assert.ok(geometry.left>=0 && geometry.right<=geometry.width+1 && !geometry.overflow);
  await page.locator('#photo-state-fail').screenshot({path:`outputs/mobile/photo-review-ui/failure-${width}.png`});
  assert.equal(await page.evaluate(()=>state.dailyCompleted.size),0);
  await page.close();console.log('PASS photo review error layout',width);
 }
} finally {await browser.close();}
