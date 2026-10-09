const BIRTH_DATE_IDS = ['profile-birthday', 'signup-birth-date', 'recovery-birthday', 'eligibility-birth-date'];

export function normalizeBirthDate(value) {
  const text = String(value ?? '').trim();
  const parts = /^(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*$/.exec(text)
    || /^(\d{4})(\d{2})(\d{2})$/.exec(text);
  if (!parts) return null;
  const [year, month, day] = parts.slice(1).map(Number);
  const date = new Date(0);
  date.setUTCHours(0, 0, 0, 0);
  date.setUTCFullYear(year, month - 1, day);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function enableManualBirthDates(doc = document) {
  for (const id of BIRTH_DATE_IDS) {
    const input = doc.getElementById(id);
    if (!input || input.type !== 'date') continue;
    input.type = 'text';
    input.inputMode = 'numeric';
    input.autocomplete = 'bday';
    input.placeholder = '예: 19711009';
    input.setAttribute('aria-label', '생년월일, 숫자 8자리로 입력. 예: 19711009');
    input.dataset.birthDateManual = 'true';
    const hint = doc.createElement('small');
    hint.className = 'birth-date-hint';
    hint.textContent = '연도·월·일 순서로 숫자 8자리 입력';
    input.insertAdjacentElement('afterend', hint);

    const validate = () => {
      const value = input.value.trim();
      input.setCustomValidity(value && !normalizeBirthDate(value)
        ? '올바른 생년월일 8자리를 입력해 주세요. 예: 19711009' : '');
    };
    const normalize = () => {
      const value = normalizeBirthDate(input.value);
      if (value) input.value = value;
      validate();
    };
    input.addEventListener('input', validate);
    input.addEventListener('blur', normalize);
    input.form?.addEventListener('submit', normalize, true);
    validate();
  }
}
