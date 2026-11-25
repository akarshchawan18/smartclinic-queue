// Sound and vibration alerts. Browsers only allow sound after a tap, so the patient taps "Turn on sound alert" once.
// Tones are generated in the browser, so no audio files are needed. Edit the notes below to change the sounds.
const Alert = (() => {
  let ctx = null, on = false;

  // iPhone: play through the speaker even when the silent switch is on (newer Safari only)
  try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) {}

  function tone(freq, start, dur, vol = 0.6) {
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + start;
    o.type = 'triangle'; o.frequency.value = freq;
    o.connect(g); g.connect(ctx.destination);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.start(t); o.stop(t + dur + 0.05);
  }

  const sounds = {
    near: () => tone(660, 0, 0.4),                                    // 1-2 patients ahead: one beep
    next: () => { tone(660, 0, 0.3); tone(880, 0.35, 0.4); },         // you're next: two beeps
    turn: () => [0, 0.9].forEach(d => {                               // your turn: rising chime, twice
      tone(784, d, 0.3); tone(988, d + 0.25, 0.3); tone(1175, d + 0.5, 0.5);
    }),
  };
  const buzz = { near: [200], next: [200, 100, 200], turn: [300, 150, 300, 150, 500] };

  return {
    get enabled() { return on; },
    get state() { return ctx ? ctx.state : 'none'; },      // "running" means sound is allowed
    enable() {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      ctx = ctx || new AC();
      ctx.resume();
      on = true;
      sounds.near();
      return true;
    },
    disable() { on = false; },
    test() { if (ctx) { ctx.resume(); sounds.turn(); if (navigator.vibrate) navigator.vibrate(buzz.turn); } },
    play(kind) {
      if (!on || !ctx) return;
      ctx.resume();
      if (sounds[kind]) sounds[kind]();
      if (navigator.vibrate) navigator.vibrate(buzz[kind] || [200]);
    },
  };
})();