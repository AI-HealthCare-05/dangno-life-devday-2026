
import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { createApiFetch, API_ORIGIN } from './network.mjs';
import { handleAppBack } from './back-navigation.mjs';
import { enableManualBirthDates } from './birth-date.mjs';

function keepIosHeaderClear() {
  const header = document.querySelector('.topbar');
  if (!header) return;
  const update = () => document.documentElement.style.setProperty(
    '--native-header-height', `${Math.ceil(header.getBoundingClientRect().height)}px`
  );
  const updateViewport = () => document.documentElement.style.setProperty(
    '--native-viewport-top', `${Math.max(0, Math.ceil(window.visualViewport?.offsetTop || 0))}px`
  );
  update();
  updateViewport();
  new ResizeObserver(update).observe(header);
  window.visualViewport?.addEventListener('scroll', updateViewport, { passive: true });
  window.visualViewport?.addEventListener('resize', updateViewport, { passive: true });
}

function keepOverlaysInViewport() {
  // Illustrated screens can establish containing blocks for fixed descendants.
  // Move only viewport overlays; their IDs and existing event listeners survive.
  for (const id of [
    'eligibility-guidance', 'profile-editor', 'emergency-questionnaire-modal',
    'diagnosis-help-modal', 'record-modal',
  ]) {
    const overlay = document.getElementById(id);
    if (overlay) document.body.append(overlay);
  }
}

function enableCompactHealthPanelPicker() {
  const picker = document.querySelector('.health-input-carousel');
  if (!picker) return;
  picker.addEventListener('click', (event) => {
    const button = event.target.closest('[data-health-tab]');
    if (!button) return;
    if (!picker.classList.contains('is-open')) {
      picker.classList.add('is-open');
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    picker.classList.remove('is-open');
  }, true);
  document.addEventListener('click', (event) => {
    if (!picker.contains(event.target)) picker.classList.remove('is-open');
  });
}

// Loaded synchronously before the existing page scripts, in mobile bundles only.
window.GandangMobile = Object.freeze({ apiOrigin: API_ORIGIN });
if (Capacitor.isNativePlatform()) {
  window.fetch = createApiFetch(window.fetch.bind(window), window.location.href);
  document.documentElement.classList.add('gandang-native');
  if (Capacitor.getPlatform() === 'ios') {
    document.documentElement.classList.add('gandang-ios');
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        enableManualBirthDates();
        keepIosHeaderClear();
        keepOverlaysInViewport();
        enableCompactHealthPanelPicker();
      }, { once: true });
    } else {
      enableManualBirthDates();
      keepIosHeaderClear();
      keepOverlaysInViewport();
      enableCompactHealthPanelPicker();
    }
  }
  let picking = false;
  function notice(message) {
    let node = document.getElementById('mobile-notice');
    if (!node) {
      node = document.createElement('div'); node.id = 'mobile-notice';
      node.setAttribute('role', 'status'); node.setAttribute('aria-live', 'polite');
      document.body.append(node);
    }
    node.textContent = message;
    clearTimeout(notice.timer); notice.timer = setTimeout(() => node.remove(), 7000);
  }
  async function selectPhoto(input) {
    if (picking) return;
    picking = true;
    try {
      const photo = await Camera.getPhoto({
        quality: 80, width: 1600, height: 1600, correctOrientation: true,
        resultType: CameraResultType.Uri, source: CameraSource.Prompt,
        saveToGallery: false, promptLabelHeader: '사진 첨부',
        promptLabelPhoto: '사진에서 선택', promptLabelPicture: '사진 촬영',
        promptLabelCancel: '취소',
      });
      if (!photo.webPath) throw new Error('사진을 읽을 수 없습니다.');
      const response = await fetch(photo.webPath);
      if (!response.ok) throw new Error('사진을 읽을 수 없습니다.');
      const blob = await response.blob();
      if (!['image/jpeg','image/png','image/webp'].includes(blob.type)) {
        throw new Error('JPEG, PNG, WebP 사진을 선택해 주세요.');
      }
      if (!blob.size || blob.size > 8 * 1024 * 1024) throw new Error('8MB 이하의 사진을 선택해 주세요.');
      const bitmap = await createImageBitmap(blob);
      const pixels = bitmap.width * bitmap.height; bitmap.close();
      if (pixels > 12000000) throw new Error('사진 크기를 줄여 다시 선택해 주세요.');
      const extension = blob.type === 'image/jpeg' ? 'jpg' : blob.type.split('/')[1];
      const data = new DataTransfer();
      data.items.add(new File([blob], 'challenge-photo.' + extension, { type: blob.type }));
      input.files = data.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (error) {
      if (!/cancel|취소/i.test(error?.message || '')) {
        notice(error?.message || '사진을 열 수 없습니다. 앱 설정에서 권한을 확인해 주세요.');
      }
    } finally { picking = false; }
  }
  document.addEventListener('click', event => {
    const input = event.target.closest?.('#v3-photo-file');
    if (!input || input.disabled) return;
    event.preventDefault(); event.stopImmediatePropagation();
    void selectPhoto(input);
  }, true);

  App.addListener('backButton', ({ canGoBack }) => {
    handleAppBack({ document, window, app: App, canGoBack });
  }).catch(() => {});
  App.addListener('appRestoredResult', result => {
    if (result.pluginId === 'Camera') {
      // A killed Activity loses the selected challenge. Never attach to another one.
      const show = () => notice('앱이 다시 시작되었습니다. 해당 챌린지에서 사진을 다시 선택해 주세요.');
      if (document.body) show(); else document.addEventListener('DOMContentLoaded', show, { once: true });
    }
  }).catch(() => {});
}
