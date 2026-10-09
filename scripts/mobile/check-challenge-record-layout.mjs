import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
try {
 await mkdir('outputs/mobile/challenge-record-layout',{recursive:true});
 for(const width of [390,720,1280]) {
  const page=await browser.newPage({viewport:{width,height:1256}});
  await page.route('**/api/**',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
  await page.goto('http://127.0.0.1:8000/static/index.html?preview=results');
  await page.waitForFunction(()=>state.step===6);
  await page.evaluate(()=>{
    renderCycle(createLocalDemoCycle(fallbackChallenges.slice(0,3).map(item=>item.challenge_id)));
    showWorkspace('challenge',{moveFocus:false});showStep(8);
    document.getElementById('message').style.setProperty('display','none','important');
  });
  await page.locator('.screen.active').evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished.catch(()=>{})));});
  const list=page.locator('#daily-log-list'),cards=await list.locator('.daily-record-card').all();
  assert.equal(cards.length,3);
  const listBox=await list.boundingBox(),boxes=await Promise.all(cards.map(card=>card.boundingBox()));
  for(let i=0;i<boxes.length;i++){
   const box=boxes[i];assert.ok(Math.abs(box.x-listBox.x)<1 && Math.abs(box.width-listBox.width)<1);
   if(i)assert.ok(box.y>=boxes[i-1].y+boxes[i-1].height+15);
   for(const text of await cards[i].locator('.daily-record-copy strong,.daily-record-copy small').all()){
    const b=await text.boundingBox();assert.ok(b.x>=box.x && b.x+b.width<=box.x+box.width+1);
   }
  }
  await list.screenshot({path:`outputs/mobile/challenge-record-layout/vertical-${width}.png`});
  await cards[0].click();assert.equal(await page.locator('#record-modal').isVisible(),true);

  await page.evaluate(()=>document.getElementById('message').style.removeProperty('display'));
  await page.locator('#confirm-simple-record').click();
  await page.waitForFunction(()=>!document.getElementById('message').hidden && document.getElementById('message').dataset.kind==='success');
  async function checkCenter(){
    const box=await page.locator('#message').boundingBox();
    const viewport=await page.evaluate(()=>({width:document.documentElement.clientWidth,height:window.innerHeight}));
    assert.ok(Math.abs(box.x+box.width/2-viewport.width/2)<2,'Completion message centered horizontally');
    assert.ok(Math.abs(box.y+box.height/2-viewport.height/2)<2,'Completion message centered vertically');
    assert.ok(box.width<=width-30);
  }
  await checkCenter();
  await page.evaluate(()=>{document.getElementById('challenge-reward-dialog').showModal();showMessage('오늘 챌린지 기록을 완료했어요.','success');});
  await checkCenter();
  await page.screenshot({path:`outputs/mobile/challenge-record-layout/centered-reward-${width}.png`});
  await page.evaluate(()=>{document.getElementById('challenge-reward-dialog').close();clearMessage();state.token='synthetic-session';});
  let writes=0,fail=false;
  await page.route('**/user-challenges/*/barriers',async route=>{
    writes++;await new Promise(resolve=>setTimeout(resolve,100));
    await route.fulfill({status:fail?500:200,contentType:'application/json',body:JSON.stringify(fail?{detail:'기록을 저장하지 못했습니다.'}:{suggestion:'목표를 더 작게 나누세요.'})});
  });
  await page.evaluate(()=>{const form=document.getElementById('barrier-form');form.requestSubmit();form.requestSubmit();});
  await page.waitForFunction(()=>document.getElementById('message').dataset.kind==='success' && !document.getElementById('message').hidden);
  assert.equal(writes,1,'Duplicate submits send only one save');
  assert.match(await page.locator('#message').textContent(),/실천하지 못한 이유를 기록했어요/);
  assert.equal(await page.locator('#barrier-suggestion').isVisible(),true);
  assert.equal(await page.locator('#barrier-suggestion-text').textContent(),'목표를 더 작게 나누세요.');
  await checkCenter();
  await page.screenshot({path:`outputs/mobile/challenge-record-layout/centered-barrier-${width}.png`});
  fail=true;
  await page.locator('#barrier-form button[type="submit"]').click();
  await page.waitForFunction(()=>document.getElementById('message').dataset.kind==='error');
  assert.match(await page.locator('#message').textContent(),/저장하지 못/);
  assert.equal(await page.locator('#barrier-form').getAttribute('aria-busy'),null);
  console.log(`PASS ${width}px: vertical cards, centered completion/reward notices, barrier save/duplicate/failure feedback`);
  await page.close();
 }
}finally{await browser.close();}
