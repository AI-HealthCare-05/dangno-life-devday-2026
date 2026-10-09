(() => {
  'use strict';
  const frame = document.querySelector('.canvas-frame');
  const header = document.querySelector('.studio-topbar');
  if (!frame || !header) return;
  document.documentElement.classList.add('forest-ingame');
  const settings = document.createElement('details');
  settings.className = 'forest-game-settings';
  settings.innerHTML = '<summary aria-label="게임 설정">설정</summary><div class="forest-settings-content"></div>';
  settings.querySelector('summary').textContent = '설정';
  settings.querySelector('summary').setAttribute('aria-label', '게임 설정');
  const content = settings.querySelector('.forest-settings-content');
  const actions = header.querySelector('.topbar-actions');
  const stats = document.createElement('div');
  stats.className = 'forest-game-stats';
  for (const selector of ['.carrot-balance', '#open-profile']) stats.append(actions.querySelector(selector));
  content.append(actions);
  content.append(document.querySelector('.forest-weather-strip'));
  const home = document.createElement('a');
  home.className = 'forest-service-home';
  // Return to the current retro home, whose startup restores the cookie session.
  // /service is the older namespaced UI and has a separate startup flow.
  home.href = '/static/intro-retro.html';
  home.textContent = '서비스 홈';
  home.setAttribute('aria-label', '서비스 홈으로 이동');
  home.addEventListener('click', () => window.dispatchEvent(new Event('forest-input-reset')));
  header.append(stats, settings, home);
  frame.append(header);
  const drawer = document.createElement('dialog');
  drawer.id = 'forest-hud-drawer';
  drawer.className = 'forest-hud-drawer';
  drawer.setAttribute('aria-label', '숲 챌린지와 모임');
  drawer.innerHTML = '<button type="button" class="forest-drawer-close" aria-label="숲 메뉴 닫기">닫기 ×</button>';
  drawer.append(document.querySelector('.right-hud'));
  frame.append(drawer);
  drawer.querySelector('button').addEventListener('click', () => drawer.close());
  drawer.addEventListener('click', event => { if (event.target === drawer) drawer.close(); });
  const nav = document.createElement('nav');
  nav.className = 'forest-game-tabs';
  nav.setAttribute('aria-label', '인게임 탭 메뉴');
  nav.innerHTML = ['옷장', '창고', '챌린지', '모임', '채팅'].map((label, index) =>
    `<button type="button" data-hud-tab="${index}" aria-pressed="false">${label}</button>`).join('');
  frame.append(nav);
  const resetInput = () => window.dispatchEvent(new Event('forest-input-reset'));
  settings.addEventListener('toggle', () => { if (settings.open) resetInput(); });
  nav.addEventListener('click', event => {
    const button = event.target.closest('[data-hud-tab]');
    if (!button) return;
    resetInput(); settings.open = false;
    if (drawer.open) drawer.close();
    nav.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    switch (button.dataset.hudTab) {
      case '0': document.getElementById('open-avatar-studio').click(); break;
      case '1': document.querySelector('[data-workspace-target="asset-dock"]').click(); break;
      case '2':
      case '3': {
        drawer.showModal();
        const panel = button.dataset.hudTab === '2' ? 'quests-panel' : 'team-inspector';
        document.querySelector(`[data-inspector-tab="${panel}"]`).click();
        break;
      }
      case '4': document.getElementById('chat-toggle').click(); break;
    }
  });
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('close', () => {
    nav.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', 'false'));
  }));
  document.getElementById('chat-close').addEventListener('click', () => {
    nav.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', 'false'));
  });
})();
