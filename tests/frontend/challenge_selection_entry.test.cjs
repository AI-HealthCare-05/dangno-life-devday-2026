const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("src/frontend/app.js", "utf8");

function load(names, context) {
  const ctx = vm.createContext(context);
  for (const name of names) {
    const fn = source.match(new RegExp(`^(?:async )?function ${name}\\([^]*?^}`, "m"));
    assert.ok(fn, name);
    vm.runInContext(fn[0], ctx);
  }
  return ctx;
}

test("new user without a cycle can select from home; ongoing cycle hides the extra entry", () => {
  const nodes = {};
  const $ = key => nodes[key] ||= { hidden: false, textContent: "" };
  const state = { cycle: null, dailyCompleted: new Set(), visitedSteps: new Set([2, 3, 4, 5, 6, 8]) };
  const ctx = load(["hasCurrentChallengeCycle", "dailyChallengeTargetCount", "allDailyChallengesCompleted", "renderTodayTaskStatus"], { $, state });
  ctx.renderTodayTaskStatus();
  assert.equal($("#today-select-challenge").hidden, false);
  assert.match($("#today-task-title").textContent, /선택한 챌린지가 없/);
  state.cycle = { status: "active", user_challenges: [{ user_challenge_id: 1 }] };
  ctx.renderTodayTaskStatus();
  assert.equal($("#today-select-challenge").hidden, true);
});

test("terminated cycles are not reused after corrected eligibility", () => {
  const ctx = load(["hasCurrentChallengeCycle"], {});
  for (const status of ["completed", "cancelled", "terminated"]) {
    assert.equal(ctx.hasCurrentChallengeCycle({ status, user_challenges: [{ user_challenge_id: 1 }] }), false);
  }
  assert.equal(ctx.hasCurrentChallengeCycle({ status: "active", user_challenges: [{ user_challenge_id: 1 }] }), true);
});

test("newly analysed user reaches selection before slow recommendations complete", async () => {
  const state = { token: "test-session", cycle: null, step: 8, visitedSteps: new Set([2, 3, 4, 5, 6, 8]) };
  let resolve;
  let started = false;
  const ctx = load(["hasCurrentChallengeCycle", "openChallengeTab"], {
    state,
    isLocalPreview: () => false,
    requireActiveHealthConsent: () => true,
    api: async () => {
      throw Object.assign(new Error("진행 중인 챌린지가 없습니다."), { status: 404 });
    },
    clearCurrentChallengeCycle() { state.cycle = null; },
    showChallengeSelectionView() {},
    showStep(step) { state.step = step; },
    loadChallenges() {
      started = true;
      return new Promise(done => { resolve = done; });
    },
  });
  const pending = ctx.openChallengeTab();
  await new Promise(done => setImmediate(done));
  assert.equal(started, true);
  assert.equal(state.step, 7);
  resolve();
  await pending;
});

test("high-risk result guidance remains available after challenge selection without blocking eligible continuation", () => {
  const nodes = { "#risk-confirm-card": { dataset: { risk: "high" } } };
  const $ = key => nodes[key] || null;
  const state = {
    visitedSteps: new Set([6]),
    capabilities: { challenge: true },
    eligibility: { reason_codes: [] },
    medicalGuidanceRequired: false,
  };
  const ctx = load(["canContinueAfterMedicalGuidance", "requiresMedicalResultGuidance"], {
    $, state,
  });
  assert.equal(ctx.requiresMedicalResultGuidance(), true);
  state.visitedSteps.add(7);
  assert.equal(ctx.requiresMedicalResultGuidance(), true);
  assert.equal(ctx.canContinueAfterMedicalGuidance(), true);
});

test("result screen keeps medical guidance when a safety exclusion still blocks challenges", () => {
  const nodes = { "#risk-confirm-card": { dataset: { risk: "high" } } };
  const $ = key => nodes[key] || null;
  const state = {
    visitedSteps: new Set([6, 7]),
    capabilities: { challenge: true },
    eligibility: { reason_codes: ["URGENT_MEDICAL_ATTENTION"] },
    medicalGuidanceRequired: false,
  };
  const ctx = load(["canContinueAfterMedicalGuidance", "requiresMedicalResultGuidance"], {
    $, state,
  });
  assert.equal(ctx.requiresMedicalResultGuidance(), true);
  assert.equal(ctx.canContinueAfterMedicalGuidance(), false);
});

test("cycle lookup failure is not treated as an empty cycle or allowed to replace it", async () => {
  const state = { token: "test-session", cycle: null };
  let selected = false;
  const ctx = load(["hasCurrentChallengeCycle", "openChallengeTab"], {
    state,
    isLocalPreview: () => false,
    requireActiveHealthConsent: () => true,
    api: async () => {
      throw Object.assign(new Error("서비스 연결 실패"), { status: 503 });
    },
    showChallengeSelectionView() { selected = true; },
    loadChallenges() { selected = true; },
  });
  await assert.rejects(ctx.openChallengeTab(), /서비스 연결 실패/);
  assert.equal(selected, false);
});

test("empty recording state always includes a selection button", () => {
  const nodes = {};
  const $ = key => nodes[key] ||= { hidden: false, innerHTML: "", closest() { return this; } };
  const state = { cycle: null, activeWorkspace: "challenge" };
  const ctx = load(["hasCurrentChallengeCycle", "renderDailyRecordList"], { $, state, renderBarrierForm() {} });
  ctx.renderDailyRecordList();
  assert.match($("#daily-log-list").innerHTML, /기록할 챌린지가 없습니다/);
  assert.match($("#daily-log-list").innerHTML, /class="primary daily-record-select"/);
  assert.match($("#daily-log-list").innerHTML, /생활습관 챌린지 선택하기/);
});

test("home refresh shows an approved current result without an active challenge", async () => {
  const nodes = {};
  const $ = key => nodes[key] ||= { hidden: false, textContent: "", dataset: {}, src: "", alt: "" };
  const calls = [];
  const state = { cycle: null, dailyCompleted: new Set() };
  const card = {
    model_key: "diabetes_current_screening", result_status: "approved",
    promotion_status: "approved", risk_category: "high", risk_category_label: "높음",
  };
  const noop = async () => {};
  const ctx = load(["normalizeRiskKey", "renderDashboardRiskSummary", "refreshDashboard"], {
    $, state,
    loadDailyRecords: noop,
    renderTodayTaskStatus: () => calls.push("today-task"),
    api: async path => {
      calls.push(path);
      if (path === "/dashboard/summary") return { risk_cards: [card] };
      if (path === "/dashboard/challenge-progress") return { recent_7_days: { completed: 0 } };
      throw new Error(`Unexpected API: ${path}`);
    },
    loadWeeklyReport: noop, loadEducation: noop, loadConnections: noop,
    loadInvitations: noop, loadSharedGroups: noop, loadHealthCheckupHistory: noop,
  });
  await ctx.refreshDashboard();
  assert.equal($("#dashboard-stage").textContent, "높음");
  assert.equal($("#dashboard-risk-summary").dataset.risk, "high");
  assert.equal($("#dashboard-complete").textContent, "0개");
  assert.ok(calls.includes("today-task"));
  assert.ok(calls.includes("/dashboard/summary"));
});
