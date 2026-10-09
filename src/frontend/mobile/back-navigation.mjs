export function handleAppBack({ document, window, app, canGoBack }) {
  const dialog = [...document.querySelectorAll('dialog[open]')].at(-1);
  if (dialog) {
    const close = dialog.querySelector('.dialog-close, [id*="close"], [data-close]');
    if (close) close.click();
    else if (dialog.dispatchEvent(new Event('cancel', { cancelable: true }))) dialog.close();
    return;
  }
  const modal = [...document.querySelectorAll('[aria-modal="true"], .record-modal')]
    .reverse().find(node => !node.hidden && node.getClientRects().length);
  const close = modal?.querySelector('.record-modal-close, .dialog-close, [id*="close"], [aria-label*="닫기"]');
  if (close) { close.click(); return; }
  const chat = document.getElementById('chat-panel');
  if (chat && !chat.hidden) { document.getElementById('chat-close')?.click(); return; }
  const settings = document.querySelector('.forest-game-settings[open]');
  if (settings) { settings.open = false; return; }
  if (document.documentElement.classList.contains('forest-ingame')) {
    window.dispatchEvent(new Event('forest-input-reset'));
    let exit = document.getElementById('forest-exit-confirm');
    if (!exit) {
      exit = document.createElement('dialog');
      exit.id = 'forest-exit-confirm';
      exit.className = 'forest-exit-confirm';
      exit.setAttribute('aria-labelledby', 'forest-exit-title');
      exit.innerHTML = '<h2 id="forest-exit-title">서비스 홈 화면으로 나가시겠습니까?</h2><div class="forest-exit-actions"><button type="button" data-close>계속 플레이</button><button type="button" data-exit>서비스 홈으로</button></div>';
      exit.querySelector('[data-close]').addEventListener('click', () => exit.close());
      exit.querySelector('[data-exit]').addEventListener('click', () => {
        window.location.assign('/?workspace=home');
      });
      document.body.append(exit);
    }
    exit.showModal();
    return;
  }
  if (window.GandangPageBack?.()) return;
  if (canGoBack) window.history.back();
  else app.minimizeApp().catch(() => {});
}
