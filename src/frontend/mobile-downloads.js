const platforms = ['android', 'ios'];
function selectPlatform(platform) {
  platforms.forEach(os => {
    const selected = os === platform;
    const tab = document.getElementById(`tab-${os}`);
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(`panel-${os}`).hidden = !selected;
  });
}
platforms.forEach(os => {
  const tab = document.getElementById(`tab-${os}`);
  tab.addEventListener('click', () => selectPlatform(os));
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 'android' : event.key === 'End' ? 'ios' : os === 'ios' ? 'android' : 'ios';
    selectPlatform(next);
    document.getElementById(`tab-${next}`).focus();
  });
});
const requested = new URLSearchParams(location.search).get('os');
const detected = 'android';
selectPlatform(platforms.includes(requested) ? requested : detected);
fetch('/api/mobile-downloads', {credentials:'omit', cache:'no-store'})
  .then(response => { if (!response.ok) throw new Error('unavailable'); return response.json(); })
  .then(data => platforms.forEach(os => {
    const url = data[os]?.url;
    const anchor = document.getElementById(`download-${os}`);
    const status = document.getElementById(`status-${os}`);
    let valid = false;
    try { const parsed = new URL(url); valid = parsed.protocol === 'https:' && !parsed.username && !parsed.password; } catch {}
    if (valid) {
      anchor.href = url;
      anchor.rel = 'noopener noreferrer';
      anchor.hidden = false;
      status.textContent = '아래 설치 안내를 따라 모바일 앱을 이용해 보세요.';
    } else {
      status.textContent = '앱 다운로드를 준비하고 있어요. 설치 링크가 준비되면 이곳에서 받을 수 있어요.';
    }
  }))
  .catch(() => platforms.forEach(os => {
    document.getElementById(`status-${os}`).textContent = '다운로드 정보를 불러오지 못했어요. 잠시 후 다시 확인해 주세요.';
  }));
