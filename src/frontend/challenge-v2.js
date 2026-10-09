/* Shared authenticated plan. Never synthesizes AI approval. Authentication is shared within this app tab. */
(() => {
  "use strict";
  const root = document.querySelector("[data-challenge-v2]");
  if (!root) return;
  const forestView=root.getAttribute?.("data-challenge-v2-view")==="forest";
  const homeParent=root.parentElement;
  const esc = x => String(x ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const proofLabel = {T1:"담당자가 사진 확인",T2:"사진과 기록 제출",T3:"직접 기록"};
  const levelLabel = {E:"쉬움",M:"보통",H:"도전"};
  const statusLabel = {assigned:"기록 준비",in_progress:"진행 중",submitted:"검토 대기",completed:"완료",not_required:"기록 제출 완료",pending:"검토 대기",passed:"사진 조건 확인",needs_retry:"재제출 필요",inconclusive:"판단 어려움"};
  const reasonLabel = {real_visual_review_unavailable:"지금은 사진 확인 대신 직접 기록하는 챌린지를 드려요.",photo_consent_or_accessibility:"사진 없이도 할 수 있는 챌린지로 바꿨어요.",difficulty_safety_or_preference_limit:"몸 상태와 선택에 맞춰 난이도를 조정했어요.",proof_mix_safety_accessibility_or_weekly_limit:"이번 주에 무리 없이 할 수 있는 챌린지로 골랐어요.",replacement_accessibility:"사진 없이 기록하기",replacement_safety:"몸 상태에 맞게 바꾸기",replacement_too_hard:"난이도 낮추기",replacement_preference:"다른 활동 선택"};
  const domainView = {
    routine:{label:"음료",message:"당근 밭에 물을 주었습니다.",image:"/static/assets/challenge-water-team-v171.webp?v=20260908-1"},
    diet:{label:"식단",message:"당근 밭에 거름을 주었습니다.",image:"/static/assets/challenge-compost-team-v171.webp?v=20260908-1"},
    activity:{label:"운동",message:"당근 밭에 잡초를 제거했습니다.",image:"/static/assets/challenge-weeding-team-v171.webp?v=20260908-1"},
  };
  const mvpStorageKey="gandang.challenge-v2.mvp-completions.v1";
  const mvpWaterCupStorageKey="gandang.challenge-v2.water-cups.v1";
  const mvpCycleStorageKey="gandang.challenge-v2.daily-cycle.v1";
  const setupUrl = "/?returnTo=forest-challenges";
  let token=null, plan=null, busy=false, needsSetup=false, connectionFailed=false, settingsOpen=location.hash==="#daily-settings";
  let mvpCompletions=readMvpCompletions();
  let mvpWaterCups=readMvpWaterCups();
  let mvpCycles=readMvpCycles();
  const channel=typeof BroadcastChannel==="function"?new BroadcastChannel("challenge-v2-refresh"):null;
  window.ForestChallengeV2={enabled:false,plan:null};
  function readMvpCompletions(){try{return JSON.parse(window.localStorage?.getItem(mvpStorageKey)||"{}")||{};}catch{return {};}}
  function readMvpWaterCups(){try{return JSON.parse(window.localStorage?.getItem(mvpWaterCupStorageKey)||"{}")||{};}catch{return {};}}
  function readMvpCycles(){try{return JSON.parse(window.localStorage?.getItem(mvpCycleStorageKey)||"{}")||{};}catch{return {};}}
  function planDayKey(){return String(plan?.day_id||plan?.starts_on||new Date().toISOString().slice(0,10));}
  function currentCycle(){return Math.max(0,Math.trunc(Number(mvpCycles[planDayKey()])||0));}
  function completionKey(item){return `${planDayKey()}:cycle-${currentCycle()}:${item.id}`;}
  function legacyCompletionKey(item){return `${planDayKey()}:${item.id}`;}
  function waterCupKey(item){return `${completionKey(item)}:cups`;}
  function waterGoal(item){
    const goal=item?.goal||{}, cups=Math.max(0,Math.trunc(Number(goal.water_goal_cups)||0));
    const cupMl=Math.max(1,Math.trunc(Number(goal.water_cup_ml)||200));
    return goal.family_id==="H02"&&goal.water_mission_version==="cup-v1"&&goal.water_goal_status==="confirmed"&&cups>0?{cups,cupMl}:null;
  }
  function waterCupProgress(item){
    const water=waterGoal(item), saved=mvpWaterCups[waterCupKey(item)]||[];
    return new Set((Array.isArray(saved)?saved:[]).map(Number).filter(index=>Number.isInteger(index)&&index>=1&&index<=water?.cups));
  }
  function saveWaterCupProgress(item,progress){
    mvpWaterCups={...mvpWaterCups,[waterCupKey(item)]:[...progress].sort((a,b)=>a-b)};
    try{window.localStorage?.setItem(mvpWaterCupStorageKey,JSON.stringify(mvpWaterCups));}catch{}
    const water=waterGoal(item);
    if(water)window.dispatchEvent(new CustomEvent("forest-water-cup-progress",{detail:{assignmentId:item.id,completionKey:completionKey(item),checked:progress.size,total:water.cups,cupMl:water.cupMl,complete:progress.size>=water.cups}}));
  }
  function completionRecord(item){return mvpCompletions[completionKey(item)]||(currentCycle()===0?mvpCompletions[legacyCompletionKey(item)]:null);}
  function isMvpCompleted(item){return Boolean(completionRecord(item));}
  function isCompleted(item){return Boolean(isMvpCompleted(item)||(currentCycle()===0&&item.status==="completed"));}
  function visibleItems(){
    const items=Array.isArray(plan?.items)?plan.items:[];
    const byDomain=new Map();
    for(const item of items)if(!byDomain.has(item.goal?.domain))byDomain.set(item.goal?.domain,item);
    const balanced=[byDomain.get("diet"),byDomain.get("activity"),byDomain.get("routine")].filter(Boolean);
    // Old already-issued plans can predate the balanced policy. Keep their
    // three real assignments visible rather than inventing mismatched cards.
    return balanced.length===3?balanced:items.slice(0,3);
  }
  function detailNote(item){return Array.from(root.querySelectorAll?.(`[data-session="${item.id}"] [name="note"]`)||[]).map(field=>field.value?.trim()).filter(Boolean).join("\n");}
  function saveMvpCompletion(item){
    const water=waterGoal(item);
    const record={assignmentId:item.id,domain:item.goal.domain,note:detailNote(item),completedAt:new Date().toISOString(),...(water?{waterCups:water.cups,waterCupMl:water.cupMl}:null)};
    mvpCompletions={...mvpCompletions,[completionKey(item)]:record};
    try{window.localStorage?.setItem(mvpStorageKey,JSON.stringify(mvpCompletions));}catch{}
    if(water)saveWaterCupProgress(item,new Set(Array.from({length:water.cups},(_,i)=>i+1)));
    return record;
  }
  function showCelebration(item){
    const view=domainView[item.goal.domain]||domainView.routine;
    window.dispatchEvent(new CustomEvent("forest-challenge-celebrated",{detail:{assignmentId:item.id,completionKey:completionKey(item),domain:item.goal.domain,label:view.label,message:view.message,image:view.image}}));
    if(!document.body?.insertAdjacentHTML)return;
    document.getElementById?.("challenge-celebration")?.remove?.();
    document.body.insertAdjacentHTML("beforeend",`<section id="challenge-celebration" class="v2-celebration" role="dialog" aria-modal="true" aria-labelledby="challenge-celebration-title"><div class="v2-celebration-card"><img src="${view.image}" alt="프리셋 친구들이 함께 ${view.label} 챌린지를 마친 모습"><span>${view.label} 챌린지 완료</span><h2 id="challenge-celebration-title">${view.message}</h2><p>오늘의 실천을 함께 축하해요!</p><button type="button" data-celebration-close>확인</button></div></section>`);
    const celebration=document.getElementById?.("challenge-celebration");
    celebration?.querySelector?.("[data-celebration-close]")?.addEventListener?.("click",()=>celebration.remove());
    celebration?.querySelector?.("button")?.focus?.();
  }
  async function readJson(response) {
    try { return await response.json(); } catch { return {}; }
  }
  async function refreshToken(forceRefresh=false) {
    if(window.GandangAuthSession){
      try{token=(await window.GandangAuthSession.resolve({forceRefresh})).token;return;}
      catch(error){error.needsSetup=[401,403].includes(error.status);if(error.needsSetup)token=null;throw error;}
    }
    const auth=await fetch("/api/v1/auth/token/refresh",{credentials:"same-origin",cache:"no-store"});
    if (!auth.ok) {
      const result=await readJson(auth);
      // JwtService uses 400 for an invalid refresh cookie, not an API outage.
      const invalidRefresh=auth.status===400&&result.detail==="Provided invalid token.";
      const needsLogin=auth.status===401||auth.status===403||invalidRefresh;
      if(needsLogin)token=null;
      const error=new Error(needsLogin?"로그인하고 챌린지 시작!":"로그인 상태를 확인하지 못했어요. 잠시 후 새로고침해 주세요.");
      error.needsSetup=needsLogin;throw error;
    }
    token=(await readJson(auth)).access_token;
    if(typeof token!=="string"||!token)throw new Error("로그인 상태를 확인하지 못했어요. 잠시 후 새로고침해 주세요.");
  }
  async function api(path,options={},canRefresh=true) {
    token=token||window.challengeV2TokenProvider?.()||window.GandangAuthSession?.read();
    if (!token) await refreshToken();
    const headers={Authorization:`Bearer ${token}`};
    if (options.body && !(options.body instanceof FormData)) headers["Content-Type"]="application/json";
    const response=await fetch(`/api/v1/challenge-v2${path}`,{...options,headers,credentials:"same-origin",cache:"no-store"});
    if(response.status===401&&canRefresh){
      token=null;
      await refreshToken(true);
      return api(path,options,false);
    }
    const result=await readJson(response);
    if (!response.ok) {
      if(response.status===401)token=null;
      const error=new Error(typeof result.detail==="string"?result.detail:"입력값을 확인해 주세요. 저장하지 못했습니다.");
      error.needsSetup=response.status===401||response.status===403;throw error;
    }
    return result.data;
  }
  const input=(name,label,type="text",extra="")=>`<label>${label}<input name="${name}" type="${type}" ${extra} required></label>`;
  function compactSettings(p={}) {
    const check=(name,label,fallback=false)=>`<label class="v2-check"><input type="checkbox" name="${name}" ${(p[name]??fallback)?"checked":""}>${label}</label>`;
    return `<section id="daily-settings" class="v2-compact-settings" data-settings ${settingsOpen?"":"hidden"} aria-label="챌린지 다시 설정하기">
      <div class="v2-mode-buttons" role="group" aria-label="챌린지 구성 선택">
        <button type="button" data-quick-mode="activity_focus">운동 위주</button>
        <button type="button" data-quick-mode="diet_focus">식단 위주</button>
        <button type="button" data-custom-mode aria-expanded="false" aria-controls="v2-custom-preferences">나만의 챌린지</button>
      </div>
      <form id="v2-custom-preferences" data-preferences data-custom-preferences hidden>
        <input type="hidden" name="mode" value="balanced">
        <label>난이도<select name="max_difficulty">${Object.entries(levelLabel).map(([k,v])=>`<option value="${k}" ${(p.max_difficulty||"E")===k?"selected":""}>${v}</option>`).join("")}</select></label>
        <label>식단 챌린지<select name="diet_family">${Object.entries({random:"랜덤",D01:"식사 구성",D02:"영양표시",D03:"식사 기록"}).map(([k,v])=>`<option value="${k}" ${(p.diet_family||"random")===k?"selected":""}>${v}</option>`).join("")}</select></label>
        <label>운동 챌린지<select name="activity_family">${Object.entries({random:"랜덤",A01:"걷기",A02:"오래 앉기 줄이기"}).map(([k,v])=>`<option value="${k}" ${(p.activity_family||"random")===k?"selected":""}>${v}</option>`).join("")}</select></label>
        <label>음료 챌린지<select name="routine_family">${Object.entries({random:"랜덤",H01:"단 음료 바꾸기",H02:"수분 기록",R01:"저녁 습관"}).map(([k,v])=>`<option value="${k}" ${(p.routine_family||"random")===k?"selected":""}>${v}</option>`).join("")}</select></label>
        <label>개인 음료 목표 확인<select name="water_goal_status">${Object.entries({unconfirmed:"아직 확인하지 않음",confirmed:"개인 목표가 있음",clinician_review_required:"의료진 확인 필요"}).map(([k,v])=>`<option value="${k}" ${(p.water_goal_status||"unconfirmed")===k?"selected":""}>${v}</option>`).join("")}</select></label>
        ${input("personal_drink_goal_ml","확인한 하루 음료 목표량(mL)","number",`min="200" max="4000" value="${p.personal_drink_goal_ml??""}"`)}
        <input type="hidden" name="water_cup_ml" value="200">
        ${input("planned_meals","오늘 예정된 식사 횟수","number",`min="0" max="3" value="${p.planned_meals??1}"`)}
        ${input("sugary_drink_opportunities","단 음료 기회 횟수","number",`min="0" max="3" value="${p.sugary_drink_opportunities??0}"`)}
        ${check("safety_confirmed","안전 조건을 확인했어요")}${check("exercise_allowed","편안히 움직일 수 있어요")}
        ${check("dietary_changes_allowed","의료진 지침 안에서 식사 구성을 바꿀 수 있어요")}${check("fluid_restriction","수분 제한이 있거나 아직 몰라요",true)}
        ${check("swallowing_restriction","씹기·삼키기 제한이 있거나 아직 몰라요",true)}${check("therapeutic_diet","치료식이 필요하거나 아직 몰라요",true)}${check("food_allergy","음식 알레르기가 있거나 아직 몰라요",true)}
        ${check("photo_accessible","사진·활동기록 화면을 제출할 수 있어요")}${check("photo_consent","사진 확인에 동의해요")}
        <label class="v2-check"><input type="checkbox" name="transition_consent" required ${p.transition_consent?"checked":""}>기존 기록과 보상을 유지할게요</label>
        <button>나만의 챌린지 저장</button>
      </form>
    </section>`;
  }
  function settings(p={}) {
    const check=(name,label,fallback=false)=>`<label class="v2-check"><input type="checkbox" name="${name}" ${(p[name]??fallback)?"checked":""}>${label}</label>`;
    return `<section id="daily-settings" data-settings ${settingsOpen?"":"hidden"} aria-label="챌린지 설정"><h4>나에게 맞게 다시 설정하기</h4><form data-preferences>
      <label>챌린지 방식<select name="mode">${Object.entries({balanced:"균형",activity_focus:"운동 중심",diet_focus:"식단 중심"}).map(([k,v])=>`<option value="${k}" ${p.mode===k?"selected":""}>${v}</option>`).join("")}</select></label>
      <label>어느 정도까지 할 수 있나요?<select name="max_difficulty">${Object.entries(levelLabel).map(([k,v])=>`<option value="${k}" ${(p.max_difficulty||"E")===k?"selected":""}>${v}</option>`).join("")}</select></label>
      ${input("planned_meals","오늘 예정된 식사 횟수","number",`min="0" max="3" value="${p.planned_meals??1}"`)}
      ${input("sugary_drink_opportunities","하루에 단 음료를 마시는 횟수(없으면 0)","number",`min="0" max="3" value="${p.sugary_drink_opportunities??0}"`)}
      <label>개인 음료 목표 확인<select name="water_goal_status">${Object.entries({unconfirmed:"아직 확인하지 않음",confirmed:"개인 목표가 있음",clinician_review_required:"의료진 확인 필요"}).map(([k,v])=>`<option value="${k}" ${(p.water_goal_status||"unconfirmed")===k?"selected":""}>${v}</option>`).join("")}</select></label>
      ${input("personal_drink_goal_ml","확인한 하루 음료 목표량(mL)","number",`min="200" max="4000" value="${p.personal_drink_goal_ml??""}"`)}
      <input type="hidden" name="water_cup_ml" value="200">
      ${check("safety_confirmed","아래 안전 조건을 확인했어요")}${check("exercise_allowed","통증·낙상 위험·운동 제한 없이 편안히 걸을 수 있어요")}
      ${check("dietary_changes_allowed","의료진 지침 안에서 식사 구성을 바꿀 수 있어요")}${check("fluid_restriction","수분 제한이 있거나 아직 몰라요",true)}
      ${check("swallowing_restriction","씹기·삼키기 제한이 있거나 아직 몰라요",true)}${check("therapeutic_diet","치료식이 필요하거나 아직 몰라요",true)}${check("food_allergy","음식 알레르기가 있거나 아직 몰라요",true)}
      ${check("photo_accessible","사진·활동기록 화면을 제출할 수 있어요")}${check("photo_consent","사진을 비공개로 최대 7일 보관하고 지정 담당자가 확인하는 데 동의해요 (선택)")}
      <p>사진은 외부 자동 분석 서비스로 보내지 않아요. 사진 없이 직접 기록할 수도 있어요. 다른 사람이나 개인정보가 찍힌 사진은 피해주세요. 사진 동의를 해제하고 저장하면 보관한 사진을 삭제해요.</p>
      <label class="v2-check"><input type="checkbox" name="transition_consent" required ${p.transition_consent?"checked":""}>기존 기록과 보상을 유지하며 새 챌린지를 시작할게요</label>
      <p>기존 챌린지를 진행 중이면 새 챌린지는 내일부터 시작해요. 바꾼 방식과 난이도는 다음 챌린지부터, 건강을 위한 제한은 바로 적용돼요.</p><button>설정 저장</button></form></section>`;
  }
  function sessionForm(item,index) {
    const g=item.goal, current=new Date(Date.now()+9*3600000).toISOString().slice(0,16);
    return `<details><summary>회차 ${index} 기록</summary><form data-session="${item.id}" data-index="${index}">
      ${input("performed_at","수행 시각 (한국 시간, 활동은 종료 시각)","datetime-local",`value="${current}"`)}
      ${g.goal_unit==="minute"?input("quantity","이번 회차 시간(분)","number",`min="${g.per_session_quantity}" max="1440"`):""}
      ${g.family_id==="H02"?input("intake_ml",`${["오전","오후","저녁"][index-1]} 구간 실제 섭취량(mL)`,"number",'min="0" max="20000"')+'<small>이전 구간과 겹치지 않는 양만 기록하세요. 0mL도 정상이며 더 마실 필요가 없습니다.</small>':""}
      <label>상세 기록<textarea name="note" maxlength="500" ${g.domain==="diet"?"required":""} placeholder="오늘 실천한 내용이나 느낀 점을 남길 수 있어요."></textarea></label>
      ${g.family_id==="D02"?input("serving_amount","표시 기준량","number",'min="0.01" step="any"')+'<label>기준 단위<select name="serving_unit"><option>g</option><option>mL</option></select></label>'+input("sugar_g","당류(g)","number",'min="0" step="any"')+(g.difficulty!=="E"?input("carbohydrate_g","총탄수화물(g)","number",'min="0" step="any"')+input("product_category","제품 종류","text",'maxlength="80"'):""):""}
      ${["D02","D03"].includes(g.family_id)&&g.difficulty==="H"&&index===g.target_sessions?`<label>${g.family_id==="D02"?"동일 100g 또는 100mL 기준 비교":"다음 날 개선점 한 줄"}<textarea name="improvement" maxlength="200" required></textarea></label>`:""}
      <label class="v2-check"><input name="done" type="checkbox" required>이 회차를 직접 수행하고 기록했어요</label><button>회차 저장</button></form></details>`;
  }
  function card(item) {
    const g=item.goal;
    const uploads=Array.from({length:g.required_uploads},(_,i)=>{
      const proof=item.evidence.find(x=>x.index===i+1);
      return `<form data-upload="${item.id}" data-index="${i+1}">${input("photo",`사진 ${i+1}${proof?` · ${proof.expired?"보관 만료":statusLabel[proof.status]}`:""}`,"file",'accept="image/jpeg,image/png,image/webp"')}<button>사진 제출</button></form>`;
    }).join("");
    return `<article class="v2-card"><div class="v2-tags"><span>${({diet:"식단",activity:"운동",routine:"생활관리"})[g.domain]}</span><span>${levelLabel[g.difficulty]}</span><span>${proofLabel[g.proof_type]}</span></div>
      <h4>${esc(g.title)}</h4><p>목표 ${g.per_session_quantity}${g.goal_unit==="minute"?"분":"회 기록"} × ${g.target_sessions}회</p>
      <strong>회차 ${item.completed_sessions}/${g.target_sessions}${g.goal_unit==="minute"?` · 총 ${item.total_quantity}/${g.per_session_quantity*g.target_sessions}분`:""} · ${statusLabel[item.status]}</strong><progress max="${g.target_sessions}" value="${item.completed_sessions}" aria-label="회차 진행률"></progress>
      ${item.verification_status==="pending"?'<p class="v2-notice">사진 조건 검토 대기 중입니다. 완료·보상은 확인 후 지급됩니다.</p>':""}
      ${["inconclusive","needs_retry"].includes(item.verification_status)?'<p class="v2-notice">사진을 확인하기 어려워요. 오늘 안에 다시 올리거나 사진 없이 기록하는 챌린지를 골라주세요.</p>':""}
      <p class="v2-safety">${esc(g.safety)}</p>
      ${item.status!=="completed"?Array.from({length:g.target_sessions},(_,i)=>item.sessions.some(s=>s.index===i+1)?`<small>회차 ${i+1} 저장됨</small>`:sessionForm(item,i+1)).join("")+uploads+`<button type="button" data-alternatives="${item.id}">다른 챌린지로 바꾸기</button><div data-options="${item.id}"></div>`:`<p>${g.proof_type==="T1"?"사진 조건 확인":g.proof_type==="T2"?"기록 제출 완료":"자가 기록 완료"} · 당근 10개 지급</p>`}
      <details><summary>근거·확인 범위</summary><p>목표 수치는 앱 시작용 설계이며 예방 효과의 순위가 아닙니다. 사진으로 실제 섭취나 걷기 진위를 증명하지 않습니다.</p>${g.sources.map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>`).join(" · ")}</details></article>`;
  }
  function compactQuest(item,openIds) {
    const g=item.goal, mvpRecord=completionRecord(item), complete=isCompleted(item), domain=domainView[g.domain]||domainView.routine, water=waterGoal(item), waterProgress=water?waterCupProgress(item):null;
    const pending=!complete&&item.verification_status==="pending"&&item.completed_sessions>=g.target_sessions;
    const waterReady=!water||waterProgress.size>=water.cups;
    const label=complete?"인증완료":pending?"확인 중":water&&!waterReady?"컵 체크 중":"인증하기";
    const summary=water?`${water.cupMl}mL 컵 ${water.cups}개 · ${waterProgress.size}/${water.cups}`:g.goal_unit==="minute"?`${g.per_session_quantity}분 × ${g.target_sessions}회`:`${g.target_sessions}회 기록`;
    const waterButtons=water&&!complete&&!pending?`<div class="v2-water-cups" role="group" aria-label="${water.cupMl}mL 컵 ${water.cups}개 체크">${Array.from({length:water.cups},(_,i)=>{const cup=i+1,checked=waterProgress.has(cup);return `<button type="button" data-water-cup="${esc(item.id)}" data-cup-index="${cup}" aria-pressed="${checked}" class="${checked?"is-checked":""}" aria-label="물컵 ${cup}/${water.cups} ${checked?"체크됨":"체크하기"}"><span class="v2-water-icon" aria-hidden="true"></span><small>${cup}/${water.cups}</small></button>`;}).join("")}</div>`:"";
    const completedNote=item.status==="completed"&&mvpRecord?`<label class="v2-completed-note">추가 기록<textarea data-mvp-note="${esc(item.id)}" maxlength="500" placeholder="오늘 실천한 내용이나 느낀 점을 남길 수 있어요.">${esc(mvpRecord.note||"")}</textarea></label>`:"";
    return `<article class="v2-quest-card${complete?" is-complete":""}">
      <span class="v2-domain-badge" data-domain="${g.domain}">${domain.label}</span><h4>${esc(g.title)}</h4><div class="v2-quest-row"><small>${summary} · ${complete?g.target_sessions:item.completed_sessions}/${g.target_sessions}</small>
      <button type="button" data-certify="${esc(item.id)}" aria-label="${esc(g.title)} ${label}" ${complete||pending||!waterReady?"disabled":""}>${label}</button></div>${waterButtons}
      <details class="v2-quest-details" data-quest-details="${esc(item.id)}" ${openIds.has(String(item.id))?"open":""}><summary>자세히 보기</summary>${card(item)}${completedNote}</details></article>`;
  }
  function openRecordDetails(itemId) {
    const detail=root.querySelector(`[data-quest-details="${itemId}"]`);
    if(!detail)return;
    detail.open=true;
    const field=detail.querySelector("form input:not([disabled]), form textarea:not([disabled]), form select:not([disabled])");
    if(field){const session=field.closest("details");if(session)session.open=true;field.focus();}
    else detail.querySelector("summary")?.focus();
  }
  function quickSessionPayload(item,index,form,performedAt=new Date()) {
    const g=item.goal;
    // Photo evidence and measurement-heavy drink/label reviews still need the
    // user-provided file or actual value. A click must never fabricate those.
    const water=waterGoal(item);
    if(g.proof_type!=="T3"||g.family_id==="D02"||(g.family_id==="H02"&&!water))return null;
    const note=form?.querySelector?.('[name="note"]')?.value?.trim()||"직접 인증 완료";
    const values={performed_at:performedAt.toISOString(),done:true,note};
    if(g.goal_unit==="minute")values.quantity=Number(g.per_session_quantity);
    if(water){values.quantity=water.cups;values.intake_ml=water.cups*water.cupMl;}
    if(g.family_id==="D03"&&g.difficulty==="H"&&index===g.target_sessions)values.improvement=note;
    return values;
  }
  function compactContent(openIds) {
    const items=visibleItems(), cycleComplete=items.length===3&&items.every(isCompleted);
    return `<p data-message role="status" aria-live="polite"></p>
      <div class="v2-compact-cards">${items.map(item=>compactQuest(item,openIds)).join("")}</div>
      ${!items.length?`<p class="v2-notice">설정을 저장했어요.${plan.starts_on?` ${esc(plan.starts_on)}부터 오늘의 퀘스트가 표시돼요.`:" 오늘의 퀘스트를 준비하고 있어요."}</p>`:""}
      ${cycleComplete?`<button class="v2-repeat-button" data-repeat-quests type="button">오늘의 퀘스트 다시 하기</button>`:""}
      <button id="forest-quest-settings" class="v2-settings-button" data-open-settings type="button" aria-label="나에게 맞게 다시 설정하기" aria-expanded="${settingsOpen}" aria-controls="daily-settings">${settingsOpen?"다시 설정 닫기":"나에게 맞게 다시 설정하기"}</button>
      ${compactSettings(plan.preferences)}<section data-compact-settings ${settingsOpen?"":"hidden"} aria-label="챌린지 안내와 보상">
      ${(plan.proof_mix_exception_reason||[]).map(r=>`<p class="v2-notice">${esc(reasonLabel[r]||"몸 상태에 맞는 다른 챌린지를 골랐어요.")}</p>`).join("")}
      ${(plan.substitutions||[]).map(()=>'<p class="v2-notice">단 음료 줄이기 대신 마신 양을 돌아보는 챌린지를 골랐어요. 더 마실 필요는 없어요.</p>').join("")}
      <p>오늘 ${plan.completed||0}/${plan.items?.length||0}개 완료${!plan.day_id?` · 시작일 ${esc(plan.starts_on)}`:""}</p>
      ${plan.day_id?`<p class="v2-wallet">계정 당근 ${plan.carrot_balance??100}개 · ${plan.chest_issued?"오늘의 보물상자를 받았어요":"오늘 할 일을 모두 마치면 보물상자를 받아요"}</p><small>숲 체험에서 모은 당근과 아이템은 따로 보관돼요.</small>`:""}
      <button data-refresh type="button">새로고침</button></section>`;
  }
  function setSettingsOpen(open,button=null) {
    settingsOpen=open;
    const section=root.querySelector("[data-settings]");if(section)section.hidden=!open;
    const management=root.querySelector("[data-compact-settings]");if(management)management.hidden=!open;
    const toggle=button||root.querySelector("#forest-quest-settings");
    if(toggle){toggle.setAttribute("aria-expanded",String(open));toggle.textContent=open?"다시 설정 닫기":"나에게 맞게 다시 설정하기";}
    if(open)root.querySelector("[data-settings] button")?.focus();
  }
  function preferencePayload(overrides={}) {
    const current=plan?.preferences||{};
    return {
      mode:"balanced", safety_confirmed:false, exercise_allowed:false, dietary_changes_allowed:false,
      planned_meals:1, sugary_drink_opportunities:0, fluid_restriction:true, swallowing_restriction:true,
      therapeutic_diet:true, food_allergy:true, photo_consent:false, photo_accessible:false,
      transition_consent:true, max_difficulty:"E",
      diet_family:"random", activity_family:"random", routine_family:"random", water_goal_status:"unconfirmed", personal_drink_goal_ml:null, water_cup_ml:200, ...current, ...overrides,
    };
  }
  async function savePreferences(values) {
    await api("/preferences",{method:"PUT",body:JSON.stringify(values)});
    plan=await api("/today",{method:"POST"});
    settingsOpen=false;
    render();
    notify("오늘의 음료·식단·운동 퀘스트를 다시 골랐어요.");
    channel?.postMessage("refresh");
  }
  function render() {
    if(!plan?.enrolled)settingsOpen=true;
    const compact=forestView&&plan?.enrolled&&!needsSetup&&!connectionFailed;
    const openIds=new Set(Array.from(root.querySelectorAll?.(".v2-quest-details[open]")||[],item=>item.dataset.questDetails));
    root.setAttribute?.("data-compact",String(Boolean(compact)));
    root.innerHTML=compact?compactContent(openIds):`<header class="v2-heading"><h3>당뇨 예방 챌린지</h3><button data-refresh type="button">새로고침</button></header><p data-message role="status" aria-live="polite"></p>${forestView?"":'<p class="v2-safety">생활습관을 돌아보는 활동이에요. 진단·처방이나 건강이 좋아졌다는 판정을 대신하지 않아요.</p>'}
      ${needsSetup?`<a class="v2-setup-link" href="${setupUrl}">로그인하고 챌린지 시작!</a>`:connectionFailed?'<p>연결을 확인한 뒤 위의 새로고침을 눌러주세요. 연결되지 않은 동안에는 설정과 기록을 저장할 수 없어요.</p>':`<button class="v2-settings-button" data-open-settings type="button" aria-expanded="${settingsOpen}" aria-controls="daily-settings">${settingsOpen?"다시 설정 닫기":"나에게 맞게 다시 설정하기"}</button>
      ${(plan?.proof_mix_exception_reason||[]).map(r=>`<p class="v2-notice">${esc(reasonLabel[r]||"몸 상태에 맞는 다른 챌린지를 골랐어요.")}</p>`).join("")}
      ${(plan?.substitutions||[]).map(()=>'<p class="v2-notice">단 음료 줄이기 대신 마신 양을 돌아보는 챌린지를 골랐어요. 더 마실 필요는 없어요.</p>').join("")}
      ${settings(plan?.preferences)}<div class="v2-cards">${(plan?.items||[]).map(card).join("")}</div>
      ${plan?.enrolled?`<p>오늘 ${plan.completed||0}/${plan.items.length}개 완료${!plan.day_id?` · 시작일 ${esc(plan.starts_on)}`:""}</p>`:""}
      ${plan?.day_id?`<p class="v2-wallet">계정 당근 ${plan.carrot_balance??100}개 · ${plan.chest_issued?"오늘의 보물상자를 받았어요":"오늘 할 일을 모두 마치면 보물상자를 받아요"}</p><small>숲 체험에서 모은 당근과 아이템은 따로 보관돼요.</small>`:""}`}`;
    const items=plan?visibleItems():[];
    const effectivePlan=plan?{...plan,items,completed:items.filter(isCompleted).length}:plan;
    window.ForestChallengeV2.plan=effectivePlan;
    if(root.parentElement.matches('[data-step="7"]'))root.insertAdjacentHTML("beforeend",'<button type="button" data-dashboard>대시보드로 이동</button>');
    window.dispatchEvent(new CustomEvent("challenge-v2-updated",{detail:effectivePlan}));
  }
  let noticeTimer;
  const notify=message=>{
    const notice=root.querySelector("[data-message]");
    if(!notice)return;
    notice.textContent=message;
    notice.classList.add("record-notice");
    notice.hidden=false;
    clearTimeout(noticeTimer);
    noticeTimer=setTimeout(()=>{notice.hidden=true;},6000);
  };
  async function load() {
    if(busy)return;busy=true;
    try {plan=await api("/today",{method:"POST"});needsSetup=false;connectionFailed=false;render();} catch(error){needsSetup=Boolean(error.needsSetup);connectionFailed=!needsSetup;plan=null;render();notify(error.message);} finally{busy=false;}
  }
  root.addEventListener("click",async event=>{
    if(event.target.closest("[data-refresh]"))return load();
    if(event.target.closest("[data-repeat-quests]")){
      mvpCycles={...mvpCycles,[planDayKey()]:currentCycle()+1};
      try{window.localStorage?.setItem(mvpCycleStorageKey,JSON.stringify(mvpCycles));}catch{}
      render();notify("오늘의 퀘스트 3개를 다시 수행할 수 있어요. 표시되는 회차는 늘어나지 않습니다.");
      return;
    }
    const cupButton=event.target.closest("[data-water-cup]");
    if(cupButton){
      const item=plan?.items?.find(candidate=>String(candidate.id)===String(cupButton.dataset.waterCup));
      const water=item&&waterGoal(item), cup=Number(cupButton.dataset.cupIndex);
      if(!water||isCompleted(item)||!Number.isInteger(cup))return;
      const progress=waterCupProgress(item);
      if(progress.has(cup))progress.delete(cup);else progress.add(cup);
      saveWaterCupProgress(item,progress);
      render();notify(progress.size>=water.cups?"컵을 모두 체크했어요. 이제 인증할 수 있어요.":"체크한 컵을 저장했어요.");
      return;
    }
    const certify=event.target.closest("[data-certify]");
    if(certify){
      if(busy||certify.disabled)return;
      const item=plan?.items?.find(candidate=>String(candidate.id)===String(certify.dataset.certify));
      const missing=item?Array.from({length:item.goal.target_sessions},(_,i)=>i+1).filter(index=>!item.sessions.some(session=>session.index===index)):[];
      const firstForm=missing.length?root.querySelector(`[data-session="${certify.dataset.certify}"][data-index="${missing[0]}"]`):null;
      if(!item)return;
      saveMvpCompletion(item);render();showCelebration(item);notify("인증을 완료했어요. 자세히 보기에 작성한 내용도 함께 보관했어요.");
      const firstPayload=missing.length?quickSessionPayload(item,missing[0],firstForm):null;
      if(!missing.length||!firstPayload)return;
      busy=true;
      try{
        const interval=Math.max(60000,item.goal.goal_unit==="minute"?Number(item.goal.per_session_quantity)*60000:60000);
        for(const [position,index] of missing.entries()){
          const form=position===0&&firstForm?firstForm:root.querySelector(`[data-session="${certify.dataset.certify}"][data-index="${index}"]`);
          const performedAt=new Date(Date.now()-(missing.length-position-1)*interval);
          const values=quickSessionPayload(item,index,form,performedAt);
          plan={...plan,...await api(`/assignments/${item.id}/sessions/${index}`,{method:"PUT",body:JSON.stringify(values)})};
        }
        render();notify("인증과 상세 기록을 저장했어요.");channel?.postMessage("refresh");
      }catch(error){notify(`MVP 인증은 완료했어요. 서버 상세 저장은 다시 시도해 주세요: ${error.message}`);}
      finally{busy=false;}
      return;
    }
    const settingsButton=event.target.closest("[data-open-settings]");
    if(settingsButton){
      setSettingsOpen(!settingsOpen,settingsButton);
      return;
    }
    const quickMode=event.target.closest("[data-quick-mode]");
    if(quickMode){
      if(busy)return;
      busy=true;quickMode.disabled=true;
      try{await savePreferences(preferencePayload({mode:quickMode.dataset.quickMode,diet_family:"random",activity_family:"random",routine_family:"random"}));}
      catch(error){notify(error.message);}
      finally{busy=false;quickMode.disabled=false;}
      return;
    }
    const customMode=event.target.closest("[data-custom-mode]");
    if(customMode){
      const form=root.querySelector("[data-custom-preferences]");
      const open=Boolean(form?.hidden);
      if(form)form.hidden=!open;
      customMode.setAttribute("aria-expanded",String(open));
      if(open)form.querySelector("select,input:not([type=hidden])")?.focus();
      return;
    }
    if(event.target.closest("[data-dashboard]"))return window.dispatchEvent(new Event("challenge-v2-open-dashboard"));
    const button=event.target.closest("[data-alternatives]");if(!button)return;
    try {
      const {items}=await api(`/assignments/${button.dataset.alternatives}/alternatives`);
      root.querySelector(`[data-options="${button.dataset.alternatives}"]`).innerHTML=`<form data-replace="${button.dataset.alternatives}"><label>새로 할 챌린지<select name="template_code" required>${items.map(x=>`<option value="${x.code}">${levelLabel[x.difficulty]} · ${proofLabel[x.proof_type]} · ${esc(x.title)}</option>`).join("")}</select></label><label>바꾸는 이유<select name="reason"><option value="accessibility">사진 찍기가 어려워요</option><option value="too_hard">더 쉬운 활동을 하고 싶어요</option><option value="safety">몸 상태에 맞게 바꾸고 싶어요</option><option value="preference">다른 활동을 하고 싶어요</option></select></label><p>이전 기록은 남겨두고 새 챌린지에서 다시 시작해요. 이미 완료한 챌린지는 바꿀 수 없어요.</p><button ${items.length?"":"disabled"}>이 챌린지로 바꾸기</button></form>`;
    }catch(error){notify(error.message);}
  });
  root.addEventListener("input",event=>{
    const completedNote=event.target.closest?.("[data-mvp-note]");
    if(completedNote){
      const item=plan?.items?.find(candidate=>String(candidate.id)===String(completedNote.dataset.mvpNote));
      if(!item||!isMvpCompleted(item))return;
      const key=completionKey(item),previous=mvpCompletions[key]||{};
      mvpCompletions={...mvpCompletions,[key]:{...previous,assignmentId:item.id,domain:item.goal.domain,note:completedNote.value?.trim()||""}};
      try{window.localStorage?.setItem(mvpStorageKey,JSON.stringify(mvpCompletions));}catch{}
      return;
    }
    const note=event.target.closest?.('[name="note"]');
    const form=note?.closest?.("[data-session]");
    const item=form&&plan?.items?.find(candidate=>String(candidate.id)===String(form.dataset.session));
    if(!item||!isMvpCompleted(item))return;
    const key=completionKey(item),previous=mvpCompletions[key]||{};
    mvpCompletions={...mvpCompletions,[key]:{...previous,assignmentId:item.id,domain:item.goal.domain,note:detailNote(item)}};
    try{window.localStorage?.setItem(mvpStorageKey,JSON.stringify(mvpCompletions));}catch{}
  });
  root.addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;
    const form=event.target,data=new FormData(form),values=Object.fromEntries(data);
    busy=true;const buttons=[...form.querySelectorAll("button")];buttons.forEach(b=>b.disabled=true);
    try {
      if(form.matches("[data-preferences]")) {
        for(const input of form.querySelectorAll('input[type="checkbox"]'))values[input.name]=input.checked;
        values.planned_meals=Number(values.planned_meals);values.sugary_drink_opportunities=Number(values.sugary_drink_opportunities);
        values.water_cup_ml=200;values.personal_drink_goal_ml=values.personal_drink_goal_ml?Number(values.personal_drink_goal_ml):null;
        await savePreferences(preferencePayload(values));
      }else if(form.matches("[data-session]")) {
        values.done=true;values.performed_at=new Date(`${values.performed_at}:00+09:00`).toISOString();
        for(const key of ["quantity","intake_ml","serving_amount","sugar_g","carbohydrate_g"])if(key in values)values[key]=Number(values[key]);
        plan={...plan,...await api(`/assignments/${form.dataset.session}/sessions/${form.dataset.index}`,{method:"PUT",body:JSON.stringify(values)})};
      }else if(form.matches("[data-upload]")) {
        if(data.get("photo").size>10*1024*1024)throw new Error("사진은 10MB 이하로 올려 주세요.");
        plan={...plan,...await api(`/assignments/${form.dataset.upload}/evidence/${form.dataset.index}`,{method:"PUT",body:data})};
      }else if(form.matches("[data-replace]")) {
        plan={...plan,...await api(`/assignments/${form.dataset.replace}/replacement`,{method:"PATCH",body:JSON.stringify(values)})};
      }
      render();notify("저장했어요.");channel?.postMessage("refresh");
    }catch(error){if(error.needsSetup){needsSetup=true;plan=null;render();}notify(error.message);}finally{busy=false;buttons.forEach(b=>b.disabled=false);}
  });
  window.addEventListener("challenge-v2-auth",()=>{token=null;load();});
  document.addEventListener("visibilitychange",()=>{if(!document.hidden&&!settingsOpen&&!root.contains(document.activeElement))load();});
  window.addEventListener("challenge-v2-step",event=>{
    if(!window.ForestChallengeV2.enabled)return;
    if(event.detail===7) {
      document.querySelector("#challenge-form")?.before(root);
      if(!root.querySelector("[data-dashboard]"))root.insertAdjacentHTML("beforeend",'<button type="button" data-dashboard>대시보드로 이동</button>');
      const title=document.querySelector("#challenge-title");if(title)title.textContent="나에게 맞는 일일 챌린지를 설정해요";
    } else if(event.detail===8) homeParent.prepend(root);
  });
  if(channel)channel.onmessage=()=>{if(!settingsOpen&&!root.contains(document.activeElement))load();};
  fetch("/api/v1/challenge-v2/capabilities",{cache:"no-store"}).then(r=>r.json()).then(result=>{
    if(!result.data.enabled){root.hidden=true;return;}
    window.ForestChallengeV2.enabled=true;document.documentElement.classList.add("challenge-v2-enabled");root.hidden=false;load();
  }).catch(()=>{root.hidden=false;root.textContent="챌린지에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 열어주세요. 연결되지 않은 동안의 완료 기록은 저장할 수 없어요.";});
})();
