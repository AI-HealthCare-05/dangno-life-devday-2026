(() => {
  'use strict';
  const pad = document.getElementById('forest-joystick');
  if (!pad) return;
  const knob = pad.querySelector('.joystick-knob');
  let pointer = null;
  let timer;
  window.ForestJoystickInput = { x: 0, y: 0 };
  function reset() {
    const oldPointer = pointer;
    pointer = null;
    clearInterval(timer);
    window.ForestJoystickInput = { x: 0, y: 0 };
    knob.style.transform = 'translate(0px, 0px)';
    pad.classList.remove('is-active');
    if (oldPointer !== null && pad.hasPointerCapture(oldPointer)) pad.releasePointerCapture(oldPointer);
  }
  function update(event) {
    const bounds = pad.getBoundingClientRect();
    const radius = bounds.width * .32;
    let x = (event.clientX - bounds.left - bounds.width / 2) / radius;
    let y = (event.clientY - bounds.top - bounds.height / 2) / radius;
    const length = Math.hypot(x, y);
    if (length > 1) { x /= length; y /= length; }
    knob.style.transform = `translate(${x * radius}px, ${y * radius}px)`;
    const magnitude = Math.hypot(x, y);
    // Displacement selects direction only; walking/running owns movement speed.
    window.ForestJoystickInput = length < .18 ? { x: 0, y: 0 }
      : { x: x / magnitude, y: y / magnitude };
  }
  pad.addEventListener('pointerdown', event => {
    if (pointer !== null || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault(); event.stopPropagation();
    pointer = event.pointerId;
    pad.setPointerCapture(pointer);
    pad.focus({ preventScroll: true });
    pad.classList.add('is-active');
    update(event);
    // Legacy canvas movement remains available when Phaser cannot initialize.
    timer = setInterval(() => {
      if (window.carrotForestPhaserActive) return;
      const { x, y } = window.ForestJoystickInput;
      if (!x && !y) return;
      const direction = Math.abs(x) > Math.abs(y) ? (x > 0 ? 'right' : 'left') : (y > 0 ? 'down' : 'up');
      window.dispatchEvent(new CustomEvent('forest-joystick-step', { detail: { direction } }));
    }, 100);
  });
  pad.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer) return;
    event.preventDefault(); event.stopPropagation(); update(event);
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    pad.addEventListener(name, event => { if (event.pointerId === pointer) reset(); });
  }
  window.addEventListener('blur', reset);
  window.addEventListener('forest-input-reset', reset);
  document.addEventListener('visibilitychange', () => { if (document.hidden) reset(); });
  for (const id of ['controls-toggle', 'ui-toggle', 'reset-position']) {
    document.getElementById(id)?.addEventListener('click', reset);
  }
})();
