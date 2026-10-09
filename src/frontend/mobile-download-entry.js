document.querySelectorAll('[data-mobile-download]').forEach(button => {
  if (window.Capacitor?.isNativePlatform?.()) {
    (button.closest('li') || button).hidden = true;
    return;
  }
  button.addEventListener('click', () => window.location.assign('/mobile-downloads'));
});
