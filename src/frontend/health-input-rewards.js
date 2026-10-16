/* Optional inputs earn server-confirmed account rewards, never browser coins. */
((host) => {
  'use strict';
  const HINT = '더 많은 건강정보를 입력하고, 더 높은 예측 결과를 받아보세요. 당근의 숲에서 사용할 수 있는 당근 100개는 덤!';
  const FIELD_IDS = ['waist', 'systolic', 'diastolic', 'health-satisfaction-score',
    'economic-satisfaction-score', 'overall-quality-of-life-score', 'cancer-diagnosis',
    'chronic-lung-disease-diagnosis', 'liver-disease-diagnosis', 'cerebrovascular-disease-diagnosis',
    'psychiatric-disease-diagnosis', 'diabetes-family-history', 'hypertension-family-history',
    'education-level', 'region', 'household-structure', 'annual-household-income'];
  // Reuse the shared-chat attachment unchanged; rotate only its presentation.
  const CARROT = `<svg class="optional-reward-carrot-art" viewBox="0 0 800 420" aria-hidden="true" focusable="false"><g transform="translate(400 210) rotate(55) translate(-614 -625)"><image href="/static/assets/optional-health-carrot-shared.png" width="1200" height="1200" preserveAspectRatio="xMidYMid meet"/></g></svg>`;

  function knownAnswer(field) {
    const value = String(field?.value ?? '').trim();
    return Boolean(value && value !== 'code_97' && field.validity?.valid !== false
      && (field.type !== 'number' || Number.isFinite(Number(value))));
  }

  class HealthInputRewards {
    constructor(root = host) {
      this.host = root;
      this.document = root.document;
      this.ownerId = null;
      this.claimed = new Set();
      this.fields = [];
      this.cache = new Map();
      this.generation = 0;
      this.statusGeneration = 0;
      this.perField = 100;
    }
    setOwner(ownerId) {
      if (this.ownerId === ownerId) return;
      const pendingHint = this.ownerId == null && this.hintSeen;
      this.ownerId = ownerId;
      this.hintSeen = Boolean(pendingHint);
      if (pendingHint && ownerId != null) {
        try { this.host.localStorage.setItem(`gandang.optional-health-reward-hint.v1:${ownerId}`, 'seen'); } catch {}
      }
      this.generation++;
      this.claimed.clear();
      this.cache.clear();
      this.summary?.setAttribute('hidden', '');
      this.render();
    }
    mount() {
      const doc = this.document, form = doc?.getElementById('health-form');
      if (!form || this.mounted) return;
      this.mounted = true;
      for (const id of FIELD_IDS) {
        const input = doc.getElementById(id);
        if (!input || input.required) continue;
        const row = doc.createElement('span'); row.className = 'optional-reward-input';
        const label = doc.querySelector(`label[for="${id}"]`);
        const name = label?.firstChild?.textContent?.trim() || label?.textContent?.trim() || id;
        input.before(row); row.append(input);
        const button = doc.createElement('button');
        button.type = 'button'; button.className = 'optional-reward-carrot';
        button.innerHTML = `${CARROT}<span>+100</span>`;
        button.setAttribute('aria-label', `${name} 입력하고 당근 100개 받기 안내`);
        row.append(button);
        const key = ({ waist: 'waist_cm', systolic: 'systolic_bp', diastolic: 'diastolic_bp',
          'annual-household-income': 'annual_household_income_10k_krw' })[id] || id.replaceAll('-', '_');
        const field = { id, key, input, row, button, name };
        this.fields.push(field);
        button.addEventListener('click', () => this.activate(field));
        input.addEventListener('focus', () => row.classList.add('is-editing'));
        input.addEventListener('blur', () => row.classList.remove('is-editing'));
      }
      const legend = doc.createElement('p'); legend.className = 'optional-reward-legend';
      legend.textContent = '🥕 표시된 선택 정보 1개당 당근 100개 · 계정별 항목당 한 번 · 아는 정보만 입력해 주세요.';
      form.prepend(legend);
      const preview = doc.createElement('p'); preview.className = 'optional-reward-preview';
      preview.setAttribute('role', 'status'); legend.after(preview); this.preview = preview;
      form.addEventListener('input', () => this.render());
      form.addEventListener('change', () => this.render());
      this.summary = doc.createElement('section');
      this.summary.id = 'optional-health-reward-summary'; this.summary.className = 'optional-health-reward-summary';
      this.summary.hidden = true; this.summary.setAttribute('role', 'status'); this.summary.setAttribute('aria-live', 'polite');
      doc.getElementById('prediction-status-card')?.before(this.summary);
      const dialog = doc.createElement('dialog'); dialog.className = 'optional-reward-hint';
      dialog.setAttribute('aria-labelledby', 'optional-reward-hint-title');
      dialog.innerHTML = `<h2 id="optional-reward-hint-title">선택 건강정보 입력 보상</h2><p>${HINT}</p><p class="optional-reward-hint-note">모르면 비워 두어도 분석을 계속할 수 있어요.</p><button type="button">입력하러 가기</button>`;
      doc.body.append(dialog); this.dialog = dialog;
      dialog.querySelector('button').addEventListener('click', () => dialog.close());
      dialog.addEventListener('close', () => this.activeField?.input.focus());
      this.render();
    }
    activate(field) {
      this.activeField = field;
      field.row.classList.add('is-editing');
      const key = `gandang.optional-health-reward-hint.v1:${this.ownerId ?? 'device'}`;
      let seen = this.hintSeen;
      try { seen ||= this.host.localStorage.getItem(key) === 'seen'; } catch {}
      if (!seen) {
        this.hintSeen = true;
        try { this.host.localStorage.setItem(key, 'seen'); } catch {}
        this.dialog.showModal();
      } else field.input.focus();
    }
    render() {
      let count = 0;
      for (const field of this.fields) {
        const filled = knownAnswer(field.input), claimed = field.key && this.claimed.has(field.key);
        field.row.classList.toggle('is-filled', filled);
        field.row.classList.toggle('is-claimed', Boolean(claimed));
        field.button.disabled = Boolean(claimed);
        field.button.querySelector('span').textContent = claimed ? '지급 완료' : `+${this.perField}`;
        if (filled && !claimed) count++;
      }
      if (this.preview) this.preview.textContent = `선택 정보 ${count}개 입력 · 예상 당근 ${count * this.perField}개 (저장 확인 후 지급)`;
    }
    async refreshStatus({ api, ownerId, isCurrent = () => true }) {
      if (ownerId != null) this.setOwner(ownerId);
      const serial = ++this.statusGeneration;
      try {
        const result = await api('/health-input-rewards');
        if (!isCurrent() || serial !== this.statusGeneration || (ownerId != null && result.user_id !== ownerId)) return;
        if (!Array.isArray(result.fields) || !Number.isInteger(result.carrots_per_field) || result.carrots_per_field < 0) return;
        this.setOwner(result.user_id);
        this.perField = result.carrots_per_field;
        const fields = new Map(result.fields.map(field => [field.input_id, field]));
        for (const item of this.fields) item.key = fields.get(item.id)?.key || null;
        this.claimed = new Set(result.fields.filter(field => field.claimed).map(field => field.key));
        this.render();
      } catch { if (isCurrent()) this.render(); } // An unavailable preview never grants money.
    }
    renderSummary(result, error = null) {
      if (!this.summary) return;
      const doc = this.document, panel = this.summary;
      panel.replaceChildren(); panel.hidden = false;
      const title = doc.createElement('h3'), copy = doc.createElement('p');
      panel.append(title, copy);
      if (error) {
        title.textContent = '당근 지급 내역을 확인하지 못했어요';
        copy.textContent = '분석은 계속 진행됩니다. 연결 상태를 확인한 뒤 지급 내역을 다시 확인해 주세요.';
        const retry = doc.createElement('button'); retry.type = 'button'; retry.textContent = '지급 내역 다시 확인';
        retry.addEventListener('click', () => { void this.claim(this.lastOptions); }); panel.append(retry);
      } else if (!result) {
        title.textContent = '선택 정보 보상을 확인하고 있어요';
        copy.textContent = '서버에 저장된 선택 정보를 확인해 계정 지갑에 지급합니다.';
      } else {
        title.textContent = result.earned_carrots > 0 ? `🥕 당근 ${result.earned_carrots}개를 획득했어요!`
          : result.checkup_reward_carrots > 0 ? `🥕 이번 건강정보로 받은 당근 ${result.checkup_reward_carrots}개` : '이번 분석의 추가 당근은 0개예요';
        copy.textContent = result.earned_carrots > 0 ? `선택 정보 ${result.rewarded_fields.length}개 × ${result.carrots_per_field}개 · 계정 지갑에 저장했어요.`
          : result.checkup_reward_carrots > 0 ? '이미 계정 지갑에 반영된 보상입니다. 다시 지급하지 않습니다.'
            : '아직 입력하지 않았거나 이미 보상받은 항목은 추가 지급에서 제외됩니다.';
        const list = doc.createElement('ul');
        for (const field of result.rewarded_fields) {
          const item = doc.createElement('li'); item.textContent = `${field.label} +${field.amount}개`; list.append(item);
        }
        if (result.rewarded_fields.length) {
          const details = doc.createElement('details'), heading = doc.createElement('summary');
          heading.textContent = '지급 항목 자세히 보기'; details.append(heading, list); panel.append(details);
        }
        const balance = doc.createElement('p'); balance.className = 'optional-reward-balance';
        balance.textContent = `현재 계정 지갑: 당근 ${result.carrot_balance}개 · 당근의 숲에서 사용할 수 있어요.`; panel.append(balance);
      }
    }
    async claim(options) {
      const { api, checkupId, inputId, ownerId, isCurrent = () => true } = options;
      if (ownerId != null) this.setOwner(ownerId);
      if (!isCurrent() || !Number.isSafeInteger(Number(checkupId)) || Number(checkupId) <= 0) return null;
      const key = `${this.ownerId}:${checkupId}:${inputId ?? ''}`;
      if (this.cache.has(key)) {
        const result = await this.cache.get(key);
        if (isCurrent() && result) this.renderSummary(result);
        return result;
      }
      const generation = this.generation;
      this.statusGeneration++;
      this.lastOptions = options;
      this.renderSummary(null);
      const pending = Promise.resolve().then(async () => {
        const controller = new AbortController();
        let timeout;
        const deadline = new Promise((_, reject) => {
          timeout = this.host.setTimeout(() => {
            controller.abort(); reject(new Error('Reward confirmation timed out'));
          }, 12000);
        });
        try {
          const result = await Promise.race([api('/health-input-rewards/claim', {
            method: 'POST', signal: controller.signal,
            body: JSON.stringify({ checkup_id: Number(checkupId), ...(inputId ? { current_screening_input_id: Number(inputId) } : {}) }),
          }), deadline]);
          if (!isCurrent() || generation !== this.generation || (ownerId != null && result.user_id !== ownerId)) {
            this.cache.delete(key);
            return null;
          }
          if (!Number.isInteger(result.earned_carrots) || result.earned_carrots < 0 || !Array.isArray(result.rewarded_fields)
              || !Array.isArray(result.eligible_fields) || !Number.isInteger(result.carrot_balance) || result.carrot_balance < 0
              || result.earned_carrots !== result.rewarded_fields.reduce((total, field) => total + field.amount, 0)
              || result.checkup_id !== Number(checkupId)) throw new Error('Invalid wallet receipt');
          for (const field of result.eligible_fields) this.claimed.add(field);
          this.render(); this.renderSummary(result);
          this.host.ForestWallet?.accept(result);
          return result;
        } catch (error) {
          if (isCurrent() && generation === this.generation) this.renderSummary(null, error);
          this.cache.delete(key);
          return null;
        } finally { this.host.clearTimeout(timeout); }
      });
      this.cache.set(key, pending);
      return pending;
    }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { HealthInputRewards, knownAnswer, FIELD_IDS, HINT };
  else { host.HealthInputRewards = new HealthInputRewards(host); host.HealthInputRewards.mount(); }
})(typeof window !== 'undefined' ? window : globalThis);
